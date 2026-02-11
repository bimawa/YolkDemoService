import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yolk.api.deps import get_llm_client, get_session_db
from yolk.models.call import CallEvaluation, SalesCall, SkillGap
from yolk.schemas.call import CallCreate, CallResponse, EvaluationResponse, SkillGapResponse
from yolk.services.evaluation import EvaluationError, EvaluationService
from yolk.services.llm import LLMClient

router = APIRouter(prefix="/calls", tags=["calls"])


@router.post("/", response_model=CallResponse, status_code=status.HTTP_201_CREATED)
async def create_call(
    payload: CallCreate,
    db: AsyncSession = Depends(get_session_db),
) -> SalesCall:
    call = SalesCall(**payload.model_dump())
    db.add(call)
    await db.flush()
    return call


@router.get("/", response_model=list[CallResponse])
async def list_calls(
    db: AsyncSession = Depends(get_session_db),
    user_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[SalesCall]:
    query = select(SalesCall)
    if user_id:
        query = query.where(SalesCall.user_id == user_id)
    query = query.offset(skip).limit(limit).order_by(SalesCall.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_db),
) -> SalesCall:
    call = await db.get(SalesCall, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


@router.post("/{call_id}/evaluate", response_model=EvaluationResponse)
async def evaluate_call(
    call_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_db),
    llm_client: LLMClient = Depends(get_llm_client),
) -> CallEvaluation:
    service = EvaluationService(llm_client)
    try:
        return await service.evaluate_call(call_id, db)
    except EvaluationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{call_id}/evaluation", response_model=EvaluationResponse)
async def get_evaluation(
    call_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_db),
) -> CallEvaluation:
    result = await db.execute(select(CallEvaluation).where(CallEvaluation.call_id == call_id))
    evaluation = result.scalar_one_or_none()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return evaluation


@router.get("/users/{user_id}/skill-gaps", response_model=list[SkillGapResponse])
async def get_user_skill_gaps(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_db),
) -> list[SkillGap]:
    result = await db.execute(
        select(SkillGap)
        .where(SkillGap.user_id == user_id, SkillGap.is_resolved == False)  # noqa: E712
        .order_by(SkillGap.score.asc())
    )
    return list(result.scalars().all())
