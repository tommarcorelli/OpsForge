"""
modules/ssh/routes.py
---------------------
Blueprint Flask du module ssh (monte sous /ssh).
"""

from flask import Blueprint, jsonify, render_template, request

from modules.ssh.core import (
    PERMIT_ROOT_LOGIN_VALUES,
    PRESETS,
    SUPPORTED_ROLES,
    generate_ssh,
    get_preset,
    list_presets,
    list_presets_by_role,
)

bp = Blueprint("ssh", __name__, url_prefix="/ssh")


@bp.route("/")
def index():
    return render_template(
        "ssh.html",
        roles=SUPPORTED_ROLES,
        presets={name: {"label": p["label"], "role": p["role"]} for name, p in PRESETS.items()},
        permit_root_values=PERMIT_ROOT_LOGIN_VALUES,
    )


@bp.route("/api/presets")
def api_presets():
    role = request.args.get("role")
    if role:
        if role not in SUPPORTED_ROLES:
            return jsonify({"error": f"Role inconnu : '{role}'."}), 400
        return jsonify({"presets": list_presets_by_role(role)})
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
    """Genere le(s) fichier(s) SSH a partir du formulaire."""
    config = request.get_json(force=True) or {}

    try:
        files = generate_ssh(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    file_list = [{"filename": fn, "content": ct} for fn, ct in files.items()]

    return jsonify({"files": file_list})
