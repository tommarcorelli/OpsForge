"""
modules/packer/routes.py
------------------------
Blueprint Flask du module Packer (monte sous /packer).
"""

import io
import zipfile

from flask import Blueprint, render_template, request, jsonify, send_file

from modules.packer.core import (
    generate_packer_template,
    generate_split_files,
    list_presets,
    get_preset,
    list_builders,
    get_builder_info,
    BUILDER_CATALOG,
    OUTPUT_FILENAME,
)

bp = Blueprint("packer", __name__, url_prefix="/packer")


@bp.route("/")
def index():
    builders = {
        key: {
            "label": info["label"],
            "required": info["required"],
            "defaults": info["defaults"],
            "post_processors": info["post_processors"],
        }
        for key, info in BUILDER_CATALOG.items()
    }
    return render_template("packer.html", presets=list_presets(), builders=builders)


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


@bp.route("/api/builders")
def api_builders():
    return jsonify({"builders": list_builders()})


@bp.route("/api/builder/<nom>")
def api_builder(nom):
    try:
        info = get_builder_info(nom)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify(info)


@bp.route("/api/generate", methods=["POST"])
def api_generate():
    """Genere le template Packer HCL2 a partir du formulaire."""
    config = request.get_json(force=True) or {}

    try:
        content = generate_packer_template(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "combined": content,
        "filename": OUTPUT_FILENAME,
    })


@bp.route("/api/download", methods=["POST"])
def api_download():
    """Regenere puis renvoie un .zip du projet Packer en fichiers separes
    (sources.pkr.hcl, build.pkr.hcl, et variables.pkr.hcl s'il y a des variables)."""
    config = request.get_json(force=True) or {}

    try:
        fichiers = generate_split_files(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for nom, contenu in fichiers.items():
            zf.writestr(nom, contenu)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="packer-project.zip",
    )
