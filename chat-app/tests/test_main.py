from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
headers = {"X-API-Key": "my-secret-key"}
def test_authentication():
    response = client.post("/sessions")
    assert response.status_code == 422
    response = client.post(
        "/sessions",
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401
def test_create_session():
    response = client.post("/sessions", headers=headers)
    assert response.status_code == 200
    assert "session_id" in response.json()
def test_session_isolation():
    first = client.post("/sessions", headers=headers).json()
    second = client.post("/sessions", headers=headers).json()
    first_id = first["session_id"]
    second_id = second["session_id"]
    response = client.get(
        f"/sessions/{first_id}/messages",
        headers=headers
    )
    assert response.status_code == 200
    response = client.get(
        f"/sessions/{second_id}/messages",
        headers=headers
    )
    assert response.status_code == 200
def test_delete_session():
    session = client.post(
        "/sessions",
        headers=headers
    ).json()
    response = client.delete(
        f"/sessions/{session['session_id']}",
        headers=headers
    )
    assert response.status_code == 200
    