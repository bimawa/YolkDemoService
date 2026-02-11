from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from yolk.models.base import BaseModel


class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="sales_rep")
    is_active: Mapped[bool] = mapped_column(default=True)

    calls: Mapped[list["SalesCall"]] = relationship(back_populates="user", lazy="selectin")
    roleplay_sessions: Mapped[list["RoleplaySession"]] = relationship(
        back_populates="user", lazy="selectin"
    )


from yolk.models.call import SalesCall  # noqa: E402
from yolk.models.session import RoleplaySession  # noqa: E402

__all__ = ["RoleplaySession", "SalesCall", "User"]
