"""
modules/cicd/cli.py
-------------------
Logique CLI du module CI/CD d'OpsForge (GitHub Actions, GitLab CI,
CircleCI, Jenkins, Drone). Appele via `python main.py cicd ...`.
"""

import argparse
import os
import sys

from modules.cicd.detector import detect_stack
from modules.cicd.core import write_workflow, generate_workflow, generate_badge_markdown
from modules.cicd.gitlab_core import (
    write_gitlab_ci,
    generate_gitlab_ci,
    generate_badge_markdown as generate_gitlab_badge_markdown,
)
from modules.cicd.circleci_core import (
    write_circleci_config,
    generate_circleci_config,
    generate_badge_markdown as generate_circleci_badge_markdown,
)
from modules.cicd.jenkins_core import (
    write_jenkinsfile,
    generate_jenkinsfile,
    generate_badge_markdown as generate_jenkins_badge_markdown,
)
from modules.cicd.drone_core import (
    write_drone_yaml,
    generate_drone_yaml,
    generate_badge_markdown as generate_drone_badge_markdown,
)

# Dossier de sortie par defaut : output/ a la racine du projet OpsForge
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def _generate_github(stacks, jobs, deploy, branches, schedule_cron):
    triggers = {
        "branches": branches,
        "pull_request": True,
        "workflow_dispatch": True,
        "schedule_cron": schedule_cron,
    }
    return generate_workflow(stacks, jobs=jobs, triggers=triggers, deploy=deploy)


def _write_github(stacks, output_path, jobs, deploy, branches, schedule_cron):
    triggers = {
        "branches": branches,
        "pull_request": True,
        "workflow_dispatch": True,
        "schedule_cron": schedule_cron,
    }
    return write_workflow(stacks, output_path, jobs=jobs, triggers=triggers, deploy=deploy)


