import json

import pytest
import yaml

from modules.cicd.deps_core import (
    FILENAMES,
    generate_dependabot_yaml,
    generate_deps_config,
    generate_renovate_json,
    list_schedules,
    list_tools,
    resolve_ecosystems,
    write_deps_config,
)

PYTHON_STACK = [{"language": "python", "package_manager": "pip"}]
NODE_STACK = [{"language": "node", "package_manager": "npm"}]


def test_list_tools_and_schedules():
    assert list_tools() == ["dependabot", "renovate"]
    assert "weekly" in list_schedules()


# ---------------------------------------------------------------------------
# Resolution des ecosystemes
# ---------------------------------------------------------------------------
def test_resolve_ecosystems_maps_languages_for_dependabot():
    stacks = [{"language": "python"}, {"language": "node"}, {"language": "go"}]
    ecosystems = resolve_ecosystems(stacks, "dependabot", include_github_actions=False)
    assert ecosystems == ["pip", "npm", "gomod"]


def test_resolve_ecosystems_java_depends_on_package_manager():
    maven = resolve_ecosystems(
        [{"language": "java", "package_manager": "maven"}], "dependabot", include_github_actions=False
    )
    gradle = resolve_ecosystems(
        [{"language": "java", "package_manager": "gradle"}], "dependabot", include_github_actions=False
    )
    assert maven == ["maven"]
    assert gradle == ["gradle"]


def test_resolve_ecosystems_ignores_unknown_language():
    ecosystems = resolve_ecosystems(
        [{"language": "cobol"}, {"language": "node"}], "dependabot", include_github_actions=False
    )
    assert ecosystems == ["npm"]


def test_resolve_ecosystems_deduplicates():
    stacks = [{"language": "node"}, {"language": "node"}]
    assert resolve_ecosystems(stacks, "dependabot", include_github_actions=False) == ["npm"]


def test_resolve_ecosystems_adds_extras():
    ecosystems = resolve_ecosystems(
        NODE_STACK, "dependabot", include_github_actions=True, include_docker=True
    )
    assert ecosystems == ["npm", "github-actions", "docker"]


def test_resolve_ecosystems_renovate_uses_manager_lists():
    managers = resolve_ecosystems(PYTHON_STACK, "renovate", include_github_actions=False)
    assert "pip_requirements" in managers
    assert "poetry" in managers


# ---------------------------------------------------------------------------
# Dependabot
# ---------------------------------------------------------------------------
def test_dependabot_output_is_valid_yaml_version_2():
    parsed = yaml.safe_load(generate_dependabot_yaml(PYTHON_STACK))
    assert parsed["version"] == 2
    assert isinstance(parsed["updates"], list)


def test_dependabot_one_block_per_ecosystem():
    parsed = yaml.safe_load(generate_dependabot_yaml(PYTHON_STACK, include_github_actions=True))
    ecosystems = [u["package-ecosystem"] for u in parsed["updates"]]
    assert ecosystems == ["pip", "github-actions"]


def test_dependabot_schedule_and_limit_applied():
    parsed = yaml.safe_load(
        generate_dependabot_yaml(NODE_STACK, schedule="daily", open_pr_limit=2, include_github_actions=False)
    )
    block = parsed["updates"][0]
    assert block["schedule"]["interval"] == "daily"
    assert block["open-pull-requests-limit"] == 2


def test_dependabot_target_branch_optional():
    with_branch = yaml.safe_load(
        generate_dependabot_yaml(NODE_STACK, target_branch="develop", include_github_actions=False)
    )
    assert with_branch["updates"][0]["target-branch"] == "develop"

    without = yaml.safe_load(generate_dependabot_yaml(NODE_STACK, include_github_actions=False))
    assert "target-branch" not in without["updates"][0]


def test_dependabot_groups_minor_and_patch_by_default():
    parsed = yaml.safe_load(generate_dependabot_yaml(NODE_STACK, include_github_actions=False))
    groups = parsed["updates"][0]["groups"]
    assert groups["npm-mineures"]["update-types"] == ["minor", "patch"]


