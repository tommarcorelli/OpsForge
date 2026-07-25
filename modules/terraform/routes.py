"""
modules/terraform/routes.py
---------------------------
Blueprint Flask du module Terraform (monté sous /terraform).

Depuis l'ajout du format CloudFormation, ce blueprint sert deux moteurs de
génération distincts derrière un même builder de ressources cliente :
- "provider" parmi SUPPORTED_PROVIDERS (aws, google, azurerm, docker, local)
  -> core.py, sortie HCL (main.tf).
- "provider" == "cloudformation" -> cloudformation_core.py, sortie YAML.
Les presets CloudFormation sont exposés avec un préfixe "cfn-" pour ne pas
entrer en collision avec les presets Terraform de même nom (ex: "ec2-web"
existe des deux côtés, avec un schéma de config différent).
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

bp = Blueprint("terraform", __name__, url_prefix="/terraform")

CFN_PRESET_PREFIX = "cfn-"


def _combined_catalog():
    catalog = dict(RESOURCE_CATALOG)
    catalog["cloudformation"] = RESOURCE_CATALOG_CFN
    return catalog


def _combined_presets_labels():
    labels = {k: v["label"] for k, v in PRESETS.items()}
    for k, v in PRESETS_CFN.items():
        labels[f"{CFN_PRESET_PREFIX}{k}"] = f"CloudFormation — {v['label']}"
    return labels


@bp.route("/")
def index():
    return render_template(
        "terraform.html",
        providers=list(SUPPORTED_PROVIDERS) + ["cloudformation"],
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


@bp.post("/api/generate")
def api_generate():
    data = request.get_json(force=True) or {}

    if data.get("provider") == "cloudformation":
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
    - Terraform : un .zip (main.tf, et variables.tf / outputs.tf s'ils sont
      non vides)."""
    data = request.get_json(force=True) or {}

    if data.get("provider") == "cloudformation":
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
