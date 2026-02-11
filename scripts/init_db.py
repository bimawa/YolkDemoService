import asyncio

from yolk.database import Base, engine
from yolk.models.call import CallEvaluation, SalesCall, SkillGap  # noqa: F401
from yolk.models.session import RoleplayMessage, RoleplaySession  # noqa: F401
from yolk.models.user import User  # noqa: F401


async def init() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init())
