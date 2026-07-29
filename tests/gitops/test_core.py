"""Tests du coeur du module GitOps d'OpsForge (ArgoCD / FluxCD)."""

import os

import pytest
import yaml

from modules.gitops.core import (
    PRESETS,
    generate_argocd_application,
    generate_files,
    generate_flux_manifests,
    get_preset,
    list_presets,
    list_source_types,
    list_tools,
    validate_config,
    write_files,
)


def _base_config(**overrides):
    config = {
        "tool": "argocd",
        "app_name": "mon-app",
        "namespace": "mon-app",
        "repo_url": "https://github.com/monorg/mon-repo.git",
        "path": "k8s/overlays/prod",
        "revision": "main",
        "source_type": "raw",
    }
    config.update(overrides)
    return config


# --------------------------------------------------------------------------
# validate_config
# --------------------------------------------------------------------------
def test_config_valide_ne_retourne_aucune_erreur():
    assert validate_config(_base_config()) == []


def test_config_non_dict_retourne_une_erreur():
    assert validate_config("pas un dict") != []
    assert validate_config(None) != []


def test_tool_manquant_est_une_erreur():
    config = _base_config()
    del config["tool"]
    errors = validate_config(config)
    assert any("tool" in e for e in errors)


def test_tool_inconnu_est_une_erreur():
    errors = validate_config(_base_config(tool="jenkins"))
    assert any("tool inconnu" in e for e in errors)


def test_app_name_manquant_est_une_erreur():
    config = _base_config()
    del config["app_name"]
    errors = validate_config(config)
    assert any("app_name" in e for e in errors)


@pytest.mark.parametrize("bad_name", ["MonApp", "mon_app", "-mon-app", "mon-app-", "a" * 64])
def test_app_name_invalide_est_une_erreur(bad_name):
    errors = validate_config(_base_config(app_name=bad_name))
    assert any("app_name invalide" in e for e in errors)


def test_repo_url_manquant_est_une_erreur():
    config = _base_config()
    del config["repo_url"]
    errors = validate_config(config)
    assert any("repo_url" in e for e in errors)


def test_source_type_inconnu_est_une_erreur():
    errors = validate_config(_base_config(source_type="svn"))
    assert any("source_type inconnu" in e for e in errors)


def test_helm_sans_chart_name_est_une_erreur():
    errors = validate_config(_base_config(source_type="helm"))
    assert any("helm_chart_name" in e for e in errors)


def test_helm_avec_chart_name_est_valide():
    errors = validate_config(_base_config(source_type="helm", helm_chart_name="mon-app"))
    assert errors == []


def test_namespace_absent_retombe_sur_app_name():
    config = _base_config()
    del config["namespace"]
    assert validate_config(config) == []


# --------------------------------------------------------------------------
# generate_argocd_application
# --------------------------------------------------------------------------
def test_argocd_application_genere_un_yaml_valide():
    yaml_text = generate_argocd_application(_base_config())
    doc = yaml.safe_load(yaml_text)
    assert doc["kind"] == "Application"
    assert doc["apiVersion"] == "argoproj.io/v1alpha1"
    assert doc["metadata"]["name"] == "mon-app"


def test_argocd_application_source_champs():
    doc = yaml.safe_load(generate_argocd_application(_base_config()))
    source = doc["spec"]["source"]
    assert source["repoURL"] == "https://github.com/monorg/mon-repo.git"
    assert source["path"] == "k8s/overlays/prod"
    assert source["targetRevision"] == "main"


def test_argocd_application_destination():
    doc = yaml.safe_load(generate_argocd_application(_base_config(namespace="prod")))
    dest = doc["spec"]["destination"]
    assert dest["namespace"] == "prod"
    assert dest["server"] == "https://kubernetes.default.svc"


def test_argocd_application_auto_sync_active_par_defaut():
    doc = yaml.safe_load(generate_argocd_application(_base_config()))
    automated = doc["spec"]["syncPolicy"]["automated"]
    assert automated["selfHeal"] is True
    assert automated["prune"] is True


