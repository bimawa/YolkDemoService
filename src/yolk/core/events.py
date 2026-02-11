from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    CALL_UPLOADED = "call.uploaded"
    CALL_EVALUATION_STARTED = "call.evaluation.started"
    CALL_EVALUATION_COMPLETED = "call.evaluation.completed"
    CALL_EVALUATION_FAILED = "call.evaluation.failed"
    SKILL_GAP_DETECTED = "skill_gap.detected"
    ROLEPLAY_ASSIGNED = "roleplay.assigned"
    ROLEPLAY_STARTED = "roleplay.started"
    ROLEPLAY_COMPLETED = "roleplay.completed"
    ROLEPLAY_PHASE_CHANGED = "roleplay.phase.changed"


@dataclass(frozen=True)
class Event:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
