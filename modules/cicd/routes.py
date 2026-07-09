"""
modules/cicd/routes.py
----------------------
Blueprint Flask du module CI/CD (monte sous /cicd).
"""

from flask import Blueprint, render_template, request, jsonify

from modules.cicd.detector import detect_stack
from modules.cicd.core import (
    generate_workflow,
    AVAILABLE_JOBS,
    DEPLOY_TARGETS,
    generate_badge_markdown,
)
from modules.cicd.gitlab_core import (
    generate_gitlab_ci,
    generate_badge_markdown as generate_gitlab_badge_markdown,
)

bp = Blueprint("cicd", __name__, url_prefix="/cicd")

SUPPORTED_LANGUAGES = ["python", "node", "go", "rust", "java", "php", "ruby", "dotnet"]


@bp.route("/")
def index():
    return render_template(
        "cicd.html",
        languages=SUPPORTED_LANGUAGES,
        deploy_targets=DEPLOY_TARGETS,
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
    """Genere le contenu du pipeline (GitHub Actions ou GitLab CI) a partir des choix faits."""
    data = request.get_json(force=True) or {}
    raw_stacks = data.get("stacks", [])
    jobs = data.get("jobs") or ["lint", "test", "build"]
    branches = data.get("branches") or ["main"]
    provider = data.get("provider") or "github"
    matrix_versions = data.get("matrix_versions") or []
    schedule_cron = data.get("schedule_cron") or None

    if not raw_stacks:
        return jsonify({"error": "Aucune stack fournie."}), 400

    # Normalise : accepte des stacks partielles (juste {"language": "python"})
    # les valeurs par defaut (version, package_manager) sont gerees par core.py
    normalized_stacks = []
    for s in raw_stacks:
        if not s.get("language"):
            continue
        stack = {
            "language": s["language"],
            "version": s.get("version") or None,
            "package_manager": s.get("package_manager") or "",
        }
        if matrix_versions:
            stack["matrix_versions"] = matrix_versions
        normalized_stacks.append(stack)

    deploy_targets = data.get("deploy_targets") or []
    deploy_config = None
    if deploy_targets:
        deploy_config = {
            "targets": deploy_targets,
            "pages_dir": data.get("pages_dir"),
            "pages_build_cmd": data.get("pages_build_cmd"),
            "docker_image": data.get("docker_image"),
            "deploy_path": data.get("deploy_path"),
            "service_name": data.get("service_name"),
            "s3_bucket": data.get("s3_bucket"),
            "aws_region": data.get("aws_region"),
        }

    try:
        if provider == "gitlab":
            yaml_text = generate_gitlab_ci(
                normalized_stacks, jobs=jobs, deploy=deploy_config, branches=branches,
                schedule_cron=schedule_cron,
            )
        else:
            triggers = {
                "branches": branches,
                "pull_request": True,
                "workflow_dispatch": True,
                "schedule_cron": schedule_cron,
            }
            yaml_text = generate_workflow(
                normalized_stacks, jobs=jobs, triggers=triggers, deploy=deploy_config
            )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    filename = ".gitlab-ci.yml" if provider == "gitlab" else "ci.yml"

    result = {"yaml": yaml_text, "filename": filename}

    badge_repo = data.get("badge_repo")
    if badge_repo:
        if provider == "gitlab":
            result["badge"] = generate_gitlab_badge_markdown(badge_repo, branch=branches[0])
        else:
            result["badge"] = generate_badge_markdown(
                badge_repo, branch=branches[0], workflow_filename=filename
            )

    return jsonify(result)


@bp.route("/api/jobs-for/<language>")
def api_jobs_for(language):
    """Retourne les jobs disponibles pour un langage donne (utilise par le JS)."""
    return jsonify({"jobs": AVAILABLE_JOBS.get(language, [])})