def test_argocd_application_sync_manuelle():
    doc = yaml.safe_load(generate_argocd_application(_base_config(auto_sync=False)))
    assert "automated" not in doc["spec"]["syncPolicy"]


def test_argocd_application_create_namespace_sync_option():
    doc = yaml.safe_load(generate_argocd_application(_base_config(create_namespace=True)))
    assert "CreateNamespace=true" in doc["spec"]["syncPolicy"]["syncOptions"]


def test_argocd_application_sans_create_namespace():
    doc = yaml.safe_load(generate_argocd_application(_base_config(create_namespace=False)))
    sync_options = doc["spec"]["syncPolicy"].get("syncOptions", [])
    assert "CreateNamespace=true" not in sync_options


def test_argocd_application_kustomize_ajoute_prune_propagation():
    doc = yaml.safe_load(generate_argocd_application(_base_config(source_type="kustomize")))
    assert "PrunePropagationPolicy=foreground" in doc["spec"]["syncPolicy"]["syncOptions"]


def test_argocd_application_helm_values_type_preserve():
    config = _base_config(
        source_type="helm",
        helm_chart_name="mon-app",
        helm_values={"replicaCount": 3, "enabled": True, "ratio": 1.5, "image": "repo:tag"},
        helm_value_files=["values-prod.yaml"],
    )
    doc = yaml.safe_load(generate_argocd_application(config))
    helm = doc["spec"]["source"]["helm"]
    assert helm["valueFiles"] == ["values-prod.yaml"]
    values = yaml.safe_load(helm["values"])
    assert values == {"replicaCount": 3, "enabled": True, "ratio": 1.5, "image": "repo:tag"}


def test_argocd_application_project_personnalise():
    doc = yaml.safe_load(generate_argocd_application(_base_config(project="mon-projet")))
    assert doc["spec"]["project"] == "mon-projet"


def test_argocd_application_invalide_leve_value_error():
    with pytest.raises(ValueError):
        generate_argocd_application({"tool": "argocd"})


# --------------------------------------------------------------------------
# generate_flux_manifests
# --------------------------------------------------------------------------
def test_flux_raw_genere_gitrepository_et_kustomization():
    fichiers = generate_flux_manifests(_base_config(tool="flux"))
    assert set(fichiers.keys()) == {"flux-gitrepository.yaml", "flux-kustomization.yaml"}

    git_doc = yaml.safe_load(fichiers["flux-gitrepository.yaml"])
    assert git_doc["kind"] == "GitRepository"
    assert git_doc["spec"]["url"] == "https://github.com/monorg/mon-repo.git"
    assert git_doc["spec"]["ref"]["branch"] == "main"

    kustomization_doc = yaml.safe_load(fichiers["flux-kustomization.yaml"])
    assert kustomization_doc["kind"] == "Kustomization"
    assert kustomization_doc["spec"]["path"] == "k8s/overlays/prod"
    assert kustomization_doc["spec"]["sourceRef"]["name"] == "mon-app"


def test_flux_helm_genere_gitrepository_et_helmrelease():
    config = _base_config(tool="flux", source_type="helm", helm_chart_name="mon-app", path="charts/mon-app")
    fichiers = generate_flux_manifests(config)
    assert set(fichiers.keys()) == {"flux-gitrepository.yaml", "flux-helmrelease.yaml"}

    hr_doc = yaml.safe_load(fichiers["flux-helmrelease.yaml"])
    assert hr_doc["kind"] == "HelmRelease"
    assert hr_doc["spec"]["chart"]["spec"]["chart"] == "charts/mon-app"
    assert hr_doc["spec"]["chart"]["spec"]["sourceRef"]["kind"] == "GitRepository"


