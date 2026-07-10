"""
modules/k8s/routes.py
---------------------
Blueprint Flask du module Kubernetes/Helm (monte sous /k8s).
"""

import io
import zipfile

from flask import Blueprint, render_template, request, jsonify, send_file

from modules.k8s.core import (
    generate_manifests,
    generate_manifests_combined,
    generate_helm_chart,
    valider_config,
    SERVICE_TYPES,
)

bp = Blueprint("k8s", __name__, url_prefix="/k8s")


def _config_from_payload(data):
    """Construit la config core a partir du JSON du formulaire web."""
    config = {
        "name": (data.get("name") or "").strip(),
        "image": (data.get("image") or "").strip(),
        "replicas": data.get("replicas") if isinstance(data.get("replicas"), int) else 2,
        "container_port": data.get("container_port") or 8080,
        "service_type": data.get("service_type") or "ClusterIP",
        "service_port": data.get("service_port") or 80,
        "namespace": (data.get("namespace") or "").strip() or None,
        "env": data.get("env") or {},
        "probe_path": (data.get("probe_path") or "").strip() or None,
    }
    ingress = data.get("ingress")
    if ingress and (ingress.get("host") or "").strip():
        config["ingress"] = {
            "host": ingress["host"].strip(),
            "path": (ingress.get("path") or "/").strip() or "/",
            "class": (ingress.get("class") or "").strip(),
            "tls": bool(ingress.get("tls")),
        }
    return config


@bp.route("/")
def index():
    return render_template("k8s.html", service_types=SERVICE_TYPES)


@bp.route("/api/generate", methods=["POST"])
def api_generate():
    """Genere manifests ou chart Helm selon le mode demande."""
    data = request.get_json(force=True) or {}
    mode = data.get("mode", "manifests")
    config = _config_from_payload(data)

    erreurs, avertissements = valider_config(config)
    if erreurs:
        return jsonify({"error": " ".join(erreurs)}), 400

    try:
        if mode == "helm":
            files = generate_helm_chart(config)
            combined = None
        else:
            files = generate_manifests(config)
            combined = generate_manifests_combined(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "mode": mode,
        "files": files,
        "combined": combined,
        "warnings": avertissements,
        "chart_name": config["name"],
    })


@bp.route("/api/download", methods=["POST"])
def api_download():
    """Regenere puis renvoie un .zip (chart Helm complet ou manifests)."""
    data = request.get_json(force=True) or {}
    mode = data.get("mode", "manifests")
    config = _config_from_payload(data)

    erreurs, _ = valider_config(config)
    if erreurs:
        return jsonify({"error": " ".join(erreurs)}), 400

    try:
        if mode == "helm":
            files = generate_helm_chart(config)
            root = config["name"]
            zip_name = f"{config['name']}-chart.zip"
        else:
            files = generate_manifests(config)
            root = "k8s"
            zip_name = f"{config['name']}-manifests.zip"
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, content in files.items():
            zf.writestr(f"{root}/{rel_path}", content)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=zip_name,
    )
