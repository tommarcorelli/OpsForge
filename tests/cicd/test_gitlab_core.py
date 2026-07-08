"""
test_gitlab_core.py
--------------------
Tests unitaires pour generator/gitlab_core.py.

Lancer avec : pytest tests/test_gitlab_core.py -v
"""

import pytest
import yaml

from modules.cicd.gitlab_core import generate_gitlab_ci


def _parse(yaml_text):
    return yaml.safe_load(yaml_text)


def test_no_stacks_raises_error():
    with pytest.raises(ValueError):
        generate_gitlab_ci([], jobs=["test"])


def test_basic_single_stack_generates_valid_yaml():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_gitlab_ci(stacks, jobs=["lint", "test", "build"])
    parsed = _parse(yaml_text)

    assert parsed["stages"] == ["lint", "test", "build"]
    assert "lint-python" in parsed
    assert "test-python" in parsed
    assert "build-python" in parsed


def test_only_requested_stages_appear():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_gitlab_ci(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    assert parsed["stages"] == ["test"]


def test_multi_stack_generates_jobs_for_each():
    stacks = [
        {"language": "python", "version": "3.12", "package_manager": "pip"},
        {"language": "node", "version": "20", "package_manager": "npm"},
    ]
    yaml_text = generate_gitlab_ci(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    assert "test-python" in parsed
    assert "test-node" in parsed


def test_job_uses_correct_image():
    stacks = [{"language": "python", "version": "3.11", "package_manager": "pip"}]
    yaml_text = generate_gitlab_ci(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    assert parsed["test-python"]["image"] == "python:3.11-slim"


def test_gitlab_pages_creates_job_named_pages():
    """GitLab exige que le job de Pages s'appelle EXACTEMENT 'pages'."""
    stacks = [{"language": "node", "version": "20", "package_manager": "npm"}]
    yaml_text = generate_gitlab_ci(
        stacks, jobs=["build"], deploy={"targets": ["gitlab_pages"], "pages_dir": "build"}
    )
    parsed = _parse(yaml_text)

    assert "pages" in parsed
    assert parsed["pages"]["artifacts"]["paths"] == ["public"]


def test_gitlab_pages_skipped_without_node_stack():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_gitlab_ci(
        stacks, jobs=["build"], deploy={"targets": ["gitlab_pages", "docker_hub"]}
    )
    parsed = _parse(yaml_text)

    assert "pages" not in parsed
    assert "deploy-docker_hub" in parsed


def test_stages_include_deploy_when_deploy_requested():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_gitlab_ci(
        stacks, jobs=["test"], deploy={"targets": ["docker_hub"]}
    )
    parsed = _parse(yaml_text)

    assert parsed["stages"] == ["test", "deploy"]


def test_docker_hub_uses_dind_service():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_gitlab_ci(
        stacks, jobs=["test"], deploy={"targets": ["docker_hub"], "docker_image": "user/app"}
    )
    parsed = _parse(yaml_text)

    assert "docker:24-dind" in parsed["deploy-docker_hub"]["services"]
    assert "user/app:latest" in " ".join(parsed["deploy-docker_hub"]["script"])


def test_ssh_deploy_uses_variables_not_hardcoded():
    """Les identifiants ne doivent jamais etre en dur, seulement des
    variables CI/CD GitLab ($SSH_HOST, etc.)."""
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_gitlab_ci(
        stacks, jobs=["test"], deploy={"targets": ["ssh"], "deploy_path": "/var/www/app"}
    )
    assert "$SSH_HOST" in yaml_text
    assert "$SSH_USER" in yaml_text
    assert "$SSH_PRIVATE_KEY" in yaml_text


def test_stage_order_is_always_lint_test_build_deploy():
    """Meme si les jobs sont demandes dans le desordre, les stages
    doivent rester dans l'ordre logique lint -> test -> build -> deploy."""
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_gitlab_ci(
        stacks,
        jobs=["build", "lint", "test"],
        deploy={"targets": ["docker_hub"]},
    )
    parsed = _parse(yaml_text)

    assert parsed["stages"] == ["lint", "test", "build", "deploy"]
