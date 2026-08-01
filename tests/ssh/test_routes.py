import pytest

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def test_index_page_returns_200(client):
    res = client.get("/ssh/")
    assert res.status_code == 200
    assert b"ssh/style.css" in res.data
    assert b"ssh/script.js" in res.data


def test_hub_links_to_ssh_module(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b'href="/ssh/"' in res.data


def test_api_presets_lists_all_presets(client):
    res = client.get("/ssh/api/presets")
    assert res.status_code == 200
    presets = res.get_json()["presets"]
    assert "poste-de-travail" in presets
    assert "serveur-durci" in presets


def test_api_presets_filtered_by_role(client):
    res = client.get("/ssh/api/presets?role=server")
    assert res.status_code == 200
    presets = res.get_json()["presets"]
    assert "serveur-durci" in presets
    assert "poste-de-travail" not in presets


def test_api_presets_unknown_role_returns_400(client):
    res = client.get("/ssh/api/presets?role=proxy")
    assert res.status_code == 400


def test_api_preset_valid_name(client):
    res = client.get("/ssh/api/preset/acces-bastion")
    assert res.status_code == 200
    data = res.get_json()
    assert data["role"] == "client"
    assert any(h["alias"] == "bastion" for h in data["hosts"])


def test_api_preset_unknown_name_returns_404(client):
    res = client.get("/ssh/api/preset/ce-preset-nexiste-pas")
    assert res.status_code == 404


def test_api_generate_client_returns_config(client):
    payload = {
        "preset": "custom",
        "role": "client",
        "hosts": [{"alias": "lab", "hostname": "192.168.1.50", "user": "tom"}],
    }
    res = client.post("/ssh/api/generate", json=payload)
    assert res.status_code == 200
    files = res.get_json()["files"]
    assert files[0]["filename"] == "ssh_config"
    assert "Host lab" in files[0]["content"]


def test_api_generate_server_returns_fragment(client):
    res = client.post("/ssh/api/generate", json={"preset": "serveur-durci", "role": "server"})
    assert res.status_code == 200
    filenames = {f["filename"] for f in res.get_json()["files"]}
    assert filenames == {"sshd_config.d/10-opsforge-durcissement.conf"}


def test_api_generate_server_with_keys_returns_two_files(client):
    payload = {
        "preset": "custom",
        "role": "server",
        "authorized_keys": [{"key": "ssh-ed25519 AAAAC3Nza tom@laptop", "restrict": True}],
    }
    res = client.post("/ssh/api/generate", json=payload)
    assert res.status_code == 200
    filenames = {f["filename"] for f in res.get_json()["files"]}
    assert "authorized_keys" in filenames


def test_api_generate_invalid_config_returns_400(client):
    res = client.post("/ssh/api/generate", json={"preset": "custom", "role": "client", "hosts": []})
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_api_generate_empty_body_returns_400(client):
    res = client.post("/ssh/api/generate", json={})
    assert res.status_code == 400
