"""
modules/dockerfile/routes.py
-----------------------------
Blueprint Flask du module Dockerfile (monte sous /dockerfile).
"""

from flask import Blueprint, render_template, request, jsonify

from modules.cicd.detector import detect_stack
from modules.dockerfile.core import (
    generate_dockerfile,
    generate_dockerignore,
    SUPPORTED_LANGUAGES,
    DEFAULT_PORTS,
    DEFAULT_ENTRYPOINTS,
)

bp = Blueprint("dockerfile", __name__, url_prefix="/dockerfile")


@bp.route("/")
def index():
    return render_template(
        "dockerfile.html",
        languages=SUPPORTED_LANGUAGES,
        default_ports=DEFAULT_PORTS,
        default_entrypoints=DEFAULT_ENTRYPOINTS,
    )


@bp.route("/api/detect", methods=["POST"])
def api_detect():
    """Detecte automatiquement le(s) stack(s) presents dans un dossier local."""
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()

    if not path:
        return jsonify({"error": "Merci de renseigner un chemin de dossier."}), 400

    try:
        stacks = detect_stack(path)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not stacks:
        return jsonify({
            "error": "Aucun stack detecte dans ce dossier. "
                     "Tu peux choisir manuellement ci-dessous."
        }), 404

    return jsonify({"stacks": stacks})


@bp.route("/api/generate", methods=["POST"])
def api_generate():
    """Genere le Dockerfile (+ .dockerignore optionnel) a partir des choix faits."""
    data = request.get_json(force=True) or {}
    language = data.get("language")

    if not language:
        return jsonify({"error": "Merci de choisir un langage."}), 400

    stack = {
        "language": language,
        "version": data.get("version") or None,
        "package_manager": data.get("package_manager") or "",
    }

    port = data.get("port") or None
    entrypoint = data.get("entrypoint") or None
    workdir = data.get("workdir") or "/app"

    try:
        dockerfile_text = generate_dockerfile(
            stack, port=port, entrypoint=entrypoint, workdir=workdir
        )
        dockerignore_text = generate_dockerignore(language)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "dockerfile": dockerfile_text,
        "dockerignore": dockerignore_text,
        "filename": "Dockerfile",
    })
