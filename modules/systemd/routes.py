"""
modules/systemd/routes.py
--------------------------
Blueprint Flask du module systemd (monte sous /systemd).
"""

from flask import Blueprint, render_template, request, jsonify

from modules.systemd.core import (
    generate_units,
    list_presets,
    get_preset,
    SUPPORTED_MODES,
    SERVICE_TYPES,
    RESTART_POLICIES,
)

bp = Blueprint("systemd", __name__, url_prefix="/systemd")


@bp.route("/")
def index():
    return render_template(
        "systemd.html",
        modes=SUPPORTED_MODES,
        service_types=SERVICE_TYPES,
        restart_policies=RESTART_POLICIES,
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
    """Genere la ou les unites systemd a partir du formulaire."""
    config = request.get_json(force=True) or {}

    try:
        units = generate_units(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    unit_list = [{"filename": fn, "content": ct} for fn, ct in units.items()]
    combined = "\n".join(units.values())
    name = (config.get("name") or "unit").strip()

    return jsonify({
        "units": unit_list,
        "combined": combined,
        "name": name,
    })
