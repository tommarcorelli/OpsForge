"""
modules/firewall/routes.py
----------------------------
Blueprint Flask du module firewall (monte sous /firewall).
"""

from flask import Blueprint, jsonify, render_template, request

from modules.firewall.core import (
    SUPPORTED_BACKENDS,
    generate_firewall,
    get_preset,
    list_presets,
)

bp = Blueprint("firewall", __name__, url_prefix="/firewall")


@bp.route("/")
def index():
    return render_template(
        "firewall.html",
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
    """Genere le(s) fichier(s) pare-feu (+ fail2ban en option) a partir du formulaire."""
    config = request.get_json(force=True) or {}

    try:
        files = generate_firewall(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    file_list = [{"filename": fn, "content": ct} for fn, ct in files.items()]

    return jsonify({"files": file_list})
