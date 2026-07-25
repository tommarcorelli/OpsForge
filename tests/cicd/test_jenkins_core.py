"""
test_jenkins_core.py
---------------------
Tests unitaires pour modules/cicd/jenkins_core.py.

Le Jenkinsfile est du Groovy, pas du YAML : les assertions portent donc
sur la presence de motifs textuels et l'equilibre des accolades, plutot
que sur un parsing structure comme pour les autres providers.

Lancer avec : pytest tests/cicd/test_jenkins_core.py -v
"""

import pytest

from modules.cicd.jenkins_core import generate_jenkinsfile, generate_badge_markdown


def _braces_balanced(text):
    return text.count("{") == text.count("}")


def test_no_stacks_raises_error():
    with pytest.raises(ValueError):
        generate_jenkinsfile([], jobs=["test"])


def test_basic_single_stack_generates_pipeline():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_jenkinsfile(stacks, jobs=["lint", "test", "build"])

    assert text.startswith("pipeline {")
    assert "agent none" in text
    assert "stage('Lint - python')" in text
    assert "stage('Test - python')" in text
    assert "stage('Build - python')" in text
    assert _braces_balanced(text)


def test_only_requested_jobs_appear():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_jenkinsfile(stacks, jobs=["test"])

    assert "stage('Test - python')" in text
    assert "stage('Lint - python')" not in text
    assert "stage('Build - python')" not in text


def test_multi_stack_generates_stages_for_each():
    stacks = [
        {"language": "python", "version": "3.12", "package_manager": "pip"},
        {"language": "node", "version": "20", "package_manager": "npm"},
    ]
    text = generate_jenkinsfile(stacks, jobs=["test"])

    assert "stage('Test - python')" in text
    assert "stage('Test - node')" in text


def test_job_uses_correct_docker_image():
    stacks = [{"language": "python", "version": "3.11", "package_manager": "pip"}]
    text = generate_jenkinsfile(stacks, jobs=["test"])

    assert "image 'python:3.11-slim'" in text


def test_docker_hub_deploy_uses_credentials_binding():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_jenkinsfile(
        stacks, jobs=["test"], deploy={"targets": ["docker_hub"], "docker_image": "user/app"}
    )

    assert "stage('Deploy Docker Hub')" in text
    assert "credentials('dockerhub-credentials')" in text
    assert "user/app:latest" in text
    assert _braces_balanced(text)


def test_ssh_deploy_uses_sshagent_not_hardcoded_secrets():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_jenkinsfile(
        stacks, jobs=["test"], deploy={"targets": ["ssh"], "deploy_path": "/var/www/app"}
    )

    assert "sshagent(credentials: ['ssh-deploy-credentials'])" in text
    assert "$SSH_HOST" in text
    assert "$SSH_USER" in text


def test_aws_s3_skipped_without_node_stack():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_jenkinsfile(
        stacks, jobs=["test"], deploy={"targets": ["aws_s3", "docker_hub"]}
    )

    assert "Deploy AWS S3" not in text
    assert "Deploy Docker Hub" in text


def test_deploy_stage_filtered_to_branch():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_jenkinsfile(
        stacks, jobs=["test"], deploy={"targets": ["docker_hub"]}, branches=["release"]
    )

    assert "when { branch 'release' }" in text


def test_schedule_cron_adds_triggers_block():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_jenkinsfile(stacks, jobs=["test"], schedule_cron="0 3 * * *")

    assert "triggers {" in text
    assert "cron('0 3 * * *')" in text
    assert _braces_balanced(text)


def test_no_schedule_means_no_triggers_block():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    text = generate_jenkinsfile(stacks, jobs=["test"])

    assert "triggers {" not in text


def test_badge_markdown_simple_job():
    badge = generate_badge_markdown("https://ci.example.com", "mon-projet")
    assert badge.startswith("[![Jenkins]")
    assert "https://ci.example.com/job/mon-projet/badge/icon" in badge
    assert "https://ci.example.com/job/mon-projet/" in badge


def test_badge_markdown_multibranch_job_path():
    badge = generate_badge_markdown("https://ci.example.com/", "mon-projet/main")
    assert "job/mon-projet/job/main/badge/icon" in badge