def test_flux_helmrelease_values_type_preserve():
    config = _base_config(
        tool="flux", source_type="helm", helm_chart_name="mon-app",
        helm_values={"replicaCount": 3, "enabled": False},
    )
    fichiers = generate_flux_manifests(config)
    hr_doc = yaml.safe_load(fichiers["flux-helmrelease.yaml"])
    assert hr_doc["spec"]["values"] == {"replicaCount": 3, "enabled": False}


def test_flux_kustomization_prune():
    fichiers = generate_flux_manifests(_base_config(tool="flux", prune=False))
    doc = yaml.safe_load(fichiers["flux-kustomization.yaml"])
    assert doc["spec"]["prune"] is False


def test_flux_interval_personnalise():
    fichiers = generate_flux_manifests(_base_config(tool="flux", interval="10m"))
    git_doc = yaml.safe_load(fichiers["flux-gitrepository.yaml"])
    assert git_doc["spec"]["interval"] == "10m"


def test_flux_invalide_leve_value_error():
    with pytest.raises(ValueError):
        generate_flux_manifests({"tool": "flux"})


# --------------------------------------------------------------------------
# generate_files (dispatch)
# --------------------------------------------------------------------------
def test_generate_files_dispatch_argocd():
    fichiers = generate_files(_base_config(tool="argocd"))
    assert list(fichiers.keys()) == ["argocd-application.yaml"]


def test_generate_files_dispatch_flux():
    fichiers = generate_files(_base_config(tool="flux"))
    assert "flux-gitrepository.yaml" in fichiers


def test_generate_files_invalide_leve_value_error():
    with pytest.raises(ValueError):
        generate_files({"tool": "argocd"})


# --------------------------------------------------------------------------
# write_files
# --------------------------------------------------------------------------
def test_write_files_ecrit_sur_disque(tmp_path):
    paths = write_files(_base_config(tool="argocd"), str(tmp_path))
    assert len(paths) == 1
    assert os.path.isfile(paths[0])
    with open(paths[0]) as f:
        assert "kind: Application" in f.read()


def test_write_files_flux_ecrit_plusieurs_fichiers(tmp_path):
    paths = write_files(_base_config(tool="flux"), str(tmp_path))
    assert len(paths) == 2
    for p in paths:
        assert os.path.isfile(p)


def test_write_files_cree_les_dossiers_manquants(tmp_path):
    output_dir = str(tmp_path / "sous" / "dossier")
    paths = write_files(_base_config(tool="argocd"), output_dir)
    assert os.path.isfile(paths[0])


# --------------------------------------------------------------------------
# Listing helpers
# --------------------------------------------------------------------------
def test_list_tools():
    assert set(list_tools()) == {"argocd", "flux"}


def test_list_source_types():
    assert set(list_source_types()) == {"raw", "kustomize", "helm"}


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------
def test_list_presets_correspond_au_dict_presets():
    assert set(list_presets()) == set(PRESETS.keys())


def test_get_preset_inconnu_leve_value_error():
    with pytest.raises(ValueError):
        get_preset("ce-preset-n-existe-pas")


def test_get_preset_retourne_une_copie():
    p1 = get_preset("argocd-raw-manifests")
    p1["app_name"] = "modifie"
    p2 = get_preset("argocd-raw-manifests")
    assert p2["app_name"] != "modifie"


@pytest.mark.parametrize("nom_preset", list(PRESETS.keys()))
def test_tous_les_presets_sont_valides(nom_preset):
    config = get_preset(nom_preset)
    assert validate_config(config) == []


@pytest.mark.parametrize("nom_preset", list(PRESETS.keys()))
def test_tous_les_presets_generent_un_yaml_valide(nom_preset):
    config = get_preset(nom_preset)
    fichiers = generate_files(config)
    assert fichiers
    for nom, contenu in fichiers.items():
        doc = yaml.safe_load(contenu)
        assert doc is not None, f"{nom_preset}/{nom} n'a pas produit de YAML valide"
