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
from modules.cloudinit.ignition_core import (
    generate_ignition,
    OUTPUT_FILENAME as IGNITION_FILENAME,
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
    """Genere le fichier cloud-config (ou Ignition) a partir du formulaire."""
    data = request.get_json(force=True) or {}
    fmt = (data.pop("format", None) or "cloud-config").strip()

    if fmt == "ignition":
        try:
            content = generate_ignition(data)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({
            "combined": content,
            "filename": IGNITION_FILENAME,
            "format": "ignition",
        })

    try:
        content = generate_cloud_config(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "combined": content,
        "filename": OUTPUT_FILENAME,
        "format": "cloud-config",
    })
