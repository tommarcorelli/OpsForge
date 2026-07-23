"""
modules/nginx/routes.py
------------------------
Blueprint Flask du module Nginx (monte sous /nginx).
"""

from flask import Blueprint, render_template, request, jsonify

from modules.nginx.core import (
    generate_config,
    generate,
    list_presets,
    get_preset,
    SUPPORTED_MODES,
    LB_ALGORITHMS,
    SUPPORTED_TARGETS,
    TARGET_MODES,
)

bp = Blueprint("nginx", __name__, url_prefix="/nginx")


@bp.route("/")
def index():
    return render_template(
        "nginx.html",
        modes=SUPPORTED_MODES,
        algorithms=LB_ALGORITHMS,
        presets=list_presets(),
        targets=SUPPORTED_TARGETS,
        target_modes=TARGET_MODES,
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
    """Genere la config a partir des choix faits dans le formulaire, pour la
    cible demandee (nginx [defaut], caddy ou traefik)."""
    config = request.get_json(force=True) or {}
    target = (config.pop("target", None) or "nginx").strip()

    try:
        conf_text = generate(config, target=target)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    server_name = (config.get("server_name") or "app").strip()
    ext = {"nginx": "conf", "caddy": "Caddyfile", "traefik": "yml"}.get(target, "conf")
    filename = "Caddyfile" if target == "caddy" else f"{server_name}.{ext}"

    return jsonify({
        "config": conf_text,
        "filename": filename,
        "target": target,
    })
