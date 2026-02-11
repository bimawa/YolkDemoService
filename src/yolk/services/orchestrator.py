from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from opentelemetry import trace

from yolk.models.session import RoleplaySession

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from yolk.models.call import SkillGap
    from yolk.services.evaluation import EvaluationService

tracer = trace.get_tracer(__name__)


@dataclass
class ScenarioConfig:
    scenario_id: str
    name: str
    description: str
    target_skills: list[str]
    difficulty: str
    buyer_persona: str
    context: str


SCENARIO_CATALOG: dict[str, ScenarioConfig] = {
    "discovery_basics": ScenarioConfig(
        scenario_id="discovery_basics",
        name="Discovery Deep Dive",
        description="Practice asking the right discovery questions to uncover needs",
        target_skills=["discovery", "active_listening"],
        difficulty="beginner",
        buyer_persona="VP of Sales at mid-market SaaS company, open but busy",
        context="First meeting. The buyer responded to an outbound email. They have 15 minutes.",
    ),
    "objection_price": ScenarioConfig(
        scenario_id="objection_price",
        name="Price Objection Battleground",
        description="Handle aggressive price pushback from a skeptical buyer",
        target_skills=["objection_handling", "negotiation"],
        difficulty="intermediate",
        buyer_persona="CFO who's been burned by expensive software before, very price-sensitive",
        context=(
            "Second call. They liked the demo but are pushing "
            "hard on price. Competitor quoted 30% less."
        ),
    ),
    "negotiation_complex": ScenarioConfig(
        scenario_id="negotiation_complex",
        name="Multi-Stakeholder Negotiation",
        description="Navigate complex deal with multiple decision makers",
        target_skills=["negotiation", "closing", "discovery"],
        difficulty="advanced",
        buyer_persona="Procurement lead who needs sign-off from CTO and CFO",
        context="Third call. They want to buy but need to justify to leadership. Budget is tight.",
    ),
    "closing_momentum": ScenarioConfig(
        scenario_id="closing_momentum",
        name="Close the Deal",
        description="Practice closing techniques when buyer is warm but hesitant",
        target_skills=["closing", "objection_handling"],
        difficulty="intermediate",
        buyer_persona="Director of Operations who likes the product but fears change management",
        context="Final call. They've done a trial, results are good. But they keep stalling.",
    ),
    "rapport_cold": ScenarioConfig(
        scenario_id="rapport_cold",
        name="Cold Call Warm-Up",
        description="Build rapport quickly with a cold prospect",
        target_skills=["rapport_building", "discovery"],
        difficulty="beginner",
        buyer_persona="Head of Marketing, wasn't expecting your call, mildly annoyed",
        context="Cold call. You have 60 seconds to earn their attention.",
    ),
}

SKILL_TO_SCENARIOS: dict[str, list[str]] = {
    "discovery": ["discovery_basics", "rapport_cold"],
    "active_listening": ["discovery_basics"],
    "objection_handling": ["objection_price", "closing_momentum"],
    "negotiation": ["objection_price", "negotiation_complex"],
    "closing": ["negotiation_complex", "closing_momentum"],
    "rapport_building": ["rapport_cold"],
}


class GapToGameOrchestrator:
    def __init__(self, evaluation_service: EvaluationService) -> None:
        self._evaluation_service = evaluation_service

    async def assign_training(
        self,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> list[RoleplaySession]:
        with tracer.start_as_current_span(
            "orchestrator.assign_training",
            attributes={"user.id": str(user_id)},
        ):
            gaps = await self._evaluation_service.get_user_skill_gaps(user_id, db)
            if not gaps:
                return []

            scenarios = self._select_scenarios(gaps)
            sessions = []

            for scenario_config in scenarios:
                session = RoleplaySession(
                    user_id=user_id,
                    scenario_id=scenario_config.scenario_id,
                    status="created",
                    current_phase="greeting",
                    target_skills=scenario_config.target_skills,
                    context={
                        "buyer_persona": scenario_config.buyer_persona,
                        "scenario_context": scenario_config.context,
                        "difficulty": scenario_config.difficulty,
                    },
                )
                db.add(session)
                sessions.append(session)

            await db.flush()
            return sessions

    def _select_scenarios(
        self,
        gaps: list[SkillGap],
        max_scenarios: int = 3,
    ) -> list[ScenarioConfig]:
        scored_scenarios: dict[str, float] = {}

        for gap in gaps:
            candidate_ids = SKILL_TO_SCENARIOS.get(gap.skill_name, [])
            severity_weight = {"critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.0}
            weight = severity_weight.get(gap.severity, 1.0)

            for scenario_id in candidate_ids:
                current = scored_scenarios.get(scenario_id, 0.0)
                gap_score = (10.0 - gap.score) * weight
                scored_scenarios[scenario_id] = current + gap_score

        sorted_ids = sorted(scored_scenarios, key=lambda k: scored_scenarios[k], reverse=True)
        selected = []

        for scenario_id in sorted_ids[:max_scenarios]:
            if config := SCENARIO_CATALOG.get(scenario_id):
                selected.append(config)

        return selected

    def get_scenario(self, scenario_id: str) -> ScenarioConfig | None:
        return SCENARIO_CATALOG.get(scenario_id)
