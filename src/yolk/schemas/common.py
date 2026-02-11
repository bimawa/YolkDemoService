import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StrictSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IDTimestampSchema(StrictSchema):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
