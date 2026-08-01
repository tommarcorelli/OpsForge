import json

import pytest
import yaml

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


BASE_PAYLOAD = {
    "stacks": [{"language": "python", "package_manager": "pip"}],
    "jobs": ["test"],
    "branches": ["main"],
    "provider": "github",
}


def _payload(**overrides):
    return {**BASE_PAYLOAD, **overrides}


def test_generate_without_deps_has_no_extra_files(client):
    res = client.post("/cicd/api/generate", json=_payload())
    assert res.status_code == 200
    assert "extra_files" not in res.get_json()


def test_generate_with_dependabot_returns_extra_file(client):
    res = client.post("/cicd/api/generate", json=_payload(deps_tool="dependabot"))
    assert res.status_code == 200
    extra = res.get_json()["extra_files"]
    assert len(extra) == 1
    assert extra[0]["filename"] == ".github/dependabot.yml"
    parsed = yaml.safe_load(extra[0]["content"])
    assert parsed["version"] == 2


def test_generate_with_renovate_returns_json_file(client):
    res = client.post("/cicd/api/generate", json=_payload(deps_tool="renovate"))
    assert res.status_code == 200
    extra = res.get_json()["extra_files"][0]
    assert extra["filename"] == "renovate.json"
    assert "npm" not in json.loads(extra["content"])["enabledManagers"]


def test_deps_target_branch_follows_pipeline_branch(client):
    res = client.post(
        "/cicd/api/generate", json=_payload(branches=["develop"], deps_tool="dependabot")
    )
    parsed = yaml.safe_load(res.get_json()["extra_files"][0]["content"])
    assert parsed["updates"][0]["target-branch"] == "develop"


def test_github_actions_ecosystem_only_on_github(client):
    on_github = client.post("/cicd/api/generate", json=_payload(deps_tool="dependabot"))
    ecosystems = [
        u["package-ecosystem"]
        for u in yaml.safe_load(on_github.get_json()["extra_files"][0]["content"])["updates"]
    ]
    assert "github-actions" in ecosystems

    on_gitlab = client.post(
        "/cicd/api/generate", json=_payload(provider="gitlab", deps_tool="renovate")
    )
    managers = json.loads(on_gitlab.get_json()["extra_files"][0]["content"])["enabledManagers"]
    assert "github-actions" not in managers


def test_deps_options_are_forwarded(client):
    res = client.post(
        "/cicd/api/generate",
        json=_payload(
            deps_tool="dependabot",
            deps_schedule="daily",
            deps_include_docker=True,
            deps_group_minor_patch=False,
        ),
    )
    parsed = yaml.safe_load(res.get_json()["extra_files"][0]["content"])
    ecosystems = [u["package-ecosystem"] for u in parsed["updates"]]
    assert "docker" in ecosystems
    assert parsed["updates"][0]["schedule"]["interval"] == "daily"
    assert "groups" not in parsed["updates"][0]


def test_unknown_deps_tool_returns_400(client):
    res = client.post("/cicd/api/generate", json=_payload(deps_tool="greenkeeper"))
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_unknown_deps_schedule_returns_400(client):
    res = client.post(
        "/cicd/api/generate", json=_payload(deps_tool="dependabot", deps_schedule="hourly")
    )
    assert res.status_code == 400


def test_cicd_page_exposes_deps_controls(client):
    res = client.get("/cicd/")
    assert res.status_code == 200
    assert b'name="deps-tool"' in res.data
    assert b"Dependabot" in res.data
    assert b"Renovate" in res.data
