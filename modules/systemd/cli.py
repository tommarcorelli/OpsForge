"""
modules/systemd/cli.py
-----------------------
Logique CLI du module systemd d'OpsForge.
Appele via `python main.py systemd ...`.
"""

import argparse
import json
import os
import sys

from modules.systemd.core import (
    generate_combined,
    write_units,
    list_presets,
    get_preset,
    SUPPORTED_MODES,
    SERVICE_TYPES,
)

# Dossier de sortie par defaut : output/ a la racine du projet OpsForge
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge systemd",
        description=(
            "Genere des unites systemd (.service et .timer) : services "
            "supervises (redemarrage auto, durcissement) ou taches planifiees."
        ),
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        default=None,
        help="Fichier JSON decrivant l'unite (voir --preset pour un depart rapide).",
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
        help="Surcharge le mode (service / timer).",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Surcharge le nom de l'unite.",
    )
    parser.add_argument(
        "--exec-start",
        default=None,
        help="Surcharge la commande a executer (ExecStart).",
    )
    parser.add_argument(
        "--type",
        dest="service_type",
        choices=SERVICE_TYPES,
        default=None,
        help="Surcharge le type de service (simple / exec / forking / oneshot / notify).",
    )
    parser.add_argument(
        "--on-calendar",
        default=None,
        help="Planification OnCalendar (mode timer), ex : '*-*-* 02:00:00'.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Dossier de sortie (defaut : output/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche les unites generees sans rien ecrire sur disque.",
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
    if args.name:
        config["name"] = args.name
    if args.exec_start:
        config["exec_start"] = args.exec_start
    if args.service_type:
        config["service_type"] = args.service_type
    if args.on_calendar:
        config["on_calendar"] = args.on_calendar

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
        paths = write_units(config, output_dir)
    except ValueError as e:
        print(f"Erreur : {e}")
        return 1

    print("\nUnite(s) systemd generee(s) avec succes :")
    for path in paths:
        print(f"  - {path}")

    name = (config.get("name") or "unit").strip()
    unit_to_enable = f"{name}.timer" if config.get("mode") == "timer" else f"{name}.service"
    print(
        f"\nPour installer : sudo cp {output_dir}/{name}.* /etc/systemd/system/ "
        f"&& sudo systemctl daemon-reload && sudo systemctl enable --now {unit_to_enable}"
    )
    return 0
