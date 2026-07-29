"""
modules/gitops/cli.py
-----------------------
Logique CLI du module GitOps d'OpsForge (ArgoCD / FluxCD).
Appele via `python main.py gitops ...`.
"""

import argparse
import json
import os
import sys

from modules.gitops.core import (
    generate_files,
    get_preset,
    list_presets,
    list_source_types,
    list_tools,
    write_files,
)

# Dossier de sortie par defaut : output/ a la racine du projet OpsForge
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge gitops",
        description=(
            "Genere des manifests GitOps (ArgoCD Application, ou FluxCD "
            "GitRepository + Kustomization/HelmRelease), a partir d'un "
            "fichier JSON ou d'un preset."
        ),
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        default=None,
        help="Fichier JSON decrivant la config (voir --preset pour un depart rapide).",
    )
    parser.add_argument(
        "--preset",
        default=None,
        help=f"Utilise un preset predefini. Disponibles : {', '.join(list_presets())}.",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="Affiche la liste des presets disponibles et quitte.",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help=f"Affiche les outils GitOps geres ({', '.join(list_tools())}) et quitte.",
    )
    parser.add_argument(
        "--list-source-types",
        action="store_true",
        help=f"Affiche les types de source geres ({', '.join(list_source_types())}) et quitte.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Dossier de sortie (defaut : output/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche les fichiers generes sans rien ecrire sur disque.",
    )
    return parser


def _load_config(args):
    if args.config_file:
        with open(args.config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    elif args.preset:
        try:
            config = get_preset(args.preset)
        except ValueError as e:
            print(f"Erreur : {e}")
            sys.exit(1)
    else:
        print(
            "Erreur : fournis un fichier de config JSON ou --preset "
            f"({', '.join(list_presets())})."
        )
        sys.exit(1)
    return config


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_presets:
        print("Presets disponibles :")
        for name in list_presets():
            print(f"  - {name}")
        return 0

    if args.list_tools:
        print("Outils GitOps geres :")
        for name in list_tools():
            print(f"  - {name}")
        return 0

    if args.list_source_types:
        print("Types de source geres :")
        for name in list_source_types():
            print(f"  - {name}")
        return 0

    config = _load_config(args)

    if args.dry_run:
        try:
            fichiers = generate_files(config)
        except ValueError as e:
            print(f"Erreur : {e}")
            return 1
        print("\n--- Apercu (dry-run) ---\n")
        for nom, contenu in fichiers.items():
            print(f"# --- {nom} ---")
            print(contenu)
        print("--- Fin de l'apercu : rien n'a ete ecrit sur disque ---")
        return 0

    output_dir = args.output_dir or OUTPUT_DIR

    try:
        paths = write_files(config, output_dir)
    except ValueError as e:
        print(f"Erreur : {e}")
        return 1

    print("\nManifests GitOps generes avec succes :")
    for path in paths:
        print(f"  - {path}")

    tool = config.get("tool")
    if tool == "argocd":
        print(
            "\nUtilisation : `kubectl apply -f "
            + os.path.basename(paths[0])
            + "` (namespace argocd), ou dans l'UI ArgoCD via New App > Edit as YAML."
        )
    else:
        print(
            "\nUtilisation : `kubectl apply -f .` dans le dossier genere "
            "(namespace ou Flux est installe), ou commite-les dans le "
            "depot surveille par `flux bootstrap` si tu geres tes sources via Git."
        )
    return 0
