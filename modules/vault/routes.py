"""
modules/vault/routes.py
------------------------
Blueprint Flask du module HashiCorp Vault (monte sous /vault).
"""

import io
import zipfile

from flask import Blueprint, jsonify, render_template, request, send_file

from modules.vault.core import (
    AUDIT_DEVICE_CATALOG,
    AUTH_METHOD_CATALOG,
    CAPABILITIES,
    SEAL_TYPES,
    SECRETS_ENGINE_CATALOG,
    STORAGE_BACKENDS,
    generate_files,
    get_preset,
    list_audit_devices,
    list_auth_methods,
    list_presets,
    list_secrets_engines,
)

bp = Blueprint("vault", __name__, url_prefix="/vault")


@bp.route("/")
def index():
    return render_template(
        "vault.html",
        presets=list_presets(),
        storage_backends=STORAGE_BACKENDS,
        seal_types=SEAL_TYPES,
        auth_methods=AUTH_METHOD_CATALOG,
        secrets_engines=SECRETS_ENGINE_CATALOG,
        audit_devices=AUDIT_DEVICE_CATALOG,
        capabilities=CAPABILITIES,
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
        "storage_backends": {k: v for k, v in STORAGE_BACKENDS.items()},
        "seal_types": {k: v for k, v in SEAL_TYPES.items()},
        "auth_methods": list_auth_methods(),
        "secrets_engines": list_secrets_engines(),
        "audit_devices": list_audit_devices(),
        "capabilities": list(CAPABILITIES),
    })


@bp.route("/api/generate", methods=["POST"])
def api_generate():
    """Genere les fichiers Vault (config.hcl, policies/*.hcl, bootstrap.sh)."""
    config = request.get_json(force=True) or {}

    try:
        fichiers = generate_files(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"files": fichiers})


@bp.route("/api/download", methods=["POST"])
def api_download():
    """Regenere puis renvoie un .zip du projet Vault (config.hcl + policies/ + bootstrap.sh)."""
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
        download_name="vault-project.zip",
    )
