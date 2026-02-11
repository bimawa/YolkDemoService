import uuid
from enum import StrEnum
from typing import Any

from yolk.schemas.common import IDTimestampSchema, StrictSchema


class SessionStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class ConversationPhase(StrEnum):
    GREETING = "greeting"
    DISCOVERY = "discovery"
    QUALIFICATION = "qualification"
    OBJECTION_HANDLING = "objection_handling"
    NEGOTIATION = "negotiation"
    CLOSING = "closing"
    WRAP_UP = "wrap_up"


class SessionCreate(StrictSchema):
    user_id: uuid.UUID
    scenario_id: str
    target_skills: list[str] = []  # noqa: RUF012


class SessionResponse(IDTimestampSchema):
    user_id: uuid.UUID
    scenario_id: str
    status: str
    current_phase: str
    turn_count: int
    target_skills: list[str]
    evaluation_summary: dict[str, Any] | None


class MessageResponse(IDTimestampSchema):
    session_id: uuid.UUID
    role: str
    content: str
    phase: str
    sequence_number: int


class WebSocketMessage(StrictSchema):
    type: str
    content: str | None = None
    session_id: uuid.UUID | None = None
    metadata: dict[str, Any] | None = None


class WebSocketResponse(StrictSchema):
    type: str
    content: str | None = None
    phase: str | None = None
    session_id: uuid.UUID | None = None
    turn_number: int | None = None
    is_final: bool = False
    error: str | None = None
