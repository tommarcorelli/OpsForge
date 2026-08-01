import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def test_index_page_returns_200(client):
    res = client.get("/logging/")
    assert res.status_code == 200
    assert b"logging/style.css" in res.data
    assert b"logging/script.js" in res.data


def test_api_presets_lists_all_presets(client):
    res = client.get("/logging/api/presets")
    assert res.status_code == 200
    data = res.get_json()
    assert "docker-loki" in data["presets"]


def test_api_preset_valid_name(client):
    res = client.get("/logging/api/preset/nginx-loki")
    assert res.status_code == 200
    data = res.get_json()
    assert data["backend"] == "fluent-bit"
    assert len(data["sources"]) == 1


def test_api_preset_unknown_name_returns_404(client):
    res = client.get("/logging/api/preset/ce-preset-nexiste-pas")
    assert res.status_code == 404


def test_api_generate_valid_config_returns_files(client):
    payload = {"preset": "docker-loki", "backend": "fluent-bit"}
    res = client.post("/logging/api/generate", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    filenames = {f["filename"] for f in data["files"]}
    assert filenames == {"fluent-bit.conf"}


def test_api_generate_vector_backend(client):
    payload = {"preset": "app-json-loki", "backend": "vector"}
    res = client.post("/logging/api/generate", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    filenames = {f["filename"] for f in data["files"]}
    assert filenames == {"vector.toml"}


def test_api_generate_invalid_config_returns_400(client):
    payload = {"preset": "custom", "backend": "fluent-bit", "sources": []}
    res = client.post("/logging/api/generate", json=payload)
    assert res.status_code == 400


def test_api_generate_empty_body_returns_400(client):
    res = client.post("/logging/api/generate", json={})
    assert res.status_code == 400
