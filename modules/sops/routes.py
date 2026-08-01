"""
modules/sops/routes.py
-----------------------
Blueprint Flask du module sops (monte sous /sops).
"""

from flask import Blueprint, jsonify, render_template, request

from modules.sops.core import (
    INPUT_TYPES,
    PRESETS,
    generate_sops,
    get_preset,
    list_presets,
)

bp = Blueprint("sops", __name__, url_prefix="/sops")


@bp.route("/")
def index():
    return render_template(
        "sops.html",
        presets={name: p["label"] for name, p in PRESETS.items()},
        input_types=[t for t in INPUT_TYPES if t],
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
    """Genere le(s) fichier(s) SOPS a partir du formulaire."""
    config = request.get_json(force=True) or {}

    try:
        files = generate_sops(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    file_list = [{"filename": fn, "content": ct} for fn, ct in files.items()]

    return jsonify({"files": file_list})
