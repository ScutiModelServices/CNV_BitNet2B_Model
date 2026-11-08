import pytest


def test_missing_weights_keep_admin_available_then_download_makes_ready():
    from fastapi.testclient import TestClient
    from app import create_app
    from conftest import make_engine, FakeLoaded

    downloaded = []

    def loader(source):
        if not downloaded:
            raise OSError("not downloaded /private/cache")
        return FakeLoaded(source)

    model = make_engine(loader=loader, cached_sha=lambda repo: "revision" if downloaded else None,
                        remote_sha=lambda repo: "revision", download=lambda repo: downloaded.append(repo))
    with TestClient(create_app(model, "admin", warm=True)) as client:
        assert client.get("/health").json()["ready"] is False
        assert client.get("/admin/").status_code == 200
        client.headers["X-Internal-Token"] = client.post("/admin/tokens", json={"name": "test"}, headers={"X-Internal-Token": "admin"}).json()["token"]
        response = client.post("/v1/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        assert response.status_code == 503
        assert "Download" in response.json()["detail"]
        assert "/private" not in response.text
        assert downloaded == []
        assert client.post("/admin/updates/check", headers={"X-Internal-Token": "admin"}).json()["weights"][0]["update"]
        assert downloaded == []
        assert client.post("/admin/updates/weights", headers={"X-Internal-Token": "admin"}).status_code == 200
        assert client.post("/v1/chat", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 200
        assert client.get("/health").json()["ready"] is True
