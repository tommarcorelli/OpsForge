"""
modules/terraform/routes.py
---------------------------
Blueprint Flask du module Terraform (monté sous /terraform).
"""

from flask import Blueprint, render_template, request, jsonify

from modules.terraform.core import (
    generate_terraform,
    valider_config,
    obtenir_preset,
    SUPPORTED_PROVIDERS,
    RESOURCE_CATALOG,
    PRESETS,
)

bp = Blueprint("terraform", __name__, url_prefix="/terraform")


@bp.route("/")
def index():
    return render_template(
        "terraform.html",
        providers=list(SUPPORTED_PROVIDERS),
        catalog=RESOURCE_CATALOG,
        presets={k: v["label"] for k, v in PRESETS.items()},
    )


@bp.get("/api/catalog")
def api_catalog():
    """Catalogue des types de ressources par provider (pour le builder)."""
    return jsonify(RESOURCE_CATALOG)


@bp.get("/api/presets")
def api_presets():
    return jsonify({k: v["label"] for k, v in PRESETS.items()})


@bp.get("/api/preset/<nom>")
def api_preset(nom):
    try:
        return jsonify(obtenir_preset(nom))
    except KeyError:
        return jsonify({"error": f"Preset inconnu : {nom}"}), 404


@bp.post("/api/generate")
def api_generate():
    config = request.get_json(force=True) or {}

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
