"""
modules/terraform/routes.py
---------------------------
Blueprint Flask du module Terraform (monte sous /terraform). v0 — a enrichir.
"""

from flask import Blueprint, render_template, request, jsonify

from modules.terraform.core import (
    generate_terraform,
    valider_config,
    SUPPORTED_PROVIDERS,
)

bp = Blueprint("terraform", __name__, url_prefix="/terraform")


@bp.route("/")
def index():
    return render_template("terraform.html", providers=list(SUPPORTED_PROVIDERS))


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
