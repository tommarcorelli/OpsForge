"""
modules/dockerfile/cli.py
--------------------------
Logique CLI du module Dockerfile d'OpsForge.
Appele via `python main.py dockerfile ...`.
"""

import argparse
import os
import sys

from modules.cicd.detector import detect_stack
from modules.dockerfile.core import (
    generate_dockerfile,
    generate_dockerignore,
    generate_docker_bake,
    write_dockerfile,
    write_dockerignore,
    write_docker_bake,
    SUPPORTED_LANGUAGES,
)

# Dossier de sortie par defaut : output/ a la racine du projet OpsForge
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge dockerfile",
        description=(
            "Genere un Dockerfile multi-stage (build + runtime allege) a partir "
            "d'un dossier de projet, en reutilisant la detection de stack du "
            "module CI/CD."
        ),
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        default=".",
        help="Chemin du dossier de projet a analyser (defaut : dossier courant).",
    )
    parser.add_argument(
        "--lang",
        choices=SUPPORTED_LANGUAGES,
        default=None,
        help="Force le langage a utiliser (ignore la detection automatique).",
    )
    parser.add_argument(
        "--package-manager",
        default=None,
        help="Force le package manager (ex: poetry, yarn, gradle). "
             "Sinon, celui detecte automatiquement est utilise.",
    )
    parser.add_argument(
        "--version",
        dest="lang_version",
        default=None,
        help="Force la version du langage (ex: 3.12, 20, 17). "
             "Sinon, celle detectee automatiquement est utilisee.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port expose dans le Dockerfile (defaut : convention du langage).",
    )
    parser.add_argument(
        "--entrypoint",
        default=None,
        help="Fichier/binaire/DLL de demarrage "
             "(ex: main.py, index.js, MonProjet.dll). Ignore pour java/php.",
    )
    parser.add_argument(
        "--workdir",
        default="/app",
        help="Dossier de travail dans le conteneur (defaut : /app).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Chemin de sortie du Dockerfile (defaut : output/Dockerfile).",
    )
    parser.add_argument(
        "--no-dockerignore",
        action="store_true",
        help="Ne genere pas de .dockerignore a cote du Dockerfile.",
    )
    parser.add_argument(
        "--bake",
        action="store_true",
        help="Genere aussi un docker-bake.hcl (build multi-tags/multi-plateformes "
             "via `docker buildx bake`) a cote du Dockerfile.",
    )
    parser.add_argument(
        "--image-name",
        default="app",
        help="Nom de l'image utilise dans le docker-bake.hcl (defaut : app).",
    )
    parser.add_argument(
        "--tags",
        default=None,
        help="Tags separes par des virgules pour le docker-bake.hcl (defaut : latest).",
    )
    parser.add_argument(
        "--platforms",
        default=None,
        help="Plateformes separees par des virgules pour le build multi-arch "
             "(defaut : linux/amd64,linux/arm64).",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Ajoute `output = [\"type=registry\"]` au docker-bake.hcl pour pousser "
             "l'image directement apres build.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le Dockerfile genere dans le terminal sans rien ecrire sur disque.",
    )

    return parser


def _resolve_stack(args):
    """Determine la stack a utiliser : detection automatique + surcharges CLI."""
    if args.lang:
        return {
            "language": args.lang,
            "version": args.lang_version,
            "package_manager": args.package_manager or "",
        }

    print(f"Analyse du dossier : {os.path.abspath(args.project_path)}")
    stacks = detect_stack(args.project_path)

    if not stacks:
        print("Aucune stack detectee. Utilise --lang pour choisir manuellement "
              f"({', '.join(SUPPORTED_LANGUAGES)}).")
        sys.exit(1)

    if len(stacks) > 1:
        found = ", ".join(s["language"] for s in stacks)
        print(f"Plusieurs stacks detectees ({found}). "
              "Precise laquelle utiliser avec --lang.")
        sys.exit(1)

    stack = stacks[0]
    print(f"Stack detectee : {stack['language']} "
          f"(package manager: {stack['package_manager']}, version: {stack['version']})")

    if args.lang_version:
        stack["version"] = args.lang_version
    if args.package_manager:
        stack["package_manager"] = args.package_manager

    return stack


def main(argv=None):
    args = build_parser().parse_args(argv)

    stack = _resolve_stack(args)

    if args.dry_run:
        try:
            content = generate_dockerfile(
                stack, port=args.port, entrypoint=args.entrypoint, workdir=args.workdir
            )
        except ValueError as e:
            print(f"Erreur : {e}")
            sys.exit(1)
        output_path = args.output or os.path.join(OUTPUT_DIR, "Dockerfile")
        print(f"\n--- Apercu (dry-run) : {output_path} ---\n")
        print(content)
        if not args.no_dockerignore:
            print(f"--- Apercu (dry-run) : {output_path}.dockerignore ---\n")
            print(generate_dockerignore(stack["language"]))
        if args.bake:
            tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
            platforms = (
                [p.strip() for p in args.platforms.split(",") if p.strip()]
                if args.platforms else None
            )
            bake_path = os.path.join(os.path.dirname(output_path) or ".", "docker-bake.hcl")
            print(f"--- Apercu (dry-run) : {bake_path} ---\n")
            print(generate_docker_bake(
                stack, image_name=args.image_name, tags=tags, platforms=platforms,
                push=args.push,
            ))
        print("--- Fin de l'apercu : rien n'a ete ecrit sur disque ---")
        return

    output_path = args.output or os.path.join(OUTPUT_DIR, "Dockerfile")

    try:
        write_dockerfile(
            stack, output_path, port=args.port, entrypoint=args.entrypoint, workdir=args.workdir
        )
    except ValueError as e:
        print(f"Erreur : {e}")
        sys.exit(1)

    print(f"\nDockerfile genere avec succes : {output_path}")

    if not args.no_dockerignore:
        dockerignore_path = os.path.join(os.path.dirname(output_path) or ".", ".dockerignore")
        write_dockerignore(stack["language"], dockerignore_path)
        print(f".dockerignore genere : {dockerignore_path}")

    if args.bake:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
        platforms = (
            [p.strip() for p in args.platforms.split(",") if p.strip()]
            if args.platforms else None
        )
        bake_path = os.path.join(os.path.dirname(output_path) or ".", "docker-bake.hcl")
        write_docker_bake(
            stack, bake_path, image_name=args.image_name, tags=tags, platforms=platforms,
            push=args.push,
        )
        print(f"docker-bake.hcl genere : {bake_path}")

    print(f"\nPour construire l'image : docker build -t mon-app {os.path.dirname(output_path) or '.'}")
    if args.bake:
        print(f"Ou via Bake : docker buildx bake -f {bake_path}")
