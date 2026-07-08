"""
test_advanced_features.py
--------------------------
Tests pour les fonctionnalites avancees ajoutees apres la v1 :
matrix builds, declenchement planifie (cron), nouvelles cibles de
deploiement (Vercel, AWS S3), et generation de badges Markdown.

Couvre les deux providers (GitHub Actions et GitLab CI).

Lancer avec : pytest tests/test_advanced_features.py -v
"""

import pytest
import yaml

from modules.cicd.core import generate_workflow, generate_badge_markdown
from modules.cicd.gitlab_core import (
    generate_gitlab_ci,
    generate_badge_markdown as generate_gitlab_badge_markdown,
)


# ==============================================================================
# Matrix builds
# ==============================================================================

def test_matrix_build_github_actions():
    stacks = [{"language": "python", "matrix_versions": ["3.10", "3.11", "3.12"]}]
    parsed = yaml.safe_load(generate_workflow(stacks, jobs=["test"]))
    matrix = parsed["jobs"]["test-python"]["strategy"]["matrix"]
    assert matrix["python-version"] == ["3.10", "3.11", "3.12"]


def test_matrix_uses_expression_not_literal_version():
    """La version dans les steps doit referencer ${{ matrix.xxx }},
    pas une version litterale, sinon la matrice ne sert a rien."""
    stacks = [{"language": "python", "matrix_versions": ["3.10", "3.11"]}]
    yaml_text = generate_workflow(stacks, jobs=["test"])
    assert "${{ matrix.python-version }}" in yaml_text


def test_single_version_does_not_trigger_matrix():
    """Une seule version dans matrix_versions ne doit pas generer de
    strategy.matrix (pas la peine pour une seule valeur)."""
    stacks = [{"language": "python", "matrix_versions": ["3.12"]}]
    parsed = yaml.safe_load(generate_workflow(stacks, jobs=["test"]))
    assert "strategy" not in parsed["jobs"]["test-python"]


def test_matrix_build_gitlab():
    stacks = [{"language": "node", "matrix_versions": ["18", "20", "22"]}]
    parsed = yaml.safe_load(generate_gitlab_ci(stacks, jobs=["test"]))
    assert parsed["test-node"]["parallel"]["matrix"] == [{"NODE_VERSION": ["18", "20", "22"]}]


def test_matrix_gitlab_uses_variable_in_image():
    stacks = [{"language": "node", "matrix_versions": ["18", "20"]}]
    yaml_text = generate_gitlab_ci(stacks, jobs=["test"])
    assert "node:$NODE_VERSION-slim" in yaml_text


# ==============================================================================
# Declenchement planifie (cron)
# ==============================================================================

def test_cron_trigger_github_actions():
    stacks = [{"language": "python"}]
    yaml_text = generate_workflow(stacks, jobs=["test"], triggers={"schedule_cron": "0 3 * * *"})
    parsed = yaml.safe_load(yaml_text)
    assert parsed["on"]["schedule"] == [{"cron": "0 3 * * *"}]


def test_no_cron_means_no_schedule_section():
    stacks = [{"language": "python"}]
    yaml_text = generate_workflow(stacks, jobs=["test"])
    assert "schedule:" not in yaml_text


def test_cron_gitlab_adds_explanatory_note():
    """GitLab ne peut pas planifier un pipeline en pur YAML : on doit
    ajouter une note expliquant comment le faire via l'UI."""
    stacks = [{"language": "python"}]
    yaml_text = generate_gitlab_ci(stacks, jobs=["test"], schedule_cron="0 3 * * *")
    assert "Settings > CI/CD > Schedules" in yaml_text
    assert "0 3 * * *" in yaml_text


def test_cron_gitlab_yaml_still_valid_with_comment():
    stacks = [{"language": "python"}]
    yaml_text = generate_gitlab_ci(stacks, jobs=["test"], schedule_cron="0 3 * * *")
    parsed = yaml.safe_load(yaml_text)
    assert "test-python" in parsed


# ==============================================================================
# Nouvelles cibles de deploiement : Vercel, AWS S3
# ==============================================================================

def test_vercel_deploy_github():
    stacks = [{"language": "python"}]
    yaml_text = generate_workflow(stacks, jobs=["test"], deploy={"targets": ["vercel"]})
    assert "VERCEL_TOKEN" in yaml_text
    assert "VERCEL_ORG_ID" in yaml_text


def test_vercel_deploy_gitlab():
    stacks = [{"language": "python"}]
    yaml_text = generate_gitlab_ci(stacks, jobs=["test"], deploy={"targets": ["vercel"]})
    assert "$VERCEL_TOKEN" in yaml_text


def test_aws_s3_requires_node_github():
    stacks = [{"language": "python"}]
    parsed = yaml.safe_load(generate_workflow(stacks, jobs=["build"], deploy={"targets": ["aws_s3"]}))
    assert "deploy-aws_s3" not in parsed["jobs"]


def test_aws_s3_works_with_node_github():
    stacks = [{"language": "node"}]
    yaml_text = generate_workflow(
        stacks, jobs=["build"],
        deploy={"targets": ["aws_s3"], "s3_bucket": "mon-bucket", "aws_region": "eu-west-3"},
    )
    assert "mon-bucket" in yaml_text
    assert "eu-west-3" in yaml_text


def test_aws_s3_gitlab():
    stacks = [{"language": "node"}]
    yaml_text = generate_gitlab_ci(
        stacks, jobs=["build"], deploy={"targets": ["aws_s3"], "s3_bucket": "mon-bucket"}
    )
    assert "mon-bucket" in yaml_text


# ==============================================================================
# Badges Markdown
# ==============================================================================

def test_badge_markdown_github():
    badge = generate_badge_markdown("octocat/hello-world", branch="main")
    assert badge.startswith("[![CI]")
    assert "github.com/octocat/hello-world/actions" in badge
    assert "branch=main" in badge


def test_badge_markdown_github_strips_slashes():
    badge = generate_badge_markdown("/octocat/hello-world/")
    assert "github.com/octocat/hello-world/actions" in badge


def test_badge_markdown_gitlab():
    badge = generate_gitlab_badge_markdown("mygroup/myproject", branch="develop")
    assert "gitlab.com/mygroup/myproject/badges/develop" in badge


def test_badge_markdown_gitlab_custom_host():
    badge = generate_gitlab_badge_markdown("mygroup/myproject", gitlab_host="gitlab.mycompany.com")
    assert "gitlab.mycompany.com" in badge
