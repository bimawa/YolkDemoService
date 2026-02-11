from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from yolk.database import async_session_factory
from yolk.services.llm import LLMClient

_llm_client: LLMClient | None = None


def get_llm_client_instance() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


async def get_session_db() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_llm_client() -> LLMClient:
    return get_llm_client_instance()
