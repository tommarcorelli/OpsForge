"""
test_core.py
------------
Tests unitaires pour generator/core.py.

Lancer avec : pytest tests/test_core.py -v
"""

import pytest
import yaml

from modules.cicd.core import generate_workflow


def _parse(yaml_text):
    return yaml.safe_load(yaml_text)


def test_no_stacks_raises_error():
    with pytest.raises(ValueError):
        generate_workflow([], jobs=["test"])


def test_concurrency_et_permissions_par_defaut():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    parsed = _parse(generate_workflow(stacks, jobs=["test"]))
    assert parsed["concurrency"]["cancel-in-progress"] is True
    assert parsed["permissions"]["contents"] == "read"


def test_permissions_elargies_pour_github_pages():
    stacks = [{"language": "node", "version": "20", "package_manager": "npm"}]
    parsed = _parse(generate_workflow(
        stacks, jobs=["build"], deploy={"targets": ["github_pages"]}))
    assert parsed["permissions"]["pages"] == "write"
    assert parsed["permissions"]["contents"] == "write"


def test_ruby_genere_un_job_valide():
    stacks = [{"language": "ruby", "version": "3.3", "package_manager": "bundler"}]
    parsed = _parse(generate_workflow(stacks, jobs=["lint", "test", "build"]))
    assert "lint-ruby" in parsed["jobs"]
    assert "test-ruby" in parsed["jobs"]
    assert "build-ruby" in parsed["jobs"]
    # utilise bien l'action officielle ruby/setup-ruby
    yaml_text = generate_workflow(stacks, jobs=["test"])
    assert "ruby/setup-ruby@v1" in yaml_text
    assert 'ruby-version: "3.3"' in yaml_text


def test_dotnet_genere_un_job_valide():
    stacks = [{"language": "dotnet", "version": "8.0", "package_manager": "dotnet"}]
    parsed = _parse(generate_workflow(stacks, jobs=["test", "build"]))
    assert "test-dotnet" in parsed["jobs"]
    assert "build-dotnet" in parsed["jobs"]
    yaml_text = generate_workflow(stacks, jobs=["build"])
    assert "actions/setup-dotnet@v4" in yaml_text
    assert 'dotnet-version: "8.0.x"' in yaml_text


def test_basic_single_stack_generates_valid_yaml():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_workflow(stacks, jobs=["lint", "test", "build"])
    parsed = _parse(yaml_text)

    assert "lint-python" in parsed["jobs"]
    assert "test-python" in parsed["jobs"]
    assert "build-python" in parsed["jobs"]


def test_only_requested_jobs_are_generated():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_workflow(stacks, jobs=["lint"])
    parsed = _parse(yaml_text)

    assert list(parsed["jobs"].keys()) == ["lint-python"]


def test_multi_stack_generates_jobs_for_each():
    stacks = [
        {"language": "python", "version": "3.12", "package_manager": "pip"},
        {"language": "node", "version": "20", "package_manager": "npm"},
    ]
    yaml_text = generate_workflow(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    assert "test-python" in parsed["jobs"]
    assert "test-node" in parsed["jobs"]


def test_build_depends_on_test_when_both_present():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_workflow(stacks, jobs=["test", "build"])
    parsed = _parse(yaml_text)

    assert parsed["jobs"]["build-python"]["needs"] == ["test-python"]


def test_build_has_no_needs_when_test_not_selected():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_workflow(stacks, jobs=["build"])
    parsed = _parse(yaml_text)

    assert "needs" not in parsed["jobs"]["build-python"]


def test_lint_never_has_dependencies():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_workflow(stacks, jobs=["lint", "test", "build"])
    parsed = _parse(yaml_text)

    assert "needs" not in parsed["jobs"]["lint-python"]


def test_deploy_docker_hub_depends_on_build():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_workflow(
        stacks,
        jobs=["test", "build"],
        deploy={"targets": ["docker_hub"], "docker_image": "user/app"},
    )
    parsed = _parse(yaml_text)

    assert parsed["jobs"]["deploy-docker_hub"]["needs"] == ["build-python"]


def test_deploy_depends_on_test_when_no_build():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_workflow(
        stacks,
        jobs=["test"],
        deploy={"targets": ["docker_hub"]},
    )
    parsed = _parse(yaml_text)

    assert parsed["jobs"]["deploy-docker_hub"]["needs"] == ["test-python"]


def test_github_pages_skipped_without_node_stack():
    """github_pages ne doit pas generer de job si aucune stack Node."""
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_workflow(
        stacks,
        jobs=["build"],
        deploy={"targets": ["github_pages", "docker_hub"]},
    )
    parsed = _parse(yaml_text)

    assert "deploy-github_pages" not in parsed["jobs"]
    assert "deploy-docker_hub" in parsed["jobs"]


def test_github_pages_included_with_node_stack():
    stacks = [{"language": "node", "version": "20", "package_manager": "npm"}]
    yaml_text = generate_workflow(
        stacks,
        jobs=["build"],
        deploy={"targets": ["github_pages"], "pages_dir": "build"},
    )
    parsed = _parse(yaml_text)

    assert "deploy-github_pages" in parsed["jobs"]


def test_github_actions_secrets_syntax_preserved():
    """La syntaxe ${{ secrets.XXX }} ne doit pas etre cassee par le
    remplacement des placeholders (regression test pour le passage de
    .format() a .replace())."""
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_workflow(
        stacks,
        jobs=["test"],
        deploy={"targets": ["ssh"], "deploy_path": "/var/www/app"},
    )
    assert "${{ secrets.SSH_HOST }}" in yaml_text
    assert "${{ secrets.SSH_USER }}" in yaml_text
    assert "${{ secrets.SSH_PRIVATE_KEY }}" in yaml_text


def test_custom_branches_appear_in_triggers():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_workflow(
        stacks,
        jobs=["test"],
        triggers={"branches": ["main", "develop"], "pull_request": True, "workflow_dispatch": True},
    )
    parsed = _parse(yaml_text)

    assert parsed["on"]["push"]["branches"] == ["main", "develop"]


def test_default_version_used_when_missing():
    stacks = [{"language": "python", "package_manager": "pip"}]
    yaml_text = generate_workflow(stacks, jobs=["test"])
    assert 'python-version: "3.12"' in yaml_text


def test_unknown_package_manager_falls_back_gracefully():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "conda"}]
    # Ne doit pas lever d'exception, doit utiliser un fallback raisonnable
    yaml_text = generate_workflow(stacks, jobs=["test"])
    assert "pip install -r requirements.txt" in yaml_text
