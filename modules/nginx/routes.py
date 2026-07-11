"""
modules/nginx/routes.py
------------------------
Blueprint Flask du module Nginx (monte sous /nginx).
"""

from flask import Blueprint, render_template, request, jsonify

from modules.nginx.core import (
    generate_config,
    list_presets,
    get_preset,
    SUPPORTED_MODES,
    LB_ALGORITHMS,
)

bp = Blueprint("nginx", __name__, url_prefix="/nginx")


@bp.route("/")
def index():
    return render_template(
        "nginx.html",
        modes=SUPPORTED_MODES,
        algorithms=LB_ALGORITHMS,
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
    """Genere la config Nginx a partir des choix faits dans le formulaire."""
    config = request.get_json(force=True) or {}

    try:
        conf_text = generate_config(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    server_name = (config.get("server_name") or "app").strip()
    return jsonify({
        "config": conf_text,
        "filename": server_name,
    })
