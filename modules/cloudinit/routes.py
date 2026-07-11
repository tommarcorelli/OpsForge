"""
modules/cloudinit/routes.py
----------------------------
Blueprint Flask du module cloud-init (monte sous /cloudinit).
"""

from flask import Blueprint, render_template, request, jsonify

from modules.cloudinit.core import (
    generate_cloud_config,
    list_presets,
    get_preset,
    OUTPUT_FILENAME,
)

bp = Blueprint("cloudinit", __name__, url_prefix="/cloudinit")


@bp.route("/")
def index():
    return render_template("cloudinit.html", presets=list_presets())


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
    """Genere le fichier cloud-config a partir du formulaire."""
    config = request.get_json(force=True) or {}

    try:
        content = generate_cloud_config(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "combined": content,
        "filename": OUTPUT_FILENAME,
    })
