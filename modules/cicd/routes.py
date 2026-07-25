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
    generate_badge_markdown as generate_github_badge_markdown,
)
from modules.cicd.gitlab_core import (
    generate_gitlab_ci,
    generate_badge_markdown as generate_gitlab_badge_markdown,
)
from modules.cicd.circleci_core import (
    generate_circleci_config,
    generate_badge_markdown as generate_circleci_badge_markdown,
)
from modules.cicd.jenkins_core import (
    generate_jenkinsfile,
    generate_badge_markdown as generate_jenkins_badge_markdown,
)
from modules.cicd.drone_core import (
    generate_drone_yaml,
    generate_badge_markdown as generate_drone_badge_markdown,
)

bp = Blueprint("cicd", __name__, url_prefix="/cicd")

SUPPORTED_LANGUAGES = ["python", "node", "go", "rust", "java", "php", "ruby", "dotnet"]


def _generate_github(stacks, jobs, deploy, branches, schedule_cron):
    triggers = {
        "branches": branches,
        "pull_request": True,
        "workflow_dispatch": True,
        "schedule_cron": schedule_cron,
    }
    return generate_workflow(stacks, jobs=jobs, triggers=triggers, deploy=deploy)


# --------------------------------------------------------------------------
# Table de dispatch : une entree par plateforme CI/CD prise en charge.
# 'generate' a toujours la signature (stacks, jobs, deploy, branches,
# schedule_cron) -> str, quelle que soit la plateforme, pour que
# api_generate() n'ait pas besoin de connaitre les differences internes.
# --------------------------------------------------------------------------
PROVIDERS = {
    "github": {"generate": _generate_github, "filename": "ci.yml"},
    "gitlab": {
        "generate": lambda stacks, jobs, deploy, branches, schedule_cron: generate_gitlab_ci(
            stacks, jobs=jobs, deploy=deploy, branches=branches, schedule_cron=schedule_cron
        ),
        "filename": ".gitlab-ci.yml",
    },
    "circleci": {
        "generate": lambda stacks, jobs, deploy, branches, schedule_cron: generate_circleci_config(
            stacks, jobs=jobs, deploy=deploy, branches=branches, schedule_cron=schedule_cron
        ),
        "filename": "config.yml",
    },
    "jenkins": {
        "generate": lambda stacks, jobs, deploy, branches, schedule_cron: generate_jenkinsfile(
            stacks, jobs=jobs, deploy=deploy, branches=branches, schedule_cron=schedule_cron
        ),
        "filename": "Jenkinsfile",
    },
    "drone": {
        "generate": lambda stacks, jobs, deploy, branches, schedule_cron: generate_drone_yaml(
            stacks, jobs=jobs, deploy=deploy, branches=branches, schedule_cron=schedule_cron
        ),
        "filename": ".drone.yml",
    },
}


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
    """Genere le contenu du pipeline (GitHub Actions, GitLab CI, CircleCI,
    Jenkins ou Drone) a partir des choix faits."""
    data = request.get_json(force=True) or {}
    raw_stacks = data.get("stacks", [])
    jobs = data.get("jobs") or ["lint", "test", "build"]
    branches = data.get("branches") or ["main"]
    provider = data.get("provider") or "github"
    matrix_versions = data.get("matrix_versions") or []
    schedule_cron = data.get("schedule_cron") or None

    if provider not in PROVIDERS:
        return jsonify({"error": f"Plateforme inconnue : '{provider}'."}), 400

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

    provider_info = PROVIDERS[provider]

    try:
        yaml_text = provider_info["generate"](
            normalized_stacks, jobs, deploy_config, branches, schedule_cron
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    filename = provider_info["filename"]
    result = {"yaml": yaml_text, "filename": filename}

    badge_repo = data.get("badge_repo")
    if badge_repo:
        if provider == "gitlab":
            result["badge"] = generate_gitlab_badge_markdown(badge_repo, branch=branches[0])
        elif provider == "circleci":
            result["badge"] = generate_circleci_badge_markdown(badge_repo, branch=branches[0])
        elif provider == "drone":
            result["badge"] = generate_drone_badge_markdown(badge_repo, branch=branches[0])
        elif provider == "jenkins":
            # Format attendu : "url_jenkins,nom_du_job" (Jenkins n'est pas
            # rattache a un slug "org/repo" comme les autres plateformes).
            jenkins_url, _, job_name = badge_repo.partition(",")
            if job_name.strip():
                result["badge"] = generate_jenkins_badge_markdown(
                    jenkins_url.strip(), job_name.strip(), branch=branches[0]
                )
        else:
            result["badge"] = generate_github_badge_markdown(
                badge_repo, branch=branches[0], workflow_filename=filename
            )

    return jsonify(result)


@bp.route("/api/jobs-for/<language>")
def api_jobs_for(language):
    """Retourne les jobs disponibles pour un langage donne (utilise par le JS)."""
    return jsonify({"jobs": AVAILABLE_JOBS.get(language, [])})
