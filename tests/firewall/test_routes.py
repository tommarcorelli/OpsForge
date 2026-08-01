import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def test_index_page_returns_200(client):
    res = client.get("/firewall/")
    assert res.status_code == 200
    assert b"firewall/style.css" in res.data
    assert b"firewall/script.js" in res.data


def test_api_presets_lists_all_presets(client):
    res = client.get("/firewall/api/presets")
    assert res.status_code == 200
    data = res.get_json()
    assert "web-public" in data["presets"]
    assert "db-private" in data["presets"]
    assert "ssh-bastion" in data["presets"]
    assert "custom" in data["presets"]


def test_api_preset_valid_name(client):
    res = client.get("/firewall/api/preset/web-public")
    assert res.status_code == 200
    data = res.get_json()
    assert data["backend"] == "ufw"
    assert len(data["rules"]) == 3


def test_api_preset_unknown_name_returns_404(client):
    res = client.get("/firewall/api/preset/ce-preset-nexiste-pas")
    assert res.status_code == 404
    assert "error" in res.get_json()


def test_api_generate_valid_config_returns_files(client):
    payload = {"preset": "web-public", "backend": "ufw", "fail2ban": True}
    res = client.post("/firewall/api/generate", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    filenames = {f["filename"] for f in data["files"]}
    assert filenames == {"setup-firewall.sh", "jail.local"}


def test_api_generate_nftables_backend(client):
    payload = {"preset": "ssh-bastion", "backend": "nftables"}
    res = client.post("/firewall/api/generate", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    filenames = {f["filename"] for f in data["files"]}
    assert filenames == {"nftables.conf"}


def test_api_generate_invalid_config_returns_400(client):
    payload = {"preset": "custom", "backend": "ufw", "rules": []}
    res = client.post("/firewall/api/generate", json=payload)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_api_generate_invalid_backend_returns_400(client):
    payload = {"preset": "web-public", "backend": "bogus-backend"}
    res = client.post("/firewall/api/generate", json=payload)
    assert res.status_code == 400


def test_api_generate_empty_body_returns_400(client):
    res = client.post("/firewall/api/generate", json={})
    assert res.status_code == 400
