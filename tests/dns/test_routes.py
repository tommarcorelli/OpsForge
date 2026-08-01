import json

import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def test_index_page_returns_200(client):
    res = client.get("/dns/")
    assert res.status_code == 200
    assert b"dns/style.css" in res.data
    assert b"dns/script.js" in res.data


def test_hub_links_to_dns_module(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b'href="/dns/"' in res.data


def test_api_presets_lists_all_presets(client):
    res = client.get("/dns/api/presets")
    assert res.status_code == 200
    presets = res.get_json()["presets"]
    assert "site-statique" in presets
    assert "sous-domaines-services" in presets


def test_api_preset_valid_name(client):
    res = client.get("/dns/api/preset/site-statique")
    assert res.status_code == 200
    data = res.get_json()
    assert data["engine"] == "bind"
    assert data["domain"] == "exemple.com"


def test_api_preset_engine_override(client):
    res = client.get("/dns/api/preset/site-statique?engine=route53")
    assert res.status_code == 200
    assert res.get_json()["engine"] == "route53"


def test_api_preset_unknown_name_returns_404(client):
    res = client.get("/dns/api/preset/ce-preset-nexiste-pas")
    assert res.status_code == 404


def test_api_generate_bind_returns_zone_file(client):
    preset = client.get("/dns/api/preset/site-statique").get_json()
    res = client.post("/dns/api/generate", json=preset)
    assert res.status_code == 200
    filenames = {f["filename"] for f in res.get_json()["files"]}
    assert filenames == {"exemple.com.zone"}


def test_api_generate_route53_returns_json_file(client):
    preset = client.get("/dns/api/preset/site-statique?engine=route53").get_json()
    res = client.post("/dns/api/generate", json=preset)
    assert res.status_code == 200
    files = res.get_json()["files"]
    assert files[0]["filename"] == "exemple.com.route53.json"
    json.loads(files[0]["content"])


def test_api_generate_invalid_config_returns_400(client):
    res = client.post("/dns/api/generate", json={"preset": "custom", "domain": "x.com", "records": []})
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_api_generate_empty_body_returns_400(client):
    res = client.post("/dns/api/generate", json={})
    assert res.status_code == 400
