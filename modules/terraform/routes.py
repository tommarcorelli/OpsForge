"""
modules/terraform/routes.py
---------------------------
Blueprint Flask du module Terraform (monté sous /terraform).

Ce blueprint sert trois moteurs de génération distincts derrière un même
builder de ressources cliente :
- "provider" parmi SUPPORTED_PROVIDERS (aws, google, azurerm, docker, local)
  -> core.py, sortie HCL (main.tf).
- "provider" == "cloudformation" -> cloudformation_core.py, sortie YAML
  (catalogue AWS-only à part, schéma resources[].properties).
- "provider" == "pulumi-<cloud>" (pulumi-aws/google/azurerm/docker, pas de
  "local" — pas d'équivalent Pulumi officiel) -> pulumi_core.py, sortie
  Python (__main__.py). Réutilise directement le catalogue Terraform du
  cloud correspondant (mêmes types/args), contrairement à CloudFormation.

Les presets CloudFormation sont préfixés "cfn-", les presets Pulumi
"pulumi:" (deux ponctuations différentes du tiret des valeurs de
provider "pulumi-aws" etc., pour ne pas les confondre) — aucun des trois
espaces de noms n'entre en collision avec les presets Terraform bruts.
"""

import io
import zipfile

from flask import Blueprint, render_template, request, jsonify, send_file

from modules.terraform.core import (
    generate_terraform,
    generate_terraform_files,
    valider_config,
    obtenir_preset,
    SUPPORTED_PROVIDERS,
    RESOURCE_CATALOG,
    PRESETS,
)
from modules.terraform.cloudformation_core import (
    generate_cloudformation,
    valider_config as valider_config_cfn,
    obtenir_preset as obtenir_preset_cfn,
    RESOURCE_CATALOG as RESOURCE_CATALOG_CFN,
    PRESETS as PRESETS_CFN,
)
from modules.terraform.pulumi_core import (
    generate_pulumi,
    valider_config as valider_config_pulumi,
    obtenir_preset as obtenir_preset_pulumi,
    PULUMI_PROVIDERS,
    PRESETS as PRESETS_PULUMI,
    OUTPUT_FILENAME as PULUMI_FILENAME,
)

bp = Blueprint("terraform", __name__, url_prefix="/terraform")

CFN_PRESET_PREFIX = "cfn-"
PULUMI_PROVIDER_PREFIX = "pulumi-"
PULUMI_PRESET_PREFIX = "pulumi:"


def _combined_catalog():
    catalog = dict(RESOURCE_CATALOG)
    catalog["cloudformation"] = RESOURCE_CATALOG_CFN
    for cloud in PULUMI_PROVIDERS:
        catalog[f"{PULUMI_PROVIDER_PREFIX}{cloud}"] = RESOURCE_CATALOG.get(cloud, [])
    return catalog


def _combined_presets_labels():
    labels = {k: v["label"] for k, v in PRESETS.items()}
    for k, v in PRESETS_CFN.items():
        labels[f"{CFN_PRESET_PREFIX}{k}"] = f"CloudFormation — {v['label']}"
    for k, v in PRESETS_PULUMI.items():
        labels[f"{PULUMI_PRESET_PREFIX}{k}"] = f"Pulumi — {v['label']}"
    return labels


@bp.route("/")
def index():
    pulumi_providers = [f"{PULUMI_PROVIDER_PREFIX}{cloud}" for cloud in PULUMI_PROVIDERS]
    return render_template(
        "terraform.html",
        providers=list(SUPPORTED_PROVIDERS) + ["cloudformation"] + pulumi_providers,
        catalog=_combined_catalog(),
        presets=_combined_presets_labels(),
    )


@bp.get("/api/catalog")
def api_catalog():
    """Catalogue des types de ressources par provider (pour le builder)."""
    return jsonify(_combined_catalog())


@bp.get("/api/presets")
def api_presets():
    return jsonify(_combined_presets_labels())


@bp.get("/api/preset/<nom>")
def api_preset(nom):
    if nom.startswith(CFN_PRESET_PREFIX):
        try:
            cfg = obtenir_preset_cfn(nom[len(CFN_PRESET_PREFIX):])
        except KeyError:
            return jsonify({"error": f"Preset inconnu : {nom}"}), 404
        cfg["provider"] = "cloudformation"
        # Le builder cote client attend "args" par ressource (vocabulaire
        # Terraform) : on l'alimente depuis "properties" (vocabulaire CFN).
        for res in cfg.get("resources", []):
            res["args"] = res.pop("properties", {})
        return jsonify(cfg)

    if nom.startswith(PULUMI_PRESET_PREFIX):
        try:
            cfg = obtenir_preset_pulumi(nom[len(PULUMI_PRESET_PREFIX):])
        except KeyError:
            return jsonify({"error": f"Preset inconnu : {nom}"}), 404
        cfg["provider"] = f"{PULUMI_PROVIDER_PREFIX}{cfg['provider']}"
        return jsonify(cfg)

    try:
        return jsonify(obtenir_preset(nom))
    except KeyError:
        return jsonify({"error": f"Preset inconnu : {nom}"}), 404


