"""
test_teamcity_core.py
-----------------------
Tests unitaires pour modules/cicd/teamcity_core.py.

Le fichier settings.kts est du Kotlin, pas du YAML : les assertions
portent donc sur la presence de motifs textuels et l'equilibre des
accolades, comme pour jenkins_core.py.

Lancer avec : pytest tests/cicd/test_teamcity_core.py -v
"""

import pytest

from modules.cicd.teamcity_core import (
    _cron_to_teamcity_fields,
    generate_badge_markdown,
    generate_teamcity_kotlin_dsl,
)


def _braces_balanced(text):
    return text.count("{") == text.count("}")


def test_no_stacks_raises_error():
    with pytest.raises(ValueError):
        generate_teamcity_kotlin_dsl([], jobs=["test"])


def test_basic_single_stack_generates_pipeline():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_teamcity_kotlin_dsl(stacks, jobs=["lint", "test", "build"])

    assert 'version = "2024.03"' in text
    assert "object LintPython : BuildType(" in text
    assert "object TestPython : BuildType(" in text
    assert "object BuildPython : BuildType(" in text
    assert "buildType(LintPython)" in text
    assert "buildType(TestPython)" in text
    assert "buildType(BuildPython)" in text
    assert _braces_balanced(text)


def test_only_requested_jobs_appear():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_teamcity_kotlin_dsl(stacks, jobs=["test"])

    assert "object TestPython" in text
    assert "object LintPython" not in text
    assert "object BuildPython" not in text


def test_multi_stack_generates_build_types_for_each():
    stacks = [
        {"language": "python", "version": "3.12", "package_manager": "pip"},
        {"language": "node", "version": "20", "package_manager": "npm"},
    ]
    text = generate_teamcity_kotlin_dsl(stacks, jobs=["test"])

    assert "object TestPython" in text
    assert "object TestNode" in text
    assert _braces_balanced(text)


def test_build_uses_docker_wrapper_with_correct_image():
    stacks = [{"language": "python", "version": "3.11", "package_manager": "pip"}]
    text = generate_teamcity_kotlin_dsl(stacks, jobs=["test"])

    assert 'dockerImage = "python:3.11-slim"' in text
    assert "dockerPull = true" in text


def test_build_has_snapshot_dependency_on_test():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_teamcity_kotlin_dsl(stacks, jobs=["test", "build"])

    # Le bloc dependencies de BuildPython doit referencer TestPython
    build_block_start = text.index("object BuildPython")
    build_block = text[build_block_start:]
    assert "dependencies {" in build_block
    assert "snapshot(TestPython)" in build_block
    assert _braces_balanced(text)


def test_lint_has_no_dependencies_block():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_teamcity_kotlin_dsl(stacks, jobs=["lint", "test"])

    lint_start = text.index("object LintPython")
    lint_block = text[lint_start:lint_start + text[lint_start:].index("})")]
    assert "dependencies {" not in lint_block


def test_docker_hub_deploy_build_type():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_teamcity_kotlin_dsl(
        stacks, jobs=["test"], deploy={"targets": ["docker_hub"], "docker_image": "user/app"}
    )

    assert "object DeployDockerHub" in text
    assert "user/app:latest" in text
    assert "%dockerhub.username%" in text
    assert "%dockerhub.password%" in text
    assert _braces_balanced(text)


def test_ssh_deploy_uses_parameters_not_hardcoded():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_teamcity_kotlin_dsl(
        stacks, jobs=["test"], deploy={"targets": ["ssh"], "deploy_path": "/var/www/app"}
    )

    assert "%ssh.host%" in text
    assert "%ssh.user%" in text
    assert "%ssh.private.key%" in text
    assert "/var/www/app" in text


def test_aws_s3_skipped_without_node_stack():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_teamcity_kotlin_dsl(
        stacks, jobs=["test"], deploy={"targets": ["aws_s3", "docker_hub"]}
    )

    assert "object DeployAwsS3" not in text
    assert "object DeployDockerHub" in text


def test_aws_s3_present_with_node_stack():
    stacks = [{"language": "node", "version": "20", "package_manager": "npm"}]
    text = generate_teamcity_kotlin_dsl(
        stacks, jobs=["test"], deploy={"targets": ["aws_s3"], "s3_bucket": "mybucket"}
    )

    assert "object DeployAwsS3" in text
    assert "mybucket" in text


def test_deploy_has_branch_filter():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_teamcity_kotlin_dsl(
        stacks, jobs=["test"], deploy={"targets": ["docker_hub"]}, branches=["release"]
    )

    deploy_start = text.index("object DeployDockerHub")
    deploy_block = text[deploy_start:]
    assert 'branchFilter = "+:refs/heads/release"' in deploy_block


def test_deploy_depends_on_last_stack_build_type():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_teamcity_kotlin_dsl(
        stacks, jobs=["test", "build"], deploy={"targets": ["docker_hub"]}
    )

    deploy_start = text.index("object DeployDockerHub")
    deploy_block = text[deploy_start:]
    assert "snapshot(BuildPython)" in deploy_block


def test_cron_to_teamcity_fields_wildcard_day_of_week():
    fields = _cron_to_teamcity_fields("0 3 * * *")
    assert fields == {
        "seconds": "0", "minutes": "0", "hours": "3",
        "dayOfMonth": "*", "month": "*", "dayOfWeek": "*",
    }


def test_cron_to_teamcity_fields_specific_day_of_week():
    fields = _cron_to_teamcity_fields("0 3 * * 1")
    assert fields["dayOfWeek"] == "1"
    assert fields["dayOfMonth"] == "?"  # un seul des deux peut etre specifique


def test_cron_to_teamcity_fields_invalid_returns_none():
    assert _cron_to_teamcity_fields("not a cron") is None


def test_schedule_cron_adds_schedule_trigger():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_teamcity_kotlin_dsl(stacks, jobs=["test"], schedule_cron="0 3 * * *")

    assert "schedulingPolicy = cron {" in text
    assert 'hours = "3"' in text
    assert _braces_balanced(text)


def test_no_schedule_means_no_schedule_trigger():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_teamcity_kotlin_dsl(stacks, jobs=["test"])

    assert "schedulingPolicy" not in text


def test_badge_markdown_format():
    badge = generate_badge_markdown("https://ci.example.com", "MyProj_Test")
    assert badge.startswith("[![TeamCity]")
    assert "MyProj_Test" in badge
    assert "ci.example.com" in badge