# --------------------------------------------------------------------------
# Table de dispatch : une entree par plateforme CI/CD prise en charge.
# 'generate'/'write' ont toujours la signature (stacks, jobs, deploy,
# branches, schedule_cron) / (stacks, output_path, jobs, deploy, branches,
# schedule_cron), quelle que soit la plateforme.
# --------------------------------------------------------------------------
PROVIDERS = {
    "github": {
        "generate": _generate_github,
        "write": _write_github,
        "default_filename": "ci.yml",
        "real_path_hint": ".github/workflows/ci.yml",
    },
    "gitlab": {
        "generate": lambda s, j, d, b, c: generate_gitlab_ci(s, jobs=j, deploy=d, branches=b, schedule_cron=c),
        "write": lambda s, p, j, d, b, c: write_gitlab_ci(s, p, jobs=j, deploy=d, branches=b, schedule_cron=c),
        "default_filename": ".gitlab-ci.yml",
        "real_path_hint": ".gitlab-ci.yml (a la racine du depot)",
    },
    "circleci": {
        "generate": lambda s, j, d, b, c: generate_circleci_config(s, jobs=j, deploy=d, branches=b, schedule_cron=c),
        "write": lambda s, p, j, d, b, c: write_circleci_config(s, p, jobs=j, deploy=d, branches=b, schedule_cron=c),
        "default_filename": "config.yml",
        "real_path_hint": ".circleci/config.yml",
    },
    "jenkins": {
        "generate": lambda s, j, d, b, c: generate_jenkinsfile(s, jobs=j, deploy=d, branches=b, schedule_cron=c),
        "write": lambda s, p, j, d, b, c: write_jenkinsfile(s, p, jobs=j, deploy=d, branches=b, schedule_cron=c),
        "default_filename": "Jenkinsfile",
        "real_path_hint": "Jenkinsfile (a la racine du depot)",
    },
    "drone": {
        "generate": lambda s, j, d, b, c: generate_drone_yaml(s, jobs=j, deploy=d, branches=b, schedule_cron=c),
        "write": lambda s, p, j, d, b, c: write_drone_yaml(s, p, jobs=j, deploy=d, branches=b, schedule_cron=c),
        "default_filename": ".drone.yml",
        "real_path_hint": ".drone.yml (a la racine du depot)",
    },
}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge cicd",
        description="Genere un pipeline CI/CD (GitHub Actions, GitLab CI, CircleCI, "
                     "Jenkins ou Drone) a partir d'un dossier de projet.",
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        default=".",
        help="Chemin du projet a analyser (defaut : dossier courant)",
    )
    parser.add_argument(
        "--jobs",
        nargs="+",
        choices=["lint", "test", "build"],
        default=["lint", "test", "build"],
        help="Jobs a inclure dans le pipeline (defaut : tous)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Chemin de sortie du fichier genere. Par defaut : output/<fichier> "
             "(dans ce projet). Emplacement reel attendu dans ton depot selon la "
             "plateforme : github -> .github/workflows/ci.yml, gitlab -> .gitlab-ci.yml, "
             "circleci -> .circleci/config.yml, jenkins -> Jenkinsfile, drone -> .drone.yml.",
    )
    parser.add_argument(
        "--branches",
        nargs="+",
        default=["main"],
        help="Branches declenchant le pipeline (defaut : main)",
    )
    parser.add_argument(
        "--provider",
        choices=list(PROVIDERS.keys()),
        default="github",
        help="Plateforme cible : github, gitlab, circleci, jenkins ou drone. Defaut : github",
    )

    # ---- Options de deploiement ----
    parser.add_argument(
        "--deploy",
        nargs="+",
        default=[],
        help="Cible(s) de deploiement. GitHub : github_pages, docker_hub, ssh, vercel, aws_s3. "
             "GitLab : gitlab_pages, docker_hub, ssh, vercel, aws_s3. "
             "CircleCI/Jenkins/Drone : docker_hub, ssh, vercel, aws_s3 (pas de 'pages' natif). "
             "Necessitent de configurer les secrets/variables correspondants "
             "(voir le README pour le detail par cible).",
    )
    parser.add_argument(
        "--pages-dir",
        default=None,
        help="[github_pages/aws_s3] Dossier du build statique a publier (defaut: dist)",
    )
    parser.add_argument(
        "--pages-build-cmd",
        default=None,
        help="[github_pages/aws_s3] Commande de build du site (defaut: npm run build)",
    )
    parser.add_argument(
        "--docker-image",
        default=None,
        help="[docker_hub] Nom de l'image (ex: monusername/monapp)",
    )
    parser.add_argument(
        "--deploy-path",
        default=None,
        help="[ssh] Chemin de destination sur le serveur distant",
    )
    parser.add_argument(
        "--service-name",
        default=None,
        help="[ssh] Nom du service systemd a redemarrer apres deploiement",
    )
    parser.add_argument(
        "--s3-bucket",
        default=None,
        help="[aws_s3] Nom du bucket S3 cible",
    )
    parser.add_argument(
        "--aws-region",
        default=None,
        help="[aws_s3] Region AWS (defaut: us-east-1)",
    )

    # ---- Matrix build / cron / badge ----
    parser.add_argument(
        "--matrix-versions",
        nargs="+",
        default=None,
        help="Teste le job 'test' sur plusieurs versions du langage "
             "(ex: --matrix-versions 3.10 3.11 3.12). Applique a toutes "
             "les stacks detectees.",
    )
    parser.add_argument(
        "--schedule-cron",
        default=None,
        help="Expression cron pour un declenchement planifie "
             "(ex: '0 3 * * *' pour tous les jours a 3h). "
             "GitHub/CircleCI : ajoute directement le trigger natif. "
             "GitLab/Drone : ajoute une note expliquant comment le configurer "
             "manuellement (pas possible en pur YAML sur ces plateformes). "
             "Jenkins : ajoute un bloc triggers { cron(...) }.",
    )
    parser.add_argument(
        "--badge-repo",
        default=None,
        help="Si fourni (ex: 'monuser/monrepo'), affiche en plus un "
             "snippet Markdown de badge de statut a coller dans ton README. "
             "Pour Jenkins, format special : 'url_jenkins,nom_du_job' "
             "(ex: 'https://ci.exemple.com,mon-projet').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le pipeline genere dans le terminal sans rien ecrire sur disque.",
    )

    return parser


