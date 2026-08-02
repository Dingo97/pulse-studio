from fastapi.testclient import TestClient

from app.main import app


def test_cross_origin_write_is_rejected() -> None:
    with TestClient(app) as client:
        response = client.delete(
            "/api/projects/00000000000000000000000000000000",
            headers={"Origin": "https://evil.example"},
        )
    assert response.status_code == 403


def test_untrusted_host_is_rejected() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health", headers={"Host": "evil.example"})
    assert response.status_code == 400
