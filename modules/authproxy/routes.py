"""
modules/authproxy/routes.py
----------------------------
Blueprint Flask du module authproxy (monte sous /authproxy).
"""

from flask import Blueprint, jsonify, render_template, request

from modules.authproxy.core import (
    AUTHELIA_POLICIES,
    OAUTH2_PROXY_PROVIDERS,
    PRESETS,
    SUPPORTED_ENGINES,
    generate_authproxy,
    get_preset,
    list_presets,
    list_presets_by_engine,
)

bp = Blueprint("authproxy", __name__, url_prefix="/authproxy")


@bp.route("/")
def index():
    return render_template(
        "authproxy.html",
        engines=SUPPORTED_ENGINES,
        presets={name: {"label": p["label"], "engine": p["engine"]} for name, p in PRESETS.items()},
        oauth2_providers=OAUTH2_PROXY_PROVIDERS,
        authelia_policies=AUTHELIA_POLICIES,
    )


@bp.route("/api/presets")
def api_presets():
    engine = request.args.get("engine")
    if engine:
        if engine not in SUPPORTED_ENGINES:
            return jsonify({"error": f"Moteur inconnu : '{engine}'."}), 400
        return jsonify({"presets": list_presets_by_engine(engine)})
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
    """Genere le(s) fichier(s) d'authentification a partir du formulaire."""
    config = request.get_json(force=True) or {}

    try:
        files = generate_authproxy(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    file_list = [{"filename": fn, "content": ct} for fn, ct in files.items()]

    return jsonify({"files": file_list})
