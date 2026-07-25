"""
test_circleci_core.py
----------------------
Tests unitaires pour modules/cicd/circleci_core.py.

Lancer avec : pytest tests/cicd/test_circleci_core.py -v
"""

import pytest
import yaml

from modules.cicd.circleci_core import generate_circleci_config, generate_badge_markdown


def _parse(yaml_text):
    return yaml.safe_load(yaml_text)


def test_no_stacks_raises_error():
    with pytest.raises(ValueError):
        generate_circleci_config([], jobs=["test"])


def test_basic_single_stack_generates_valid_yaml():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_circleci_config(stacks, jobs=["lint", "test", "build"])
    parsed = _parse(yaml_text)

    assert parsed["version"] == 2.1
    assert "lint-python" in parsed["jobs"]
    assert "test-python" in parsed["jobs"]
    assert "build-python" in parsed["jobs"]


def test_only_requested_jobs_appear():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_circleci_config(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    assert list(parsed["jobs"].keys()) == ["test-python"]


def test_multi_stack_generates_jobs_for_each():
    stacks = [
        {"language": "python", "version": "3.12", "package_manager": "pip"},
        {"language": "node", "version": "20", "package_manager": "npm"},
    ]
    yaml_text = generate_circleci_config(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    assert "test-python" in parsed["jobs"]
    assert "test-node" in parsed["jobs"]


def test_job_uses_correct_image():
    stacks = [{"language": "python", "version": "3.11", "package_manager": "pip"}]
    yaml_text = generate_circleci_config(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    assert parsed["jobs"]["test-python"]["docker"][0]["image"] == "cimg/python:3.11"


def test_build_requires_test_when_both_present():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_circleci_config(stacks, jobs=["test", "build"])
    parsed = _parse(yaml_text)

    build_entry = next(
        j for j in parsed["workflows"]["build-and-test"]["jobs"] if isinstance(j, dict) and "build-python" in j
    )
    assert build_entry["build-python"]["requires"] == ["test-python"]


def test_lint_has_no_requires():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_circleci_config(stacks, jobs=["lint", "test"])
    parsed = _parse(yaml_text)

    assert "lint-python" in parsed["workflows"]["build-and-test"]["jobs"]


def test_matrix_versions_creates_matrix_parameter():
    stacks = [{
        "language": "python", "version": "3.12", "package_manager": "pip",
        "matrix_versions": ["3.10", "3.11", "3.12"],
    }]
    yaml_text = generate_circleci_config(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    assert parsed["jobs"]["test-python"]["parameters"]["version"]["type"] == "string"
    assert "<< parameters.version >>" in parsed["jobs"]["test-python"]["docker"][0]["image"]

    workflow_entry = next(
        j for j in parsed["workflows"]["build-and-test"]["jobs"] if isinstance(j, dict) and "test-python" in j
    )
    assert workflow_entry["test-python"]["matrix"]["parameters"]["version"] == ["3.10", "3.11", "3.12"]


def test_single_version_does_not_create_matrix():
    stacks = [{
        "language": "python", "version": "3.12", "package_manager": "pip",
        "matrix_versions": ["3.12"],
    }]
    yaml_text = generate_circleci_config(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    assert "parameters" not in parsed["jobs"]["test-python"]


def test_docker_hub_deploy_job():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_circleci_config(
        stacks, jobs=["test"], deploy={"targets": ["docker_hub"], "docker_image": "user/app"}
    )
    parsed = _parse(yaml_text)

    assert "deploy-docker_hub" in parsed["jobs"]
    assert "setup_remote_docker" in parsed["jobs"]["deploy-docker_hub"]["steps"]
    assert "user/app:latest" in yaml_text


def test_ssh_deploy_uses_variables_not_hardcoded():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_circleci_config(
        stacks, jobs=["test"], deploy={"targets": ["ssh"], "deploy_path": "/var/www/app"}
    )
    assert "$SSH_HOST" in yaml_text
    assert "$SSH_USER" in yaml_text
    assert "add_ssh_keys" in yaml_text


def test_aws_s3_skipped_without_node_stack():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_circleci_config(
        stacks, jobs=["test"], deploy={"targets": ["aws_s3", "docker_hub"]}
    )
    parsed = _parse(yaml_text)

    assert "deploy-aws_s3" not in parsed["jobs"]
    assert "deploy-docker_hub" in parsed["jobs"]


def test_deploy_requires_last_stack_job():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_circleci_config(
        stacks, jobs=["test", "build"], deploy={"targets": ["docker_hub"]}
    )
    parsed = _parse(yaml_text)

    deploy_entry = next(
        j for j in parsed["workflows"]["build-and-test"]["jobs"]
        if isinstance(j, dict) and "deploy-docker_hub" in j
    )
    assert deploy_entry["deploy-docker_hub"]["requires"] == ["build-python"]


def test_deploy_filtered_to_single_branch():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_circleci_config(
        stacks, jobs=["test"], deploy={"targets": ["docker_hub"]}, branches=["main"]
    )
    parsed = _parse(yaml_text)

    deploy_entry = next(
        j for j in parsed["workflows"]["build-and-test"]["jobs"]
        if isinstance(j, dict) and "deploy-docker_hub" in j
    )
    assert deploy_entry["deploy-docker_hub"]["filters"]["branches"]["only"] == "main"


def test_schedule_cron_adds_nightly_workflow():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_circleci_config(stacks, jobs=["test"], schedule_cron="0 3 * * *")
    parsed = _parse(yaml_text)

    assert "nightly" in parsed["workflows"]
    assert parsed["workflows"]["nightly"]["triggers"][0]["schedule"]["cron"] == "0 3 * * *"


def test_no_schedule_means_no_nightly_workflow():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_circleci_config(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    assert "nightly" not in parsed["workflows"]


def test_badge_markdown_format():
    badge = generate_badge_markdown("me/repo", branch="develop")
    assert badge.startswith("[![CircleCI]")
    assert "me/repo/tree/develop" in badge
    assert "gh/me/repo" in badge
