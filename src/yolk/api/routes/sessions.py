import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yolk.api.deps import get_llm_client, get_session_db
from yolk.models.session import RoleplayMessage, RoleplaySession
from yolk.schemas.session import MessageResponse, SessionCreate, SessionResponse
from yolk.services.evaluation import EvaluationService
from yolk.services.llm import LLMClient, LLMMessage
from yolk.services.orchestrator import GapToGameOrchestrator

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreate,
    db: AsyncSession = Depends(get_session_db),
) -> RoleplaySession:
    session = RoleplaySession(**payload.model_dump())
    db.add(session)
    await db.flush()
    return session


@router.post(
    "/auto-assign/{user_id}",
    response_model=list[SessionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def auto_assign_training(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_db),
    llm_client: LLMClient = Depends(get_llm_client),
) -> list[RoleplaySession]:
    eval_service = EvaluationService(llm_client)
    orchestrator = GapToGameOrchestrator(eval_service)
    sessions = await orchestrator.assign_training(user_id, db)
    if not sessions:
        raise HTTPException(status_code=404, detail="No skill gaps found for user")
    return sessions


@router.get("/", response_model=list[SessionResponse])
async def list_sessions(
    db: AsyncSession = Depends(get_session_db),
    user_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[RoleplaySession]:
    query = select(RoleplaySession)
    if user_id:
        query = query.where(RoleplaySession.user_id == user_id)
    if status_filter:
        query = query.where(RoleplaySession.status == status_filter)
    query = query.offset(skip).limit(limit).order_by(RoleplaySession.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_db),
) -> RoleplaySession:
    session = await db.get(RoleplaySession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def get_session_messages(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_db),
) -> list[RoleplayMessage]:
    session = await db.get(RoleplaySession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.messages


ROLEPLAY_EVAL_PROMPT = (
    "You are an expert sales coach evaluating a roleplay training session.\n"
    "The salesperson practiced against an AI buyer persona.\n\n"
    "Analyze the conversation and return a JSON object:\n"
    "{\n"
    '    "overall_score": <float 0-10>,\n'
    '    "phase_analysis": {\n'
    '        "<phase_name>": {\n'
    '            "score": <float 0-10>,\n'
    '            "feedback": "what they did well/poorly"\n'
    "        }\n"
    "    },\n"
    '    "strengths": ["strength 1", "strength 2"],\n'
    '    "weaknesses": ["weakness 1", "weakness 2"],\n'
    '    "improvement_tips": ["actionable tip 1", "actionable tip 2", "actionable tip 3"],\n'
    '    "buyer_engagement": <float 0-10>,\n'
    '    "would_close_deal": true/false,\n'
    '    "summary": "2-3 sentence overall assessment"\n'
    "}\n\n"
    "Be specific. Reference actual quotes from the conversation.\n"
    "Return ONLY valid JSON."
)


@router.post("/{session_id}/evaluate")
async def evaluate_roleplay_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_db),
    llm_client: LLMClient = Depends(get_llm_client),
) -> dict[str, Any]:
    session = await db.get(RoleplaySession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.messages:
        raise HTTPException(status_code=400, detail="Session has no messages to evaluate")

    transcript_lines = []
    for msg in session.messages:
        role_label = "Sales Rep" if msg.role == "user" else "Buyer"
        transcript_lines.append(f"[{msg.phase}] {role_label}: {msg.content}")
    transcript = "\n".join(transcript_lines)

    scenario_context = (
        f"Scenario: {session.scenario_id}\n"
        f"Target skills: {', '.join(session.target_skills)}\n"
        f"Total turns: {session.turn_count}\n"
    )

    messages = [
        LLMMessage(role="system", content=ROLEPLAY_EVAL_PROMPT),
        LLMMessage(
            role="user",
            content=f"{scenario_context}\nTranscript:\n\n{transcript}",
        ),
    ]

    response = await llm_client.complete(messages, temperature=0.3, max_tokens=2048)
    content = response.content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0]

    try:
        analysis = json.loads(content)
    except json.JSONDecodeError:
        analysis = {"raw_response": content, "parse_error": True}

    session.evaluation_summary = analysis
    await db.flush()

    return {
        "session_id": str(session_id),
        "scenario_id": session.scenario_id,
        "target_skills": session.target_skills,
        "turn_count": session.turn_count,
        "analysis": analysis,
    }
