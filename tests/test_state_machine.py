import pytest

from yolk.core.state_machine import (
    ConversationStateMachine,
    InvalidTransitionError,
    Phase,
)


class TestConversationStateMachine:
    def test_initial_state(self) -> None:
        sm = ConversationStateMachine()
        assert sm.current_phase == Phase.GREETING
        assert sm.turn_count == 0
        assert not sm.is_terminal

    def test_valid_transition(self) -> None:
        sm = ConversationStateMachine()
        assert sm.can_transition_to(Phase.DISCOVERY)
        assert not sm.can_transition_to(Phase.CLOSING)

    @pytest.mark.asyncio
    async def test_transition_updates_phase(self) -> None:
        sm = ConversationStateMachine()
        await sm.transition_to(Phase.DISCOVERY)
        assert sm.current_phase == Phase.DISCOVERY

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self) -> None:
        sm = ConversationStateMachine()
        with pytest.raises(InvalidTransitionError):
            await sm.transition_to(Phase.CLOSING)

    def test_record_turn(self) -> None:
        sm = ConversationStateMachine()
        sm.record_turn()
        assert sm.turn_count == 1
        assert sm.phase_turn_counts[Phase.GREETING] == 1

    def test_should_suggest_transition(self) -> None:
        sm = ConversationStateMachine()
        assert sm.should_suggest_transition(max_turns_per_phase=2) is None
        sm.record_turn()
        sm.record_turn()
        suggested = sm.should_suggest_transition(max_turns_per_phase=2)
        assert suggested == Phase.DISCOVERY

    @pytest.mark.asyncio
    async def test_full_conversation_flow(self) -> None:
        sm = ConversationStateMachine()

        await sm.transition_to(Phase.DISCOVERY)
        await sm.transition_to(Phase.QUALIFICATION)
        await sm.transition_to(Phase.OBJECTION_HANDLING)
        await sm.transition_to(Phase.NEGOTIATION)
        await sm.transition_to(Phase.CLOSING)
        await sm.transition_to(Phase.WRAP_UP)

        assert sm.is_terminal
        assert sm.allowed_transitions == []

    def test_serialization_roundtrip(self) -> None:
        sm = ConversationStateMachine()
        sm.record_turn()
        sm.record_turn()

        data = sm.to_dict()
        restored = ConversationStateMachine.from_dict(data)

        assert restored.current_phase == sm.current_phase
        assert restored.turn_count == sm.turn_count

    @pytest.mark.asyncio
    async def test_transition_callback(self) -> None:
        transitions: list[tuple[Phase, Phase]] = []

        async def on_transition(from_phase: Phase, to_phase: Phase) -> None:
            transitions.append((from_phase, to_phase))

        sm = ConversationStateMachine()
        sm.on_transition(on_transition)

        await sm.transition_to(Phase.DISCOVERY)

        assert len(transitions) == 1
        assert transitions[0] == (Phase.GREETING, Phase.DISCOVERY)
