from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from yolk.core.state_machine import Phase
from yolk.services.llm import LLMResponse


def _make_db_session_row(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    scenario_id: str = "discovery_basics",
) -> MagicMock:
    row = MagicMock()
    row.id = session_id
    row.user_id = user_id
    row.scenario_id = scenario_id
    row.status = "created"
    row.context = {}
    row.current_phase = "greeting"
    row.turn_count = 0
    row.target_skills = ["discovery"]
    return row


class TestWebSocketRoleplay:
    @pytest.fixture()
    def _mock_app(self) -> TestClient:
        with (
            patch("yolk.messaging.broker.RabbitBroker", autospec=True),
            patch("yolk.messaging.broker.broker") as mock_broker,
        ):
            mock_broker.start = AsyncMock()
            mock_broker.close = AsyncMock()

            from yolk.main import app

            return TestClient(app)

    def test_websocket_session_started(self, _mock_app: TestClient) -> None:
        session_id = uuid.uuid4()
        user_id = uuid.uuid4()
        db_row = _make_db_session_row(session_id, user_id)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=db_row)
        mock_db.flush = AsyncMock()

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(
            return_value=LLMResponse(
                content="Hello, how can I help you today?",
                model="mock",
                usage={},
            )
        )

        async def fake_get_db():
            yield mock_db

        async def fake_get_llm() -> MagicMock:
            return mock_llm

        from yolk.main import app

        app.dependency_overrides[
            __import__("yolk.api.deps", fromlist=["get_session_db"]).get_session_db
        ] = fake_get_db
        app.dependency_overrides[
            __import__("yolk.api.deps", fromlist=["get_llm_client"]).get_llm_client
        ] = fake_get_llm

        try:
            with _mock_app.websocket_connect(f"/api/v1/ws/roleplay/{session_id}") as ws:
                data = ws.receive_json()
                assert data["type"] == "session_started"
                assert data["session_id"] == str(session_id)
                assert data["phase"] == Phase.GREETING

                ws.send_json({"type": "message", "content": "Hi, I'm from Acme Corp"})

                typing_msg = ws.receive_json()
                while typing_msg.get("type") == "heartbeat":
                    typing_msg = ws.receive_json()
                assert typing_msg["type"] == "typing"
                assert typing_msg["is_typing"] is True

                ai_msg = ws.receive_json()
                while ai_msg.get("type") == "heartbeat":
                    ai_msg = ws.receive_json()
                assert ai_msg["type"] == "message"
                assert ai_msg["content"] == "Hello, how can I help you today?"
                assert "phase" in ai_msg
                assert "turn_number" in ai_msg

                ws.send_json({"type": "end_session"})
                end_msg = ws.receive_json()
                while end_msg.get("type") == "heartbeat":
                    end_msg = ws.receive_json()
                assert end_msg["type"] == "session_ended"
                assert "evaluation_summary" in end_msg

        finally:
            app.dependency_overrides.clear()

    def test_websocket_ping_pong(self, _mock_app: TestClient) -> None:
        session_id = uuid.uuid4()
        user_id = uuid.uuid4()
        db_row = _make_db_session_row(session_id, user_id)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=db_row)
        mock_db.flush = AsyncMock()

        mock_llm = MagicMock()

        async def fake_get_db():
            yield mock_db

        async def fake_get_llm() -> MagicMock:
            return mock_llm

        from yolk.main import app

        app.dependency_overrides[
            __import__("yolk.api.deps", fromlist=["get_session_db"]).get_session_db
        ] = fake_get_db
        app.dependency_overrides[
            __import__("yolk.api.deps", fromlist=["get_llm_client"]).get_llm_client
        ] = fake_get_llm

        try:
            with _mock_app.websocket_connect(f"/api/v1/ws/roleplay/{session_id}") as ws:
                started = ws.receive_json()
                assert started["type"] == "session_started"

                ws.send_json({"type": "ping"})
                pong = ws.receive_json()
                while pong.get("type") == "heartbeat":
                    pong = ws.receive_json()
                assert pong["type"] == "pong"

                ws.send_json({"type": "end_session"})
                end_msg = ws.receive_json()
                while end_msg.get("type") == "heartbeat":
                    end_msg = ws.receive_json()
                assert end_msg["type"] == "session_ended"
        finally:
            app.dependency_overrides.clear()