def test_dependabot_without_grouping():
    parsed = yaml.safe_load(
        generate_dependabot_yaml(NODE_STACK, group_minor_patch=False, include_github_actions=False)
    )
    assert "groups" not in parsed["updates"][0]


def test_dependabot_github_actions_always_at_repo_root():
    parsed = yaml.safe_load(
        generate_dependabot_yaml(NODE_STACK, directory="/app", include_github_actions=True)
    )
    blocks = {u["package-ecosystem"]: u["directory"] for u in parsed["updates"]}
    assert blocks["npm"] == "/app"
    # Les workflows vivent dans .github/, pas dans le dossier du code.
    assert blocks["github-actions"] == "/"


def test_dependabot_rejects_unknown_schedule():
    with pytest.raises(ValueError, match="Frequence inconnue"):
        generate_dependabot_yaml(NODE_STACK, schedule="hourly")


def test_dependabot_rejects_empty_ecosystems():
    with pytest.raises(ValueError, match="Aucun ecosysteme"):
        generate_dependabot_yaml([{"language": "cobol"}], include_github_actions=False)


# ---------------------------------------------------------------------------
# Renovate
# ---------------------------------------------------------------------------
def test_renovate_output_is_valid_json_with_schema():
    parsed = json.loads(generate_renovate_json(NODE_STACK))
    assert parsed["$schema"].endswith("renovate-schema.json")
    assert "config:recommended" in parsed["extends"]


def test_renovate_enabled_managers_follow_stacks():
    parsed = json.loads(generate_renovate_json(NODE_STACK, include_github_actions=True))
    assert parsed["enabledManagers"] == ["npm", "github-actions"]


def test_renovate_schedule_is_a_time_window():
    parsed = json.loads(generate_renovate_json(NODE_STACK, schedule="weekly"))
    assert parsed["schedule"] == ["before 5am on monday"]


def test_renovate_groups_minor_updates_and_isolates_major():
    parsed = json.loads(generate_renovate_json(NODE_STACK))
    rules = parsed["packageRules"]
    minor = next(r for r in rules if r.get("groupName"))
    major = next(r for r in rules if r["matchUpdateTypes"] == ["major"])
    assert minor["matchUpdateTypes"] == ["minor", "patch"]
    assert "breaking" in major["labels"]


def test_renovate_without_grouping_keeps_only_major_rule():
    parsed = json.loads(generate_renovate_json(NODE_STACK, group_minor_patch=False))
    assert all("groupName" not in r for r in parsed["packageRules"])


def test_renovate_security_updates_are_not_throttled():
    parsed = json.loads(generate_renovate_json(NODE_STACK))
    assert parsed["vulnerabilityAlerts"]["schedule"] == ["at any time"]


def test_renovate_base_branch_optional():
    parsed = json.loads(generate_renovate_json(NODE_STACK, target_branch="develop"))
    assert parsed["baseBranches"] == ["develop"]
    assert "baseBranches" not in json.loads(generate_renovate_json(NODE_STACK))


# ---------------------------------------------------------------------------
# Point d'entree commun
# ---------------------------------------------------------------------------
def test_generate_deps_config_returns_expected_filenames():
    assert generate_deps_config(NODE_STACK, tool="dependabot")[0] == FILENAMES["dependabot"]
    assert generate_deps_config(NODE_STACK, tool="renovate")[0] == FILENAMES["renovate"]


def test_generate_deps_config_rejects_unknown_tool():
    with pytest.raises(ValueError, match="Outil de mise a jour inconnu"):
        generate_deps_config(NODE_STACK, tool="greenkeeper")


def test_generate_deps_config_ignores_directory_for_renovate():
    # Renovate balaie tout le depot : 'directory' n'a pas d'equivalent et
    # ne doit pas faire planter l'appel.
    _, content = generate_deps_config(NODE_STACK, tool="renovate", directory="/app")
    assert "directory" not in content


def test_write_deps_config_creates_parent_directory(tmp_path):
    target = tmp_path / "sous-dossier" / "dependabot.yml"
    write_deps_config(NODE_STACK, str(target), tool="dependabot")
    assert target.exists()
    assert "package-ecosystem" in target.read_text(encoding="utf-8")
