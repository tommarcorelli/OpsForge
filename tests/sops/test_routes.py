import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def test_index_page_returns_200(client):
    res = client.get("/sops/")
    assert res.status_code == 200
    assert b"sops/style.css" in res.data
    assert b"sops/script.js" in res.data


def test_hub_links_to_sops_module(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b'href="/sops/"' in res.data


def test_api_presets_lists_all_presets(client):
    res = client.get("/sops/api/presets")
    assert res.status_code == 200
    presets = res.get_json()["presets"]
    assert "solo-dev" in presets
    assert "k8s-secrets" in presets


def test_api_preset_valid_name(client):
    res = client.get("/sops/api/preset/multi-env")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["rules"]) == 3


def test_api_preset_unknown_name_returns_404(client):
    res = client.get("/sops/api/preset/ce-preset-nexiste-pas")
    assert res.status_code == 404


def test_api_generate_returns_two_files(client):
    payload = {
        "preset": "custom",
        "rules": [{"path_regex": "secrets/.*\\.yaml$", "age_recipients": ["age1" + "a" * 40]}],
    }
    res = client.post("/sops/api/generate", json=payload)
    assert res.status_code == 200
    filenames = {f["filename"] for f in res.get_json()["files"]}
    assert filenames == {".sops.yaml", "sops-diff.gitattributes"}


def test_api_generate_invalid_config_returns_400(client):
    res = client.post("/sops/api/generate", json={"preset": "custom", "rules": []})
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_api_generate_empty_body_returns_400(client):
    res = client.post("/sops/api/generate", json={})
    assert res.status_code == 400
