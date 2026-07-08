"""
main.py
-------
OpsForge — point d'entree CLI du generateur de pipeline CI/CD
(GitHub Actions & GitLab CI).

Usage :
    python main.py /chemin/vers/mon/projet
    python main.py /chemin/vers/mon/projet --jobs lint test
    python main.py /chemin/vers/mon/projet --output .github/workflows/ci.yml

Avec deploiement :
    python main.py . --deploy docker_hub --docker-image monusername/monapp
    python main.py . --deploy github_pages ssh --deploy-path /var/www/monapp --service-name monapp

Sans argument, analyse le dossier courant.
"""

import argparse
import os
import sys

from generator.detector import detect_stack
from generator.core import generate_workflow, write_workflow, DEPLOY_TARGETS, generate_badge_markdown
from generator.gitlab_core import (
    write_gitlab_ci,
    DEPLOY_TARGETS as GITLAB_DEPLOY_TARGETS,
    generate_badge_markdown as generate_gitlab_badge_markdown,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Genere un pipeline GitHub Actions a partir d'un dossier de projet."
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
        help="Chemin de sortie du fichier .yml. "
             "Par defaut : output/ci.yml (dans ce projet), "
             "ou passe '.github/workflows/ci.yml' pour l'ecrire directement dans ton repo.",
    )
    parser.add_argument(
        "--branches",
        nargs="+",
        default=["main"],
        help="Branches declenchant le pipeline (defaut : main)",
    )

    parser.add_argument(
        "--provider",
        choices=["github", "gitlab"],
        default="github",
        help="Plateforme cible : github (GitHub Actions) ou gitlab (GitLab CI). Defaut : github",
    )

    # ---- Options de deploiement ----
    parser.add_argument(
        "--deploy",
        nargs="+",
        default=[],
        help="Cible(s) de deploiement. GitHub : github_pages, docker_hub, ssh. "
             "GitLab : gitlab_pages, docker_hub, ssh. "
             "Necessitent de configurer les secrets/variables correspondants "
             "(voir le README pour le detail par cible).",
    )
    parser.add_argument(
        "--pages-dir",
        default=None,
        help="[github_pages] Dossier du build statique a publier (defaut: dist)",
    )
    parser.add_argument(
        "--pages-build-cmd",
        default=None,
        help="[github_pages] Commande de build du site (defaut: npm run build)",
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
             "GitHub : ajoute directement le trigger. "
             "GitLab : ajoute une note expliquant comment le configurer "
             "manuellement (pas possible en pur YAML sur GitLab).",
    )
    parser.add_argument(
        "--badge-repo",
        default=None,
        help="Si fourni (ex: 'monuser/monrepo'), affiche en plus un "
             "snippet Markdown de badge de statut a coller dans ton README.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

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

    triggers = {
        "branches": args.branches,
        "pull_request": True,
        "workflow_dispatch": True,
        "schedule_cron": args.schedule_cron,
    }

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

    if args.provider == "gitlab":
        output_path = args.output or os.path.join(
            os.path.dirname(__file__), "output", ".gitlab-ci.yml"
        )
        try:
            write_gitlab_ci(
                stacks, output_path, jobs=args.jobs, deploy=deploy_config,
                schedule_cron=args.schedule_cron,
            )
        except ValueError as e:
            print(f"Erreur : {e}")
            sys.exit(1)

        print(f"\nPipeline GitLab CI genere avec succes : {output_path}")
        print(f"Jobs inclus : {', '.join(args.jobs)}")
        if args.deploy:
            print(f"Deploiement inclus : {', '.join(args.deploy)}")
            print("N'oublie pas de configurer les variables CI/CD necessaires dans GitLab "
                  "(Settings > CI/CD > Variables). Voir le README.")
        if args.badge_repo:
            print(f"\nBadge Markdown pour ton README :")
            print(generate_gitlab_badge_markdown(args.badge_repo, branch=args.branches[0]))
        return

    output_path = args.output or os.path.join(
        os.path.dirname(__file__), "output", "ci.yml"
    )

    try:
        write_workflow(
            stacks, output_path, jobs=args.jobs, triggers=triggers, deploy=deploy_config
        )
    except ValueError as e:
        print(f"Erreur : {e}")
        sys.exit(1)

    print(f"\nPipeline genere avec succes : {output_path}")
    print(f"Jobs inclus : {', '.join(args.jobs)}")
    if args.deploy:
        print(f"Deploiement inclus : {', '.join(args.deploy)}")
        print("N'oublie pas de configurer les secrets necessaires dans GitHub "
              "(Settings > Secrets and variables > Actions). Voir le README.")
    if args.badge_repo:
        print(f"\nBadge Markdown pour ton README :")
        print(generate_badge_markdown(
            args.badge_repo,
            branch=args.branches[0],
            workflow_filename=os.path.basename(output_path),
        ))


if __name__ == "__main__":
    main()
