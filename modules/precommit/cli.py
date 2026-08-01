"""
modules/precommit/cli.py
--------------------------
Logique CLI du module precommit d'OpsForge.
Appele via `python main.py precommit ...`.
"""

import argparse
import json
import os

from modules.precommit.core import (
    SUPPORTED_BACKENDS,
    generate_precommit,
    get_preset,
    list_presets,
    write_precommit,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge precommit",
        description=(
            "Genere des hooks Git pre-commit (framework pre-commit ou Husky), "
            "a partir d'un preset ou d'une config JSON."
        ),
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        default=None,
        help="Fichier JSON decrivant les hooks (voir --preset pour un depart rapide).",
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
        "--backend",
        choices=SUPPORTED_BACKENDS,
        default=None,
        help="Surcharge le backend (pre-commit / husky).",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Dossier de sortie (defaut : output/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le(s) fichier(s) genere(s) sans rien ecrire sur disque.",
    )
    return parser


def _load_config(args):
    """Retourne la config chargee, ou None (en ayant deja affiche l'erreur) en cas d'echec."""
    if args.config_file:
        with open(args.config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    elif args.preset:
        try:
            config = get_preset(args.preset)
        except ValueError as e:
            print(f"Erreur : {e}")
            return None
    else:
        print(
            "Erreur : fournis un fichier de config JSON ou --preset "
            f"({', '.join(list_presets())})."
        )
        return None

    if args.backend:
        config["backend"] = args.backend

    return config


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_presets:
        print("Presets disponibles :")
        for name in list_presets():
            print(f"  - {name}")
        return 0

    config = _load_config(args)
    if config is None:
        return 1

    if args.dry_run:
        try:
            files = generate_precommit(config)
        except ValueError as e:
            print(f"Erreur : {e}")
            return 1
        for filename, content in files.items():
            print(f"\n--- Apercu (dry-run) : {filename} ---\n")
            print(content)
        print("--- Fin de l'apercu : rien n'a ete ecrit sur disque ---")
        return 0

    output_dir = args.output_dir or OUTPUT_DIR

    try:
        paths = write_precommit(config, output_dir)
    except ValueError as e:
        print(f"Erreur : {e}")
        return 1

    print("\nFichier(s) genere(s) avec succes :")
    for path in paths:
        print(f"  - {path}")

    backend = config.get("backend", "pre-commit")
    if backend == "pre-commit":
        print("\nPour activer : pip install pre-commit && pre-commit install")
    else:
        print("\nPour activer : npm install husky lint-staged --save-dev && npx husky install")
        print("Colle le contenu de lint-staged.config.json sous la cle \"lint-staged\" de ton package.json")

    return 0
