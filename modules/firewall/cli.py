"""
modules/firewall/cli.py
------------------------
Logique CLI du module firewall d'OpsForge.
Appele via `python main.py firewall ...`.
"""

import argparse
import json
import os

from modules.firewall.core import (
    SUPPORTED_BACKENDS,
    generate_firewall,
    get_preset,
    list_presets,
    write_firewall,
)

# Dossier de sortie par defaut : output/ a la racine du projet OpsForge
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge firewall",
        description=(
            "Genere des regles pare-feu (ufw ou nftables) + config fail2ban "
            "en option, a partir d'un preset ou d'une config JSON."
        ),
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        default=None,
        help="Fichier JSON decrivant les regles (voir --preset pour un depart rapide).",
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
        help="Surcharge le backend (ufw / nftables).",
    )
    parser.add_argument(
        "--fail2ban",
        action="store_true",
        help="Ajoute une config fail2ban (jail.local) a la sortie.",
    )
    parser.add_argument(
        "--no-fail2ban",
        action="store_true",
        help="Desactive fail2ban meme si le preset l'active par defaut.",
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
    if args.fail2ban:
        config["fail2ban"] = True
    if args.no_fail2ban:
        config["fail2ban"] = False

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
            files = generate_firewall(config)
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
        paths = write_firewall(config, output_dir)
    except ValueError as e:
        print(f"Erreur : {e}")
        return 1

    print("\nFichier(s) pare-feu genere(s) avec succes :")
    for path in paths:
        print(f"  - {path}")

    backend = config.get("backend", "ufw")
    if backend == "ufw":
        print(f"\nPour appliquer : sudo bash {output_dir}/setup-firewall.sh")
    else:
        print(f"\nPour appliquer : sudo cp {output_dir}/nftables.conf /etc/nftables.conf && sudo systemctl enable --now nftables")

    if config.get("fail2ban"):
        print(f"Pour fail2ban : sudo cp {output_dir}/jail.local /etc/fail2ban/jail.local && sudo systemctl restart fail2ban")

    return 0
