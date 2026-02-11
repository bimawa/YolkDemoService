from unittest.mock import AsyncMock, patch


class TestHealthEndpoint:
    def test_health_returns_ok(self) -> None:
        with (
            patch("yolk.messaging.broker.RabbitBroker", autospec=True),
            patch("yolk.messaging.broker.broker") as mock_broker,
        ):
            mock_broker.start = AsyncMock()
            mock_broker.close = AsyncMock()

            from fastapi.testclient import TestClient

            from yolk.main import app

            client = TestClient(app)
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
