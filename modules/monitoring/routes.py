"""
modules/monitoring/routes.py
-----------------------------
Blueprint Flask du module Monitoring (monte sous /monitoring).
"""

from flask import Blueprint, render_template, request, jsonify

from modules.monitoring.core import (
    generate_files,
    list_presets,
    get_preset,
    list_rules,
    SUPPORTED_MODES,
    DATASOURCE_TYPES,
)

bp = Blueprint("monitoring", __name__, url_prefix="/monitoring")


@bp.route("/")
def index():
    return render_template(
        "monitoring.html",
        modes=SUPPORTED_MODES,
        datasource_types=DATASOURCE_TYPES,
        rules=list_rules(),
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
    """Genere le(s) fichier(s) de monitoring a partir du formulaire."""
    config = request.get_json(force=True) or {}

    try:
        files = generate_files(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    file_list = [{"filename": fn, "content": ct} for fn, ct in files.items()]
    combined = "\n".join(files.values())
    filename = file_list[0]["filename"] if file_list else "config.yml"

    return jsonify({
        "files": file_list,
        "combined": combined,
        "filename": filename,
    })
