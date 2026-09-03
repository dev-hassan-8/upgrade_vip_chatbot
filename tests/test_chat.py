import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("message", ["", "   "])
def test_chat_empty_message(client: TestClient, message: str) -> None:
    response = client.post("/chat", json={"message": message})
    assert response.status_code == 400
    assert response.json()["detail"] == "Message cannot be empty."