def _cfn_config_from_request(data):
    """Traduit la config du builder partagé (resources[].args) vers le
    schema attendu par cloudformation_core.py (resources[].properties)."""
    config = {
        "resources": [
            {"type": r.get("type"), "name": r.get("name"), "properties": r.get("args") or {}}
            for r in (data.get("resources") or [])
        ],
    }
    if data.get("variables"):
        config["parameters"] = data["variables"]
    if data.get("outputs"):
        config["outputs"] = data["outputs"]
    return config


def _pulumi_config_from_request(data, cloud):
    """Le schema Pulumi reutilise directement resources[].args (meme
    vocabulaire que Terraform HCL) : pas de traduction de cles necessaire,
    juste reinjecter le vrai nom de cloud (sans le prefixe 'pulumi-')."""
    config = {
        "provider": cloud,
        "provider_config": data.get("provider_config") or {},
        "resources": data.get("resources") or [],
    }
    if data.get("outputs"):
        config["outputs"] = data["outputs"]
    return config


@bp.post("/api/generate")
def api_generate():
    data = request.get_json(force=True) or {}
    provider = data.get("provider")

    if provider == "cloudformation":
        cfg = _cfn_config_from_request(data)
        erreurs, avertissements = valider_config_cfn(cfg)
        if erreurs:
            return jsonify({"error": " ; ".join(erreurs), "avertissements": avertissements}), 400
        try:
            contenu = generate_cloudformation(cfg)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({
            "terraform": contenu,
            "filename": "template.yaml",
            "avertissements": avertissements,
        })

    if provider and provider.startswith(PULUMI_PROVIDER_PREFIX):
        cloud = provider[len(PULUMI_PROVIDER_PREFIX):]
        cfg = _pulumi_config_from_request(data, cloud)
        erreurs, avertissements = valider_config_pulumi(cfg)
        if erreurs:
            return jsonify({"error": " ; ".join(erreurs), "avertissements": avertissements}), 400
        try:
            contenu = generate_pulumi(cfg)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({
            "terraform": contenu,
            "filename": PULUMI_FILENAME,
            "avertissements": avertissements,
        })

    config = data
    erreurs, avertissements = valider_config(config)
    if erreurs:
        return jsonify({"error": " ; ".join(erreurs), "avertissements": avertissements}), 400

    try:
        contenu = generate_terraform(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "terraform": contenu,
        "filename": "main.tf",
        "avertissements": avertissements,
    })


@bp.post("/api/download")
def api_download():
    """Regenere puis renvoie le projet genere en telechargement :
    - CloudFormation : un unique fichier template.yaml.
    - Pulumi : un unique fichier __main__.py.
    - Terraform : un .zip (main.tf, et variables.tf / outputs.tf s'ils sont
      non vides)."""
    data = request.get_json(force=True) or {}
    provider = data.get("provider")

    if provider == "cloudformation":
        cfg = _cfn_config_from_request(data)
        erreurs, _ = valider_config_cfn(cfg)
        if erreurs:
            return jsonify({"error": " ; ".join(erreurs)}), 400
        try:
            contenu = generate_cloudformation(cfg)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        buffer = io.BytesIO(contenu.encode("utf-8"))
        return send_file(
            buffer,
            mimetype="text/yaml",
            as_attachment=True,
            download_name="template.yaml",
        )

    if provider and provider.startswith(PULUMI_PROVIDER_PREFIX):
        cloud = provider[len(PULUMI_PROVIDER_PREFIX):]
        cfg = _pulumi_config_from_request(data, cloud)
        erreurs, _ = valider_config_pulumi(cfg)
        if erreurs:
            return jsonify({"error": " ; ".join(erreurs)}), 400
        try:
            contenu = generate_pulumi(cfg)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        buffer = io.BytesIO(contenu.encode("utf-8"))
        return send_file(
            buffer,
            mimetype="text/x-python",
            as_attachment=True,
            download_name=PULUMI_FILENAME,
        )

    config = data
    erreurs, _ = valider_config(config)
    if erreurs:
        return jsonify({"error": " ; ".join(erreurs)}), 400

    try:
        fichiers = generate_terraform_files(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for nom, contenu in fichiers.items():
            zf.writestr(nom, contenu)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="terraform-project.zip",
    )
