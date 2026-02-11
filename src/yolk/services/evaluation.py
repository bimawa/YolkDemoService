from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from sqlalchemy import select

from yolk.models.call import CallEvaluation, SalesCall, SkillGap
from yolk.services.llm import LLMClient, LLMMessage

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

tracer = trace.get_tracer(__name__)

EVALUATION_SYSTEM_PROMPT = (
    "You are an expert sales call evaluator. "
    "Analyze the following sales call transcript "
    "and evaluate the salesperson's performance.\n\n"
    "Return a JSON object with this exact structure:\n"
    "{\n"
    '    "overall_score": <float 0-10>,\n'
    '    "rubric_results": {\n'
    '        "asked_about_budget": {\n'
    '            "question": "Did the rep ask about budget?",\n'
    '            "answer": true/false,\n'
    '            "confidence": <float 0-1>,\n'
    '            "evidence": "quote from transcript"\n'
    "        },\n"
    '        "identified_decision_maker": {\n'
    '            "question": "Did the rep identify the decision maker?",\n'
    '            "answer": true/false,\n'
    '            "confidence": <float 0-1>,\n'
    '            "evidence": "quote"\n'
    "        },\n"
    '        "asked_timeline": {\n'
    '            "question": "Did the rep ask about timeline?",\n'
    '            "answer": true/false,\n'
    '            "confidence": <float 0-1>,\n'
    '            "evidence": "quote"\n'
    "        },\n"
    '        "handled_objections": {\n'
    '            "question": "Did the rep handle objections effectively?",\n'
    '            "answer": true/false,\n'
    '            "confidence": <float 0-1>,\n'
    '            "evidence": "quote"\n'
    "        },\n"
    '        "clear_next_steps": {\n'
    '            "question": "Did the rep establish clear next steps?",\n'
    '            "answer": true/false,\n'
    '            "confidence": <float 0-1>,\n'
    '            "evidence": "quote"\n'
    "        },\n"
    '        "active_listening": {\n'
    '            "question": "Did the rep demonstrate active listening?",\n'
    '            "answer": true/false,\n'
    '            "confidence": <float 0-1>,\n'
    '            "evidence": "quote"\n'
    "        }\n"
    "    },\n"
    '    "skill_scores": {\n'
    '        "discovery": {\n'
    '            "skill_name": "discovery",\n'
    '            "category": "qualification",\n'
    '            "score": <float 0-10>,\n'
    '            "max_score": 10.0,\n'
    '            "feedback": "specific feedback"\n'
    "        },\n"
    '        "objection_handling": {\n'
    '            "skill_name": "objection_handling",\n'
    '            "category": "negotiation",\n'
    '            "score": <float 0-10>,\n'
    '            "max_score": 10.0,\n'
    '            "feedback": "specific feedback"\n'
    "        },\n"
    '        "negotiation": {\n'
    '            "skill_name": "negotiation",\n'
    '            "category": "negotiation",\n'
    '            "score": <float 0-10>,\n'
    '            "max_score": 10.0,\n'
    '            "feedback": "specific feedback"\n'
    "        },\n"
    '        "closing": {\n'
    '            "skill_name": "closing",\n'
    '            "category": "closing",\n'
    '            "score": <float 0-10>,\n'
    '            "max_score": 10.0,\n'
    '            "feedback": "specific feedback"\n'
    "        },\n"
    '        "rapport_building": {\n'
    '            "skill_name": "rapport_building",\n'
    '            "category": "communication",\n'
    '            "score": <float 0-10>,\n'
    '            "max_score": 10.0,\n'
    '            "feedback": "specific feedback"\n'
    "        },\n"
    '        "active_listening": {\n'
    '            "skill_name": "active_listening",\n'
    '            "category": "communication",\n'
    '            "score": <float 0-10>,\n'
    '            "max_score": 10.0,\n'
    '            "feedback": "specific feedback"\n'
    "        }\n"
    "    },\n"
    '    "strengths": ["strength 1", "strength 2"],\n'
    '    "weaknesses": ["weakness 1", "weakness 2"],\n'
    '    "recommended_scenarios": ["scenario_id_1", "scenario_id_2"]\n'
    "}\n\n"
    "Be specific and reference actual parts of the transcript. "
    "Return ONLY valid JSON."
)


class EvaluationService:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def evaluate_call(
        self,
        call_id: uuid.UUID,
        db: AsyncSession,
    ) -> CallEvaluation:
        with tracer.start_as_current_span(
            "evaluation.evaluate_call",
            attributes={"call.id": str(call_id)},
        ):
            call = await db.get(SalesCall, call_id)
            if not call:
                msg = f"Call {call_id} not found"
                raise EvaluationError(msg)

            if not call.transcript:
                msg = f"Call {call_id} has no transcript"
                raise EvaluationError(msg)

            call.status = "processing"
            await db.flush()

            try:
                result = await self._analyze_transcript(call.transcript)
                evaluation = await self._save_evaluation(call, result, db)
                call.status = "evaluated"
                await db.flush()
                return evaluation

            except Exception as e:
                call.status = "failed"
                await db.flush()
                msg = f"Evaluation failed for call {call_id}"
                raise EvaluationError(msg) from e

    async def _analyze_transcript(self, transcript: str) -> dict[str, Any]:
        with tracer.start_as_current_span("evaluation.analyze_transcript"):
            messages = [
                LLMMessage(role="system", content=EVALUATION_SYSTEM_PROMPT),
                LLMMessage(role="user", content=f"Transcript:\n\n{transcript}"),
            ]

            response = await self._llm.complete(messages, temperature=0.3, max_tokens=2048)

            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]

            return json.loads(content)

    async def _save_evaluation(
        self,
        call: SalesCall,
        result: dict[str, Any],
        db: AsyncSession,
    ) -> CallEvaluation:
        with tracer.start_as_current_span("evaluation.save"):
            existing = await db.execute(
                select(CallEvaluation).where(CallEvaluation.call_id == call.id)
            )
            if existing_eval := existing.scalar_one_or_none():
                await db.delete(existing_eval)
                await db.flush()

            evaluation = CallEvaluation(
                call_id=call.id,
                overall_score=result["overall_score"],
                rubric_results=result["rubric_results"],
                skill_scores=result["skill_scores"],
                strengths=result["strengths"],
                weaknesses=result["weaknesses"],
                recommended_scenarios=result.get("recommended_scenarios", []),
            )
            db.add(evaluation)
            await db.flush()

            gap_threshold = 6.0
            for skill_key, skill_data in result["skill_scores"].items():
                score = skill_data["score"]
                if score < gap_threshold:
                    severity = "critical" if score < 3 else "high" if score < 5 else "medium"
                    gap = SkillGap(
                        evaluation_id=evaluation.id,
                        user_id=call.user_id,
                        skill_name=skill_key,
                        category=skill_data.get("category", "general"),
                        severity=severity,
                        score=score,
                        description=skill_data.get("feedback"),
                    )
                    db.add(gap)

            await db.flush()
            return evaluation

    async def get_user_skill_gaps(
        self,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> list[SkillGap]:
        result = await db.execute(
            select(SkillGap)
            .where(SkillGap.user_id == user_id, SkillGap.is_resolved == False)  # noqa: E712
            .order_by(SkillGap.score.asc())
        )
        return list(result.scalars().all())


class EvaluationError(Exception):
    pass
