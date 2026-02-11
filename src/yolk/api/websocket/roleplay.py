import asyncio
import contextlib
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from yolk.api.deps import get_llm_client, get_session_db
from yolk.services.llm import LLMClient
from yolk.services.roleplay import RoleplayError, RoleplayService

logger = structlog.get_logger()
router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            if existing := self._connections.get(session_id):
                with contextlib.suppress(Exception):
                    await existing.close(code=4001, reason="Replaced by new connection")
            self._connections[session_id] = websocket

    async def disconnect(self, session_id: uuid.UUID) -> None:
        async with self._lock:
            self._connections.pop(session_id, None)

    async def send_json(self, session_id: uuid.UUID, data: dict[str, Any]) -> None:
        if ws := self._connections.get(session_id):
            try:
                await ws.send_json(data)
            except Exception:
                await self.disconnect(session_id)

    @property
    def active_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


@router.websocket("/ws/roleplay/{session_id}")
async def roleplay_websocket(
    websocket: WebSocket,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session_db),
    llm_client: LLMClient = Depends(get_llm_client),
) -> None:
    service = RoleplayService(llm_client)

    await manager.connect(session_id, websocket)
    logger.info("websocket_connected", session_id=str(session_id))

    try:
        active = await service.start_session(session_id, db)

        await websocket.send_json(
            {
                "type": "session_started",
                "session_id": str(session_id),
                "phase": active.state_machine.current_phase,
            }
        )

        heartbeat_task = asyncio.create_task(_heartbeat(websocket))

        try:
            while True:
                raw = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=300.0,
                )

                msg_type = raw.get("type", "message")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                if msg_type == "end_session":
                    summary = await service.end_session(session_id, db)
                    await websocket.send_json(
                        {
                            "type": "session_ended",
                            "evaluation_summary": summary,
                        }
                    )
                    break

                if msg_type == "message":
                    content = raw.get("content", "")
                    if not content:
                        continue

                    await websocket.send_json({"type": "typing", "is_typing": True})

                    ai_response = await service.process_message(session_id, content, db)
                    current = service.get_active_session(session_id)

                    await websocket.send_json(
                        {
                            "type": "message",
                            "content": ai_response,
                            "phase": current.state_machine.current_phase if current else "unknown",
                            "turn_number": current.state_machine.turn_count if current else 0,
                            "is_final": current.state_machine.is_terminal if current else False,
                        }
                    )

                    if current and current.state_machine.is_terminal:
                        summary = await service.end_session(session_id, db)
                        await websocket.send_json(
                            {
                                "type": "session_ended",
                                "evaluation_summary": summary,
                            }
                        )
                        break

        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    except WebSocketDisconnect:
        logger.info("websocket_disconnected", session_id=str(session_id))
    except RoleplayError as e:
        await websocket.send_json({"type": "error", "error": str(e)})
    except TimeoutError:
        await websocket.send_json({"type": "error", "error": "Session timed out"})
    except Exception:
        logger.exception("websocket_error", session_id=str(session_id))
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "error": "Internal server error"})
    finally:
        await manager.disconnect(session_id)
        logger.info("websocket_cleanup", session_id=str(session_id))


async def _heartbeat(websocket: WebSocket, interval: int = 30) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await websocket.send_json({"type": "heartbeat"})
        except Exception:
            break
