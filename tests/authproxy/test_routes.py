import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def test_index_page_returns_200(client):
    res = client.get("/authproxy/")
    assert res.status_code == 200
    assert b"authproxy/style.css" in res.data
    assert b"authproxy/script.js" in res.data


def test_hub_links_to_authproxy_module(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b'href="/authproxy/"' in res.data


def test_api_presets_lists_all_presets(client):
    res = client.get("/authproxy/api/presets")
    assert res.status_code == 200
    presets = res.get_json()["presets"]
    assert "github-org" in presets
    assert "homelab-simple" in presets


def test_api_presets_filtered_by_engine(client):
    res = client.get("/authproxy/api/presets?engine=authelia")
    assert res.status_code == 200
    presets = res.get_json()["presets"]
    assert "homelab-simple" in presets
    assert "github-org" not in presets


def test_api_presets_unknown_engine_returns_400(client):
    res = client.get("/authproxy/api/presets?engine=keycloak-direct")
    assert res.status_code == 400


def test_api_preset_valid_name(client):
    res = client.get("/authproxy/api/preset/github-org")
    assert res.status_code == 200
    data = res.get_json()
    assert data["engine"] == "oauth2-proxy"
    assert data["provider"] == "github"


def test_api_preset_unknown_name_returns_404(client):
    res = client.get("/authproxy/api/preset/ce-preset-nexiste-pas")
    assert res.status_code == 404


def test_api_generate_oauth2_returns_config(client):
    payload = {
        "preset": "custom",
        "engine": "oauth2-proxy",
        "provider": "github",
        "upstream": "http://127.0.0.1:3000",
        "redirect_url": "https://auth.exemple.com/oauth2/callback",
        "client_id": "id",
        "client_secret": "secret",
        "github_org": "monorg",
    }
    res = client.post("/authproxy/api/generate", json=payload)
    assert res.status_code == 200
    filenames = {f["filename"] for f in res.get_json()["files"]}
    assert filenames == {"oauth2-proxy.cfg", "nginx-auth-snippet.conf"}


def test_api_generate_authelia_returns_config(client):
    preset = client.get("/authproxy/api/preset/homelab-simple").get_json()
    res = client.post("/authproxy/api/generate", json=preset)
    assert res.status_code == 200
    filenames = {f["filename"] for f in res.get_json()["files"]}
    assert filenames == {"configuration.yml", "users_database.yml"}


def test_api_generate_invalid_config_returns_400(client):
    res = client.post("/authproxy/api/generate", json={"preset": "custom", "engine": "authelia", "users": []})
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_api_generate_empty_body_returns_400(client):
    res = client.post("/authproxy/api/generate", json={})
    assert res.status_code == 400
