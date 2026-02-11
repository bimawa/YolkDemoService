import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from yolk.api.deps import get_llm_client_instance
from yolk.api.routes import calls, sessions, users
from yolk.api.websocket.roleplay import router as ws_router
from yolk.config import settings
from yolk.core.tracing import instrument_app, setup_tracing
from yolk.database import engine
from yolk.messaging.broker import broker

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("starting_up", app=settings.app_name)

    if settings.otlp_enabled:
        setup_tracing()

    try:
        await broker.start()
        logger.info("rabbitmq_connected")
    except Exception:
        logger.warning("rabbitmq_unavailable")

    yield

    llm_client = get_llm_client_instance()
    await llm_client.close()

    with contextlib.suppress(Exception):
        await broker.stop()

    await engine.dispose()
    logger.info("shutdown_complete")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.otlp_enabled:
    instrument_app(app)

app.include_router(users.router, prefix="/api/v1")
app.include_router(calls.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(ws_router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": settings.app_name}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", path=request.url.path, method=request.method)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
