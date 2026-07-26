"""Tests du mode Kustomize (base/ + overlays/) du module Kubernetes d'OpsForge."""

import os

import yaml
import pytest

from modules.k8s.core import (
    generate_kustomize,
    write_kustomize,
    DEFAULT_KUSTOMIZE_OVERLAYS,
)


def _config(**overrides):
    base = {"name": "mon-app", "image": "monuser/mon-app:1.2.3"}
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Structure de base
# --------------------------------------------------------------------------

def test_fichiers_base_presents():
    files = generate_kustomize(_config())
    assert "base/kustomization.yaml" in files
    assert "base/deployment.yaml" in files
    assert "base/service.yaml" in files
    assert "base/ingress.yaml" not in files  # pas d'ingress demande


def test_fichiers_base_avec_ingress():
    files = generate_kustomize(_config(ingress={"host": "app.example.com"}))
    assert "base/ingress.yaml" in files
    base_kustomization = yaml.safe_load(files["base/kustomization.yaml"])
    assert base_kustomization["resources"] == [
        "deployment.yaml", "service.yaml", "ingress.yaml"
    ]


def test_base_kustomization_yaml_valide():
    files = generate_kustomize(_config())
    doc = yaml.safe_load(files["base/kustomization.yaml"])
    assert doc["kind"] == "Kustomization"
    assert doc["resources"] == ["deployment.yaml", "service.yaml"]


def test_base_deployment_et_service_coherents_avec_manifests():
    files = generate_kustomize(_config(replicas=4, container_port=9000))
    dep = yaml.safe_load(files["base/deployment.yaml"])
    assert dep["kind"] == "Deployment"
    assert dep["spec"]["replicas"] == 4
    svc = yaml.safe_load(files["base/service.yaml"])
    assert svc["kind"] == "Service"


# --------------------------------------------------------------------------
# Overlays par defaut (dev / staging / prod)
# --------------------------------------------------------------------------

def test_overlays_par_defaut_presents():
    files = generate_kustomize(_config())
    for env in DEFAULT_KUSTOMIZE_OVERLAYS:
        assert f"overlays/{env}/kustomization.yaml" in files


def test_overlay_dev_patch_replicas_a_un():
    files = generate_kustomize(_config(replicas=5))
    assert "overlays/dev/patch-replicas.yaml" in files
    patch = yaml.safe_load(files["overlays/dev/patch-replicas.yaml"])
    assert patch["kind"] == "Deployment"
    assert patch["metadata"]["name"] == "mon-app"
    assert patch["spec"]["replicas"] == 1

    dev_kustomization = yaml.safe_load(files["overlays/dev/kustomization.yaml"])
    assert dev_kustomization["patches"] == [{"path": "patch-replicas.yaml"}]
    assert dev_kustomization["namePrefix"] == "dev-"
    assert dev_kustomization["resources"] == ["../../base"]


def test_overlay_staging_patch_replicas_a_deux():
    files = generate_kustomize(_config())
    patch = yaml.safe_load(files["overlays/staging/patch-replicas.yaml"])
    assert patch["spec"]["replicas"] == 2


def test_overlay_prod_sans_patch_replicas():
    files = generate_kustomize(_config())
    assert "overlays/prod/patch-replicas.yaml" not in files
    prod_kustomization = yaml.safe_load(files["overlays/prod/kustomization.yaml"])
    assert "patches" not in prod_kustomization
    assert prod_kustomization["namePrefix"] == "prod-"


def test_overlay_kustomization_yaml_valide_pour_chaque_env():
    files = generate_kustomize(_config())
    for env in DEFAULT_KUSTOMIZE_OVERLAYS:
        doc = yaml.safe_load(files[f"overlays/{env}/kustomization.yaml"])
        assert doc["kind"] == "Kustomization"
        assert doc["commonLabels"] == {"app.kubernetes.io/environment": env}


# --------------------------------------------------------------------------
# Overlays personnalises
# --------------------------------------------------------------------------

def test_overlays_liste_de_noms_inconnus_sans_patch():
    files = generate_kustomize(_config(), overlays=["qa"])
    assert "overlays/qa/kustomization.yaml" in files
    assert "overlays/qa/patch-replicas.yaml" not in files
    assert "overlays/dev/kustomization.yaml" not in files  # presets par defaut ecrases


def test_overlays_dict_personnalise_avec_namespace_et_replicas():
    files = generate_kustomize(
        _config(),
        overlays={"prod": {"replicas": 10, "namespace": "prod-ns"}},
    )
    doc = yaml.safe_load(files["overlays/prod/kustomization.yaml"])
    assert doc["namespace"] == "prod-ns"
    patch = yaml.safe_load(files["overlays/prod/patch-replicas.yaml"])
    assert patch["spec"]["replicas"] == 10


def test_overlay_replicas_invalide_leve_value_error():
    with pytest.raises(ValueError):
        generate_kustomize(_config(), overlays={"dev": {"replicas": 0}})


def test_config_invalide_leve_value_error():
    with pytest.raises(ValueError):
        generate_kustomize(_config(name="Nom Invalide"))


# --------------------------------------------------------------------------
# Ecriture sur disque
# --------------------------------------------------------------------------

def test_write_kustomize_cree_arborescence(tmp_path):
    output_dir = tmp_path / "mon-app-kustomize"
    written = write_kustomize(_config(), str(output_dir))

    assert (output_dir / "base" / "kustomization.yaml").exists()
    assert (output_dir / "overlays" / "dev" / "kustomization.yaml").exists()
    assert (output_dir / "overlays" / "prod" / "kustomization.yaml").exists()
    assert len(written) == len(generate_kustomize(_config()))
