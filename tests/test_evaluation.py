import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from yolk.services.evaluation import EvaluationService
from yolk.services.llm import LLMClient, LLMResponse

MOCK_EVALUATION_RESULT = {
    "overall_score": 6.5,
    "rubric_results": {
        "asked_about_budget": {
            "question": "Did the rep ask about budget?",
            "answer": False,
            "confidence": 0.9,
            "evidence": "No budget question found in transcript",
        },
        "identified_decision_maker": {
            "question": "Did the rep identify the decision maker?",
            "answer": True,
            "confidence": 0.85,
            "evidence": "Rep asked: Who else is involved in this decision?",
        },
    },
    "skill_scores": {
        "discovery": {
            "skill_name": "discovery",
            "category": "qualification",
            "score": 4.0,
            "max_score": 10.0,
            "feedback": "Missed key discovery questions about budget and pain points",
        },
        "objection_handling": {
            "skill_name": "objection_handling",
            "category": "negotiation",
            "score": 7.0,
            "max_score": 10.0,
            "feedback": "Handled price objection well",
        },
        "closing": {
            "skill_name": "closing",
            "category": "closing",
            "score": 3.0,
            "max_score": 10.0,
            "feedback": "Did not attempt to close or establish next steps",
        },
    },
    "strengths": ["Good rapport building", "Professional tone"],
    "weaknesses": ["Missed budget question", "Weak close"],
    "recommended_scenarios": ["discovery_basics", "closing_momentum"],
}


class TestEvaluationService:
    def _make_llm_client(self, response_content: str) -> LLMClient:
        client = MagicMock(spec=LLMClient)
        client.complete = AsyncMock(
            return_value=LLMResponse(
                content=response_content,
                model="gpt-4o-mini",
                usage={"prompt_tokens": 100, "completion_tokens": 200},
            )
        )
        return client

    @pytest.mark.asyncio
    async def test_analyze_transcript_parses_json(self) -> None:
        client = self._make_llm_client(json.dumps(MOCK_EVALUATION_RESULT))
        service = EvaluationService(client)

        result = await service._analyze_transcript("Sales rep: Hello. Buyer: Hi.")
        assert result["overall_score"] == 6.5
        assert "discovery" in result["skill_scores"]

    @pytest.mark.asyncio
    async def test_analyze_transcript_handles_code_block(self) -> None:
        wrapped = f"```json\n{json.dumps(MOCK_EVALUATION_RESULT)}\n```"
        client = self._make_llm_client(wrapped)
        service = EvaluationService(client)

        result = await service._analyze_transcript("Some transcript")
        assert result["overall_score"] == 6.5

    @pytest.mark.asyncio
    async def test_skill_gaps_created_for_low_scores(self) -> None:
        result = MOCK_EVALUATION_RESULT
        low_scoring = {k: v for k, v in result["skill_scores"].items() if v["score"] < 6.0}
        assert len(low_scoring) == 2
        assert "discovery" in low_scoring
        assert "closing" in low_scoring
