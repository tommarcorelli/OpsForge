import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def test_index_page_returns_200(client):
    res = client.get("/precommit/")
    assert res.status_code == 200
    assert b"precommit/style.css" in res.data
    assert b"precommit/script.js" in res.data


def test_api_presets_lists_all_presets(client):
    res = client.get("/precommit/api/presets")
    assert res.status_code == 200
    assert "python" in res.get_json()["presets"]


def test_api_preset_valid_name(client):
    res = client.get("/precommit/api/preset/python")
    assert res.status_code == 200
    data = res.get_json()
    assert data["backend"] == "pre-commit"
    assert "black" in data["hooks"]


def test_api_preset_unknown_name_returns_404(client):
    res = client.get("/precommit/api/preset/ce-preset-nexiste-pas")
    assert res.status_code == 404


def test_api_generate_valid_config_returns_files(client):
    payload = {"preset": "python", "backend": "pre-commit"}
    res = client.post("/precommit/api/generate", json=payload)
    assert res.status_code == 200
    filenames = {f["filename"] for f in res.get_json()["files"]}
    assert filenames == {".pre-commit-config.yaml"}


def test_api_generate_husky_backend(client):
    payload = {"preset": "javascript", "backend": "husky"}
    res = client.post("/precommit/api/generate", json=payload)
    assert res.status_code == 200
    filenames = {f["filename"] for f in res.get_json()["files"]}
    assert filenames == {".husky/pre-commit", "lint-staged.config.json"}


def test_api_generate_invalid_config_returns_400(client):
    payload = {"preset": "custom", "backend": "pre-commit", "hooks": []}
    res = client.post("/precommit/api/generate", json=payload)
    assert res.status_code == 400


def test_api_generate_empty_body_returns_400(client):
    res = client.post("/precommit/api/generate", json={})
    assert res.status_code == 400
