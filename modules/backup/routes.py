"""
modules/backup/routes.py
--------------------------
Blueprint Flask du module Backup/Restore (restic / Borg), monte sous /backup.
"""

import io
import zipfile

from flask import Blueprint, jsonify, render_template, request, send_file

from modules.backup.core import (
    generate_files,
    get_preset,
    list_backends,
    list_presets,
    list_schedulers,
    list_tools,
)

bp = Blueprint("backup", __name__, url_prefix="/backup")


@bp.route("/")
def index():
    return render_template(
        "backup.html",
        presets=list_presets(),
        tools=list_tools(),
        backends=list_backends(),
        schedulers=list_schedulers(),
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


@bp.route("/api/catalog")
def api_catalog():
    return jsonify({
        "tools": list_tools(),
        "backends": list_backends(),
        "schedulers": list_schedulers(),
    })


@bp.route("/api/generate", methods=["POST"])
def api_generate():
    """Genere backup.sh/restore.sh/backup.env.example + planification
    (systemd ou cron)."""
    config = request.get_json(force=True) or {}

    try:
        fichiers = generate_files(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"files": fichiers})


@bp.route("/api/download", methods=["POST"])
def api_download():
    """Regenere puis renvoie un .zip des fichiers de sauvegarde."""
    config = request.get_json(force=True) or {}

    try:
        fichiers = generate_files(config)
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
        download_name="opsforge-backup.zip",
    )
