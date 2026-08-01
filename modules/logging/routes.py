"""
modules/logging/routes.py
----------------------------
Blueprint Flask du module logging (monte sous /logging).
"""

from flask import Blueprint, jsonify, render_template, request

from modules.logging.core import (
    SUPPORTED_BACKENDS,
    generate_logging,
    get_preset,
    list_presets,
)

bp = Blueprint("logging_forge", __name__, url_prefix="/logging")


@bp.route("/")
def index():
    return render_template(
        "logging.html",
        backends=SUPPORTED_BACKENDS,
        presets=list_presets(),
    )


@bp.route("/api/presets")
def api_presets():
    return jsonify({"presets": list_presets()})


@bp.route("/api/preset/<nom>")
def api_preset(nom):
    try:
        preset = get_preset(nom)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify(preset)


@bp.route("/api/generate", methods=["POST"])
def api_generate():
    """Genere le fichier de logging a partir du formulaire."""
    config = request.get_json(force=True) or {}

    try:
        files = generate_logging(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    file_list = [{"filename": fn, "content": ct} for fn, ct in files.items()]

    return jsonify({"files": file_list})
