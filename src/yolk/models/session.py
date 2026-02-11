import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from yolk.models.base import BaseModel


class RoleplaySession(BaseModel):
    __tablename__ = "roleplay_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    scenario_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="created")
    current_phase: Mapped[str] = mapped_column(String(50), default="greeting")
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evaluation_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    target_skills: Mapped[list[str]] = mapped_column(JSONB, default=list)

    user: Mapped["User"] = relationship(back_populates="roleplay_sessions")
    messages: Mapped[list["RoleplayMessage"]] = relationship(
        back_populates="session", lazy="selectin", order_by="RoleplayMessage.sequence_number"
    )


class RoleplayMessage(BaseModel):
    __tablename__ = "roleplay_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roleplay_sessions.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(String(50))
    sequence_number: Mapped[int] = mapped_column(Integer)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    session: Mapped["RoleplaySession"] = relationship(back_populates="messages")


from yolk.models.user import User  # noqa: E402

__all__ = ["RoleplayMessage", "RoleplaySession", "User"]
