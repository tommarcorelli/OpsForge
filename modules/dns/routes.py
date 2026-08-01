"""
modules/dns/routes.py
----------------------
Blueprint Flask du module dns (monte sous /dns).
"""

from flask import Blueprint, jsonify, render_template, request

from modules.dns.core import (
    CAA_TAGS,
    PRESETS,
    RECORD_TYPES,
    SUPPORTED_ENGINES,
    generate_dns,
    get_preset,
    list_presets,
)

bp = Blueprint("dns_forge", __name__, url_prefix="/dns")


@bp.route("/")
def index():
    return render_template(
        "dns.html",
        engines=SUPPORTED_ENGINES,
        presets={name: p["label"] for name, p in PRESETS.items()},
        record_types=RECORD_TYPES,
        caa_tags=CAA_TAGS,
    )


@bp.route("/api/presets")
def api_presets():
    return jsonify({"presets": list_presets()})


@bp.route("/api/preset/<nom>")
def api_preset(nom):
    engine = request.args.get("engine")
    try:
        preset = get_preset(nom, engine=engine)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify(preset)


@bp.route("/api/generate", methods=["POST"])
def api_generate():
    """Genere le fichier DNS a partir du formulaire."""
    config = request.get_json(force=True) or {}

    try:
        files = generate_dns(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    file_list = [{"filename": fn, "content": ct} for fn, ct in files.items()]

    return jsonify({"files": file_list})
