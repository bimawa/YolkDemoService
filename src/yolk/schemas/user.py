import uuid

from pydantic import EmailStr

from yolk.schemas.common import IDTimestampSchema, StrictSchema


class UserCreate(StrictSchema):
    email: EmailStr
    full_name: str
    role: str = "sales_rep"


class UserUpdate(StrictSchema):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserResponse(IDTimestampSchema):
    email: str
    full_name: str
    role: str
    is_active: bool


class UserBrief(StrictSchema):
    id: uuid.UUID
    full_name: str
    email: str
