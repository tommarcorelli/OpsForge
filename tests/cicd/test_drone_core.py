"""
test_drone_core.py
-------------------
Tests unitaires pour modules/cicd/drone_core.py.

Lancer avec : pytest tests/cicd/test_drone_core.py -v
"""

import pytest
import yaml

from modules.cicd.drone_core import generate_badge_markdown, generate_drone_yaml, write_drone_yaml


def _parse(yaml_text):
    return yaml.safe_load(yaml_text)


def _step_names(parsed):
    return [s["name"] for s in parsed["steps"]]


def test_no_stacks_raises_error():
    with pytest.raises(ValueError):
        generate_drone_yaml([], jobs=["test"])


def test_basic_single_stack_generates_valid_yaml():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_drone_yaml(stacks, jobs=["lint", "test", "build"])
    parsed = _parse(yaml_text)

    assert parsed["kind"] == "pipeline"
    assert parsed["type"] == "docker"
    names = _step_names(parsed)
    assert "lint-python" in names
    assert "test-python" in names
    assert "build-python" in names


def test_only_requested_jobs_appear():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_drone_yaml(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    assert _step_names(parsed) == ["test-python"]


def test_multi_stack_generates_steps_for_each():
    stacks = [
        {"language": "python", "version": "3.12", "package_manager": "pip"},
        {"language": "node", "version": "20", "package_manager": "npm"},
    ]
    yaml_text = generate_drone_yaml(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    names = _step_names(parsed)
    assert "test-python" in names
    assert "test-node" in names


def test_step_uses_correct_image():
    stacks = [{"language": "python", "version": "3.11", "package_manager": "pip"}]
    yaml_text = generate_drone_yaml(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    step = next(s for s in parsed["steps"] if s["name"] == "test-python")
    assert step["image"] == "python:3.11-slim"


def test_docker_hub_deploy_uses_official_plugin_and_secrets():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_drone_yaml(
        stacks, jobs=["test"], deploy={"targets": ["docker_hub"], "docker_image": "user/app:v2"}
    )
    parsed = _parse(yaml_text)

    step = next(s for s in parsed["steps"] if s["name"] == "deploy-docker_hub")
    assert step["image"] == "plugins/docker"
    assert step["settings"]["repo"] == "user/app"
    assert step["settings"]["tags"] == "v2"
    assert step["settings"]["password"]["from_secret"] == "docker_password"


def test_ssh_deploy_uses_secrets_not_hardcoded():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_drone_yaml(
        stacks, jobs=["test"], deploy={"targets": ["ssh"], "deploy_path": "/var/www/app"}
    )
    parsed = _parse(yaml_text)

    step = next(s for s in parsed["steps"] if s["name"] == "deploy-ssh")
    assert step["settings"]["host"]["from_secret"] == "ssh_host"
    assert step["settings"]["username"]["from_secret"] == "ssh_user"
    assert "/var/www/app" in step["settings"]["script"][0]


def test_aws_s3_skipped_without_node_stack():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_drone_yaml(
        stacks, jobs=["test"], deploy={"targets": ["aws_s3", "docker_hub"]}
    )
    parsed = _parse(yaml_text)

    names = _step_names(parsed)
    assert not any("s3" in n for n in names)
    assert "deploy-docker_hub" in names


def test_aws_s3_present_with_node_stack():
    stacks = [{"language": "node", "version": "20", "package_manager": "npm"}]
    yaml_text = generate_drone_yaml(
        stacks, jobs=["test"], deploy={"targets": ["aws_s3"], "s3_bucket": "my-bucket"}
    )
    parsed = _parse(yaml_text)

    step = next(s for s in parsed["steps"] if s["name"] == "deploy-aws_s3")
    assert step["image"] == "plugins/s3-sync"
    assert step["settings"]["bucket"] == "my-bucket"


def test_vercel_deploy_step():
    stacks = [{"language": "node", "version": "20", "package_manager": "npm"}]
    yaml_text = generate_drone_yaml(stacks, jobs=["test"], deploy={"targets": ["vercel"]})
    parsed = _parse(yaml_text)

    step = next(s for s in parsed["steps"] if s["name"] == "deploy-vercel")
    assert step["image"] == "node:20-slim"
    assert "vercel --token $VERCEL_TOKEN" in " ".join(step["commands"])


def test_deploy_cible_inconnue_ignoree():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_drone_yaml(
        stacks, jobs=["test"], deploy={"targets": ["cible-inconnue", "docker_hub"]}
    )
    names = _step_names(_parse(yaml_text))
    assert "deploy-docker_hub" in names


def test_langage_non_pris_en_charge_ne_genere_aucun_step():
    stacks = [{"language": "cobol", "version": "1.0", "package_manager": ""}]
    with pytest.raises(ValueError, match="Aucun step genere"):
        generate_drone_yaml(stacks, jobs=["test"])


def test_langage_sans_commande_installation_utilise_le_repli():
    from modules.cicd.drone_core import _get_install_cmd
    assert _get_install_cmd("cobol", "") == "echo 'Aucune commande d-installation definie pour ce langage'"


def test_package_manager_inconnu_utilise_la_premiere_commande_disponible():
    from modules.cicd.drone_core import INSTALL_COMMANDS, _get_install_cmd
    result = _get_install_cmd("python", "conda")
    assert result in INSTALL_COMMANDS["python"].values()


def test_cible_de_deploiement_cataloguee_mais_non_geree_est_ignoree(monkeypatch):
    """Garde-fou defensif : voir teamcity_core/bitbucket_core, meme principe."""
    from modules.cicd import drone_core
    monkeypatch.setitem(
        drone_core.DEPLOY_TARGETS, "mystere",
        {"requires_language": None, "label": "Cible mystere"},
    )
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_drone_yaml(
        stacks, jobs=["test"], deploy={"targets": ["mystere", "docker_hub"]}
    )
    names = _step_names(_parse(yaml_text))
    assert "deploy-docker_hub" in names
    assert "deploy-mystere" not in names


def test_write_drone_yaml_cree_le_fichier(tmp_path):
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    output = tmp_path / "sub" / ".drone.yml"
    path = write_drone_yaml(stacks, str(output), jobs=["test"])
    assert path == str(output)
    assert output.is_file()
    assert "kind: pipeline" in output.read_text(encoding="utf-8")


def test_deploy_filtered_to_branch():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_drone_yaml(
        stacks, jobs=["test"], deploy={"targets": ["docker_hub"]}, branches=["release"]
    )
    parsed = _parse(yaml_text)

    step = next(s for s in parsed["steps"] if s["name"] == "deploy-docker_hub")
    assert step["when"]["branch"] == ["release"]


def test_trigger_includes_all_branches():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_drone_yaml(stacks, jobs=["test"], branches=["main", "develop"])
    parsed = _parse(yaml_text)

    assert parsed["trigger"]["branch"] == ["main", "develop"]
    assert parsed["trigger"]["event"] == ["push", "pull_request"]


def test_schedule_cron_adds_explanatory_comment():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_drone_yaml(stacks, jobs=["test"], schedule_cron="0 3 * * *")

    assert "drone cron add" in yaml_text
    assert "0 3 * * *" in yaml_text
    # Le commentaire ne doit pas casser le parsing YAML
    _parse(yaml_text)


def test_no_schedule_means_no_cron_comment():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_drone_yaml(stacks, jobs=["test"])

    assert "drone cron" not in yaml_text


def test_badge_markdown_format():
    badge = generate_badge_markdown("me/repo", branch="develop")
    assert badge.startswith("[![Build Status]")
    assert "me/repo/status.svg?branch=develop" in badge
    assert "cloud.drone.io" in badge


def test_badge_markdown_self_hosted_url():
    badge = generate_badge_markdown("me/repo", drone_url="https://ci.example.com/")
    assert "https://ci.example.com/api/badges/me/repo" in badge
