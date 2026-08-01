"""
test_bitbucket_core.py
------------------------
Tests unitaires pour modules/cicd/bitbucket_core.py.

Lancer avec : pytest tests/cicd/test_bitbucket_core.py -v
"""

import pytest
import yaml

from modules.cicd.bitbucket_core import generate_badge_markdown, generate_bitbucket_pipelines


def _parse(yaml_text):
    return yaml.safe_load(yaml_text)


def _step_names(pipeline_steps):
    return [s["step"]["name"] for s in pipeline_steps]


def test_no_stacks_raises_error():
    with pytest.raises(ValueError):
        generate_bitbucket_pipelines([], jobs=["test"])


def test_basic_single_stack_generates_valid_yaml():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_bitbucket_pipelines(stacks, jobs=["lint", "test", "build"])
    parsed = _parse(yaml_text)

    names = _step_names(parsed["pipelines"]["default"])
    assert names == ["lint-python", "test-python", "build-python"]


def test_only_requested_jobs_appear():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_bitbucket_pipelines(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    assert _step_names(parsed["pipelines"]["default"]) == ["test-python"]


def test_multi_stack_generates_steps_for_each():
    stacks = [
        {"language": "python", "version": "3.12", "package_manager": "pip"},
        {"language": "node", "version": "20", "package_manager": "npm"},
    ]
    yaml_text = generate_bitbucket_pipelines(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    names = _step_names(parsed["pipelines"]["default"])
    assert "test-python" in names
    assert "test-node" in names


def test_step_uses_correct_image():
    stacks = [{"language": "python", "version": "3.11", "package_manager": "pip"}]
    yaml_text = generate_bitbucket_pipelines(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    step = parsed["pipelines"]["default"][0]["step"]
    assert step["image"] == "python:3.11-slim"


def test_script_is_nested_inside_step_not_sibling():
    """Regression test : script/services doivent etre DANS le mapping
    'step', pas des freres du 'step:' dans l'item de liste."""
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_bitbucket_pipelines(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    item = parsed["pipelines"]["default"][0]
    assert list(item.keys()) == ["step"]
    assert "script" in item["step"]


def test_docker_hub_deploy_step_has_services_docker():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_bitbucket_pipelines(
        stacks, jobs=["test"], deploy={"targets": ["docker_hub"], "docker_image": "user/app"}
    )
    parsed = _parse(yaml_text)

    deploy_step = parsed["pipelines"]["branches"]["main"][-1]["step"]
    assert deploy_step["name"] == "deploy-docker_hub"
    assert deploy_step["services"] == ["docker"]
    assert "user/app:latest" in yaml_text


def test_ssh_deploy_uses_variables_not_hardcoded():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_bitbucket_pipelines(
        stacks, jobs=["test"], deploy={"targets": ["ssh"], "deploy_path": "/var/www/app"}
    )
    assert "$SSH_HOST" in yaml_text
    assert "$SSH_USER" in yaml_text
    assert "$SSH_PRIVATE_KEY" in yaml_text
    assert "/var/www/app" in yaml_text


def test_aws_s3_skipped_without_node_stack():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_bitbucket_pipelines(
        stacks, jobs=["test"], deploy={"targets": ["aws_s3", "docker_hub"]}
    )
    parsed = _parse(yaml_text)

    names = _step_names(parsed["pipelines"]["branches"]["main"])
    assert "deploy-aws_s3" not in names
    assert "deploy-docker_hub" in names


def test_aws_s3_present_with_node_stack():
    stacks = [{"language": "node", "version": "20", "package_manager": "npm"}]
    yaml_text = generate_bitbucket_pipelines(
        stacks, jobs=["test"], deploy={"targets": ["aws_s3"], "s3_bucket": "mybucket"}
    )
    parsed = _parse(yaml_text)

    names = _step_names(parsed["pipelines"]["branches"]["main"])
    assert "deploy-aws_s3" in names
    assert "mybucket" in yaml_text


def test_vercel_deploy_step():
    stacks = [{"language": "node", "version": "20", "package_manager": "npm"}]
    yaml_text = generate_bitbucket_pipelines(stacks, jobs=["test"], deploy={"targets": ["vercel"]})
    parsed = _parse(yaml_text)

    names = _step_names(parsed["pipelines"]["branches"]["main"])
    assert "deploy-vercel" in names
    assert "vercel --token $VERCEL_TOKEN" in yaml_text


def test_deploy_cible_inconnue_ignoree():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_bitbucket_pipelines(
        stacks, jobs=["test"], deploy={"targets": ["cible-inconnue", "docker_hub"]}
    )
    parsed = _parse(yaml_text)
    names = _step_names(parsed["pipelines"]["branches"]["main"])
    assert "deploy-docker_hub" in names


def test_langage_non_pris_en_charge_ne_genere_aucun_step():
    stacks = [{"language": "cobol", "version": "1.0", "package_manager": ""}]
    with pytest.raises(ValueError, match="Aucun step genere"):
        generate_bitbucket_pipelines(stacks, jobs=["test"])


def test_langage_sans_commande_installation_utilise_le_repli():
    from modules.cicd.bitbucket_core import _get_install_cmd
    assert _get_install_cmd("cobol", "") == "echo 'Aucune commande d-installation definie pour ce langage'"


def test_cible_de_deploiement_cataloguee_mais_non_geree_est_ignoree(monkeypatch):
    """Garde-fou defensif : voir teamcity_core, meme principe."""
    from modules.cicd import bitbucket_core
    monkeypatch.setitem(
        bitbucket_core.DEPLOY_TARGETS, "mystere",
        {"requires_language": None, "label": "Cible mystere"},
    )
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_bitbucket_pipelines(
        stacks, jobs=["test"], deploy={"targets": ["mystere", "docker_hub"]}
    )
    parsed = _parse(yaml_text)
    names = _step_names(parsed["pipelines"]["branches"]["main"])
    assert "deploy-docker_hub" in names
    assert "deploy-mystere" not in names


def test_deploy_steps_placed_under_branches_not_default():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_bitbucket_pipelines(
        stacks, jobs=["test"], deploy={"targets": ["docker_hub"]}, branches=["main"]
    )
    parsed = _parse(yaml_text)

    default_names = _step_names(parsed["pipelines"]["default"])
    branch_names = _step_names(parsed["pipelines"]["branches"]["main"])

    assert "deploy-docker_hub" not in default_names
    assert "deploy-docker_hub" in branch_names
    # les steps lint/test/build restent aussi presents sur la branche de deploiement
    assert "test-python" in branch_names


def test_no_deploy_means_no_branches_section():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_bitbucket_pipelines(stacks, jobs=["test"])
    parsed = _parse(yaml_text)

    assert "branches" not in parsed["pipelines"]


def test_schedule_cron_adds_explanatory_comment():
    stacks = [{"language": "python", "version": "3.12", "package_manager": "pip"}]
    yaml_text = generate_bitbucket_pipelines(stacks, jobs=["test"], schedule_cron="0 3 * * *")

    assert "0 3 * * *" in yaml_text
    assert "Schedules" in yaml_text
    # doit rester du YAML valide malgre le commentaire d'en-tete
    _parse(yaml_text)


def test_badge_markdown_format():
    badge = generate_badge_markdown("myteam", "myrepo", branch="develop")
    assert badge.startswith("[![Build Status]")
    assert "myteam/myrepo/develop" in badge
    assert "bitbucket.org/myteam/myrepo" in badge
