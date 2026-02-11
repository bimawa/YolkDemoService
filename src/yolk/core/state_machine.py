from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Phase(StrEnum):
    GREETING = "greeting"
    DISCOVERY = "discovery"
    QUALIFICATION = "qualification"
    OBJECTION_HANDLING = "objection_handling"
    NEGOTIATION = "negotiation"
    CLOSING = "closing"
    WRAP_UP = "wrap_up"


PHASE_TRANSITIONS: dict[Phase, list[Phase]] = {
    Phase.GREETING: [Phase.DISCOVERY],
    Phase.DISCOVERY: [Phase.QUALIFICATION, Phase.OBJECTION_HANDLING],
    Phase.QUALIFICATION: [Phase.OBJECTION_HANDLING, Phase.NEGOTIATION],
    Phase.OBJECTION_HANDLING: [Phase.NEGOTIATION, Phase.QUALIFICATION],
    Phase.NEGOTIATION: [Phase.CLOSING, Phase.OBJECTION_HANDLING],
    Phase.CLOSING: [Phase.WRAP_UP, Phase.NEGOTIATION],
    Phase.WRAP_UP: [],
}

PHASE_PROMPTS: dict[Phase, str] = {
    Phase.GREETING: (
        "You are a potential buyer. Start with a professional greeting. "
        "Be slightly skeptical but open to hearing the pitch. "
        "Mention you're busy and have 15 minutes."
    ),
    Phase.DISCOVERY: (
        "The sales rep should be asking discovery questions. "
        "Answer questions about your business needs, but don't volunteer too much. "
        "If they don't ask about budget or timeline, don't mention it."
    ),
    Phase.QUALIFICATION: (
        "Provide some qualifying information when asked. "
        "You have a budget of $50k-100k, timeline of Q2. "
        "You're evaluating 2 other vendors. Drop hints but make them work for details."
    ),
    Phase.OBJECTION_HANDLING: (
        "Raise an objection: 'We tried something similar before and it didn't work.' "
        "Or: 'Your competitor offers this for 30% less.' "
        "Test how the rep handles pushback. Be firm but fair."
    ),
    Phase.NEGOTIATION: (
        "You're interested but need a better deal. "
        "Push on price, ask for additional features or support. "
        "Mention your other vendor options as leverage."
    ),
    Phase.CLOSING: (
        "If the rep has addressed your concerns well, be open to moving forward. "
        "Ask about next steps, contract terms, implementation timeline. "
        "If they haven't earned the close, stall: 'I need to think about it.'"
    ),
    Phase.WRAP_UP: (
        "The conversation is ending. Summarize your impression. "
        "Give a clear signal: either you'll move forward, need more time, or pass."
    ),
}


TransitionCallback = Callable[[Phase, Phase], Awaitable[None]]


@dataclass
class ConversationStateMachine:
    current_phase: Phase = Phase.GREETING
    turn_count: int = 0
    phase_turn_counts: dict[Phase, int] = field(default_factory=dict)
    _on_transition_callbacks: list[TransitionCallback] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def on_transition(self, callback: TransitionCallback) -> None:
        self._on_transition_callbacks.append(callback)

    @property
    def allowed_transitions(self) -> list[Phase]:
        return PHASE_TRANSITIONS.get(self.current_phase, [])

    @property
    def current_prompt(self) -> str:
        return PHASE_PROMPTS[self.current_phase]

    @property
    def is_terminal(self) -> bool:
        return self.current_phase == Phase.WRAP_UP

    def can_transition_to(self, target: Phase) -> bool:
        return target in self.allowed_transitions

    async def transition_to(self, target: Phase) -> None:
        async with self._lock:
            if not self.can_transition_to(target):
                allowed = ", ".join(self.allowed_transitions)
                msg = (
                    f"Cannot transition from {self.current_phase} to {target}. Allowed: [{allowed}]"
                )
                raise InvalidTransitionError(msg)

            previous = self.current_phase
            self.current_phase = target
            self.phase_turn_counts[target] = self.phase_turn_counts.get(target, 0)

            for callback in self._on_transition_callbacks:
                await callback(previous, target)

    def record_turn(self) -> None:
        self.turn_count += 1
        current_count = self.phase_turn_counts.get(self.current_phase, 0)
        self.phase_turn_counts[self.current_phase] = current_count + 1

    def should_suggest_transition(self, max_turns_per_phase: int = 4) -> Phase | None:
        current_turns = self.phase_turn_counts.get(self.current_phase, 0)
        if current_turns < max_turns_per_phase:
            return None
        transitions = self.allowed_transitions
        if transitions:
            return transitions[0]
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_phase": self.current_phase,
            "turn_count": self.turn_count,
            "phase_turn_counts": {str(k): v for k, v in self.phase_turn_counts.items()},
            "allowed_transitions": [str(t) for t in self.allowed_transitions],
            "is_terminal": self.is_terminal,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationStateMachine:
        return cls(
            current_phase=Phase(data["current_phase"]),
            turn_count=data["turn_count"],
            phase_turn_counts={Phase(k): v for k, v in data["phase_turn_counts"].items()},
        )


class InvalidTransitionError(Exception):
    pass