def _print_badge(provider, badge_repo, branch):
    if not badge_repo:
        return
    print("\nBadge Markdown pour ton README :")
    if provider == "gitlab":
        print(generate_gitlab_badge_markdown(badge_repo, branch=branch))
    elif provider == "circleci":
        print(generate_circleci_badge_markdown(badge_repo, branch=branch))
    elif provider == "drone":
        print(generate_drone_badge_markdown(badge_repo, branch=branch))
    elif provider == "jenkins":
        jenkins_url, _, job_name = badge_repo.partition(",")
        if not job_name.strip():
            print("Format invalide pour --badge-repo avec Jenkins : attendu 'url_jenkins,nom_du_job'.")
            return
        print(generate_jenkins_badge_markdown(jenkins_url.strip(), job_name.strip(), branch=branch))
    else:
        print(generate_badge_markdown(badge_repo, branch=branch))


def main(argv=None):
    args = build_parser().parse_args(argv)
    provider_info = PROVIDERS[args.provider]

    print(f"Analyse du dossier : {os.path.abspath(args.project_path)}")
    stacks = detect_stack(args.project_path)

    if not stacks:
        print("Aucune stack detectee. Verifie que ton projet contient bien un "
              "package.json, pyproject.toml, go.mod, Cargo.toml, pom.xml ou composer.json.")
        sys.exit(1)

    print("Stack(s) detectee(s) :")
    for stack in stacks:
        print(f"  - {stack['language']} "
              f"(package manager: {stack['package_manager']}, "
              f"version: {stack['version']})")

    if args.matrix_versions:
        for stack in stacks:
            stack["matrix_versions"] = args.matrix_versions
        print(f"Matrix build active sur : {', '.join(args.matrix_versions)}")

    deploy_config = None
    if args.deploy:
        deploy_config = {
            "targets": args.deploy,
            "pages_dir": args.pages_dir,
            "pages_build_cmd": args.pages_build_cmd,
            "docker_image": args.docker_image,
            "deploy_path": args.deploy_path,
            "service_name": args.service_name,
            "s3_bucket": args.s3_bucket,
            "aws_region": args.aws_region,
        }

    output_path = args.output or os.path.join(OUTPUT_DIR, provider_info["default_filename"])

    if args.dry_run:
        try:
            content = provider_info["generate"](stacks, args.jobs, deploy_config, args.branches, args.schedule_cron)
        except ValueError as e:
            print(f"Erreur : {e}")
            sys.exit(1)
        print(f"\n--- Apercu (dry-run) : {output_path} ---\n")
        print(content)
        print("--- Fin de l'apercu : rien n'a ete ecrit sur disque ---")
        return

    try:
        provider_info["write"](stacks, output_path, args.jobs, deploy_config, args.branches, args.schedule_cron)
    except ValueError as e:
        print(f"Erreur : {e}")
        sys.exit(1)

    print(f"\nPipeline genere avec succes : {output_path}")
    print(f"Emplacement reel attendu dans ton depot : {provider_info['real_path_hint']}")
    print(f"Jobs inclus : {', '.join(args.jobs)}")
    if args.deploy:
        print(f"Deploiement inclus : {', '.join(args.deploy)}")
        print("N'oublie pas de configurer les secrets/variables/identifiants necessaires "
              "cote plateforme CI. Voir le README.")

    _print_badge(args.provider, args.badge_repo, args.branches[0])


if __name__ == "__main__":
    main()
