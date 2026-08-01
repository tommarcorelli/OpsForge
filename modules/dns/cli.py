"""
modules/dns/cli.py
-------------------
Logique CLI du module dns d'OpsForge.
Appele via `python main.py dns ...`.
"""

import argparse
import json
import os

from modules.dns.core import (
    SUPPORTED_ENGINES,
    generate_dns,
    get_preset,
    list_presets,
    write_dns,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge dns",
        description=(
            "Genere des enregistrements DNS : fichier de zone BIND (RFC 1035, "
            "universel) ou lot de changements JSON pour AWS Route53."
        ),
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        default=None,
        help="Fichier JSON decrivant les enregistrements (voir --preset pour un depart rapide).",
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
        "--engine",
        choices=SUPPORTED_ENGINES,
        default=None,
        help="Format de sortie (bind / route53). Defaut : bind.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Dossier de sortie (defaut : output/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le fichier genere sans rien ecrire sur disque.",
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

    if args.engine:
        config["engine"] = args.engine

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
            files = generate_dns(config)
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
        paths = write_dns(config, output_dir)
    except ValueError as e:
        print(f"Erreur : {e}")
        return 1

    print("\nFichier(s) genere(s) avec succes :")
    for path in paths:
        print(f"  - {path}")

    engine = config.get("engine", "bind")
    if engine == "bind":
        print("\nCote serveur : deploie ce fichier comme zone maitre (BIND/PowerDNS/Knot).")
        print("Cote registrar : certains acceptent un import direct de fichier de zone.")
    else:
        print("\nApplique avec :")
        print(f"  aws route53 change-resource-record-sets --hosted-zone-id TON_ZONE_ID --change-batch file://{paths[0]}")

    return 0
