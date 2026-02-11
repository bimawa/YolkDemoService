import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from yolk.models.base import BaseModel


class SalesCall(BaseModel):
    __tablename__ = "sales_calls"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    user: Mapped["User"] = relationship(back_populates="calls")
    evaluation: Mapped["CallEvaluation | None"] = relationship(
        back_populates="call", uselist=False, lazy="selectin"
    )


class CallEvaluation(BaseModel):
    __tablename__ = "call_evaluations"

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sales_calls.id"), unique=True
    )

    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    rubric_results: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    skill_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    strengths: Mapped[list[str]] = mapped_column(JSONB, default=list)
    weaknesses: Mapped[list[str]] = mapped_column(JSONB, default=list)
    recommended_scenarios: Mapped[list[str]] = mapped_column(JSONB, default=list)

    call: Mapped["SalesCall"] = relationship(back_populates="evaluation")
    skill_gaps: Mapped[list["SkillGap"]] = relationship(
        back_populates="evaluation", lazy="selectin"
    )


class SkillGap(BaseModel):
    __tablename__ = "skill_gaps"

    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_evaluations.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )

    skill_name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_resolved: Mapped[bool] = mapped_column(default=False)

    evaluation: Mapped["CallEvaluation"] = relationship(back_populates="skill_gaps")


from yolk.models.user import User  # noqa: E402

__all__ = ["CallEvaluation", "SalesCall", "SkillGap", "User"]
