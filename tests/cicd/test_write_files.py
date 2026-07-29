"""Tests des fonctions d'ecriture disque du module CI/CD (non couvertes
jusqu'ici) : write_workflow (GitHub Actions) et write_gitlab_ci."""

import os

import yaml

from modules.cicd.core import generate_workflow, write_workflow
from modules.cicd.gitlab_core import generate_gitlab_ci, write_gitlab_ci


def _stacks():
    return [{"language": "python"}]


# --------------------------------------------------------------------------
# write_workflow (GitHub Actions)
# --------------------------------------------------------------------------

def test_write_workflow_ecrit_le_fichier(tmp_path):
    output_path = tmp_path / ".github" / "workflows" / "ci.yml"
    resultat = write_workflow(_stacks(), str(output_path), jobs=["test"])

    assert resultat == str(output_path)
    assert output_path.exists()

    contenu = output_path.read_text(encoding="utf-8")
    assert contenu == generate_workflow(_stacks(), jobs=["test"])
    assert yaml.safe_load(contenu) is not None


def test_write_workflow_cree_les_dossiers_manquants(tmp_path):
    output_path = tmp_path / "a" / "b" / "ci.yml"
    write_workflow(_stacks(), str(output_path), jobs=["test"])
    assert output_path.exists()


def test_write_workflow_respecte_le_nom_du_workflow(tmp_path):
    output_path = tmp_path / "ci.yml"
    write_workflow(_stacks(), str(output_path), jobs=["test"], workflow_name="Pipeline Perso")
    data = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert data["name"] == "Pipeline Perso"


# --------------------------------------------------------------------------
# write_gitlab_ci
# --------------------------------------------------------------------------

def test_write_gitlab_ci_ecrit_le_fichier(tmp_path):
    output_path = tmp_path / ".gitlab-ci.yml"
    resultat = write_gitlab_ci(_stacks(), str(output_path), jobs=["test"])

    assert resultat == str(output_path)
    assert output_path.exists()

    contenu = output_path.read_text(encoding="utf-8")
    assert contenu == generate_gitlab_ci(_stacks(), jobs=["test"])
    assert yaml.safe_load(contenu) is not None


def test_write_gitlab_ci_cree_les_dossiers_manquants(tmp_path):
    output_path = tmp_path / "sous" / "dossier" / ".gitlab-ci.yml"
    write_gitlab_ci(_stacks(), str(output_path), jobs=["test"])
    assert os.path.isfile(output_path)


# --------------------------------------------------------------------------
# write_bitbucket_pipelines
# --------------------------------------------------------------------------

def test_write_bitbucket_pipelines_ecrit_le_fichier(tmp_path):
    from modules.cicd.bitbucket_core import generate_bitbucket_pipelines, write_bitbucket_pipelines

    output_path = tmp_path / "bitbucket-pipelines.yml"
    resultat = write_bitbucket_pipelines(_stacks(), str(output_path), jobs=["test"])

    assert resultat == str(output_path)
    assert output_path.exists()

    contenu = output_path.read_text(encoding="utf-8")
    assert contenu == generate_bitbucket_pipelines(_stacks(), jobs=["test"])
    assert yaml.safe_load(contenu) is not None


def test_write_bitbucket_pipelines_cree_les_dossiers_manquants(tmp_path):
    from modules.cicd.bitbucket_core import write_bitbucket_pipelines

    output_path = tmp_path / "sous" / "dossier" / "bitbucket-pipelines.yml"
    write_bitbucket_pipelines(_stacks(), str(output_path), jobs=["test"])
    assert os.path.isfile(output_path)


# --------------------------------------------------------------------------
# write_teamcity_kotlin_dsl
# --------------------------------------------------------------------------

def test_write_teamcity_kotlin_dsl_ecrit_le_fichier(tmp_path):
    from modules.cicd.teamcity_core import generate_teamcity_kotlin_dsl, write_teamcity_kotlin_dsl

    output_path = tmp_path / ".teamcity" / "settings.kts"
    resultat = write_teamcity_kotlin_dsl(_stacks(), str(output_path), jobs=["test"])

    assert resultat == str(output_path)
    assert output_path.exists()

    contenu = output_path.read_text(encoding="utf-8")
    assert contenu == generate_teamcity_kotlin_dsl(_stacks(), jobs=["test"])


def test_write_teamcity_kotlin_dsl_cree_les_dossiers_manquants(tmp_path):
    from modules.cicd.teamcity_core import write_teamcity_kotlin_dsl

    output_path = tmp_path / "sous" / "dossier" / "settings.kts"
    write_teamcity_kotlin_dsl(_stacks(), str(output_path), jobs=["test"])
    assert os.path.isfile(output_path)
