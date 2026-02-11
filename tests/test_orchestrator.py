from unittest.mock import MagicMock

from yolk.models.call import SkillGap
from yolk.services.orchestrator import SCENARIO_CATALOG, GapToGameOrchestrator


class TestGapToGameOrchestrator:
    def _make_gap(
        self,
        skill_name: str,
        score: float,
        severity: str = "medium",
    ) -> SkillGap:
        gap = MagicMock(spec=SkillGap)
        gap.skill_name = skill_name
        gap.score = score
        gap.severity = severity
        return gap

    def test_select_scenarios_prioritizes_worst_gaps(self) -> None:
        eval_service = MagicMock()
        orchestrator = GapToGameOrchestrator(eval_service)

        gaps = [
            self._make_gap("discovery", 2.0, "critical"),
            self._make_gap("closing", 4.0, "high"),
            self._make_gap("rapport_building", 5.5, "medium"),
        ]

        scenarios = orchestrator._select_scenarios(gaps, max_scenarios=2)

        assert len(scenarios) <= 2
        scenario_ids = [s.scenario_id for s in scenarios]
        assert any(sid in scenario_ids for sid in ["discovery_basics", "rapport_cold"])

    def test_select_scenarios_empty_gaps(self) -> None:
        eval_service = MagicMock()
        orchestrator = GapToGameOrchestrator(eval_service)

        scenarios = orchestrator._select_scenarios([], max_scenarios=3)
        assert scenarios == []

    def test_select_scenarios_max_limit(self) -> None:
        eval_service = MagicMock()
        orchestrator = GapToGameOrchestrator(eval_service)

        gaps = [
            self._make_gap("discovery", 1.0, "critical"),
            self._make_gap("objection_handling", 2.0, "critical"),
            self._make_gap("negotiation", 2.5, "critical"),
            self._make_gap("closing", 3.0, "high"),
            self._make_gap("rapport_building", 3.5, "high"),
        ]

        scenarios = orchestrator._select_scenarios(gaps, max_scenarios=3)
        assert len(scenarios) <= 3

    def test_get_scenario(self) -> None:
        eval_service = MagicMock()
        orchestrator = GapToGameOrchestrator(eval_service)

        scenario = orchestrator.get_scenario("discovery_basics")
        assert scenario is not None
        assert scenario.scenario_id == "discovery_basics"
        assert "discovery" in scenario.target_skills

    def test_get_scenario_not_found(self) -> None:
        eval_service = MagicMock()
        orchestrator = GapToGameOrchestrator(eval_service)

        assert orchestrator.get_scenario("nonexistent") is None

    def test_scenario_catalog_completeness(self) -> None:
        assert len(SCENARIO_CATALOG) >= 5
        for scenario in SCENARIO_CATALOG.values():
            assert scenario.scenario_id
            assert scenario.name
            assert scenario.target_skills
            assert scenario.buyer_persona
            assert scenario.context
