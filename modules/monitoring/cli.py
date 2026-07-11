"""
modules/monitoring/cli.py
--------------------------
Logique CLI du module Monitoring d'OpsForge.
Appele via `python main.py monitoring ...`.
"""

import argparse
import json
import os
import sys

from modules.monitoring.core import (
    generate_combined,
    write_files,
    list_presets,
    get_preset,
    SUPPORTED_MODES,
)

# Dossier de sortie par defaut : output/ a la racine du projet OpsForge
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge monitoring",
        description=(
            "Genere de la configuration de monitoring : prometheus.yml, "
            "regles d'alerte Prometheus, ou datasources Grafana."
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
        "--mode",
        choices=SUPPORTED_MODES,
        default=None,
        help="Surcharge le mode (prometheus / alerts / grafana).",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Dossier de sortie (defaut : output/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche la config generee sans rien ecrire sur disque.",
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

    if args.mode:
        config["mode"] = args.mode

    return config


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_presets:
        print("Presets disponibles :")
        for name in list_presets():
            print(f"  - {name}")
        return 0

    config = _load_config(args)

    if args.dry_run:
        try:
            content = generate_combined(config)
        except ValueError as e:
            print(f"Erreur : {e}")
            return 1
        print("\n--- Apercu (dry-run) ---\n")
        print(content)
        print("--- Fin de l'apercu : rien n'a ete ecrit sur disque ---")
        return 0

    output_dir = args.output_dir or OUTPUT_DIR

    try:
        paths = write_files(config, output_dir)
    except ValueError as e:
        print(f"Erreur : {e}")
        return 1

    print("\nFichier(s) de monitoring genere(s) avec succes :")
    for path in paths:
        print(f"  - {path}")
    return 0
