import uuid
from enum import StrEnum

from yolk.schemas.common import IDTimestampSchema, StrictSchema


class CallStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    EVALUATED = "evaluated"
    FAILED = "failed"


class GapSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CallCreate(StrictSchema):
    user_id: uuid.UUID
    title: str
    transcript: str | None = None
    duration_seconds: int | None = None
    source_url: str | None = None


class CallResponse(IDTimestampSchema):
    user_id: uuid.UUID
    title: str
    transcript: str | None
    duration_seconds: int | None
    status: str
    source_url: str | None


class RubricItem(StrictSchema):
    question: str
    answer: bool
    confidence: float
    evidence: str


class SkillScoreItem(StrictSchema):
    skill_name: str
    category: str
    score: float
    max_score: float = 10.0
    feedback: str


class EvaluationResponse(IDTimestampSchema):
    call_id: uuid.UUID
    overall_score: float
    rubric_results: dict[str, RubricItem]
    skill_scores: dict[str, SkillScoreItem]
    strengths: list[str]
    weaknesses: list[str]
    recommended_scenarios: list[str]


class SkillGapResponse(IDTimestampSchema):
    evaluation_id: uuid.UUID
    user_id: uuid.UUID
    skill_name: str
    category: str
    severity: str
    score: float
    description: str | None
    is_resolved: bool
