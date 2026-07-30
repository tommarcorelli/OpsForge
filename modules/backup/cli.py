"""
modules/backup/cli.py
-----------------------
Logique CLI du module Backup/Restore d'OpsForge (restic / Borg).
Appele via `python main.py backup ...`.
"""

import argparse
import json
import os
import sys

from modules.backup.core import (
    generate_files,
    get_preset,
    list_backends,
    list_presets,
    list_schedulers,
    list_tools,
    write_files,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge backup",
        description=(
            "Genere un script de sauvegarde/restauration idempotent (restic ou "
            "Borg), sa planification (systemd timer ou cron) et un fichier "
            "d'environnement modele, a partir d'un fichier JSON ou d'un preset."
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
    parser.add_argument("--list-presets", action="store_true", help="Affiche les presets disponibles et quitte.")
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help=f"Affiche les outils geres ({', '.join(list_tools())}) et quitte.",
    )
    parser.add_argument(
        "--list-backends",
        action="store_true",
        help=f"Affiche les backends geres ({', '.join(list_backends())}) et quitte.",
    )
    parser.add_argument(
        "--list-schedulers",
        action="store_true",
        help=f"Affiche les planificateurs geres ({', '.join(list_schedulers())}) et quitte.",
    )
    parser.add_argument("-o", "--output-dir", default=None, help="Dossier de sortie (defaut : output/).")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Affiche les fichiers generes sans rien ecrire sur disque.",
    )
    return parser


def _load_config(args):
    if args.config_file:
        with open(args.config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    if args.preset:
        try:
            return get_preset(args.preset)
        except ValueError as e:
            print(f"Erreur : {e}")
            sys.exit(1)
    print(f"Erreur : fournis un fichier de config JSON ou --preset ({', '.join(list_presets())}).")
    sys.exit(1)


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_presets:
        print("Presets disponibles :")
        for name in list_presets():
            print(f"  - {name}")
        return 0
    if args.list_tools:
        print("Outils geres :")
        for name in list_tools():
            print(f"  - {name}")
        return 0
    if args.list_backends:
        print("Backends geres :")
        for name in list_backends():
            print(f"  - {name}")
        return 0
    if args.list_schedulers:
        print("Planificateurs geres :")
        for name in list_schedulers():
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

    print("\nFichiers de sauvegarde generes avec succes :")
    for path in paths:
        print(f"  - {path}")

    print(
        "\nProchaines etapes : copie 'backup.env.example' en 'backup.env' dans le "
        "meme dossier, renseigne les vraies valeurs (JAMAIS committees dans Git), "
        "puis installe le service (systemd) ou la ligne crontab generee."
    )
    return 0
