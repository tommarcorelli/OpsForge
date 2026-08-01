"""
modules/ssh/cli.py
------------------
Logique CLI du module ssh d'OpsForge.
Appele via `python main.py ssh ...`.
"""

import argparse
import json
import os

from modules.ssh.core import (
    PRESETS,
    SUPPORTED_ROLES,
    generate_ssh,
    get_preset,
    list_presets,
    write_ssh,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge ssh",
        description=(
            "Genere une configuration SSH : fichier client ~/.ssh/config "
            "(alias, cles, bastion, tunnels) ou fragment de durcissement "
            "sshd_config.d/ cote serveur."
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
        "--role",
        choices=SUPPORTED_ROLES,
        default=None,
        help="Surcharge le role (client : ~/.ssh/config, server : sshd_config.d/).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="[server] Surcharge le port d'ecoute de sshd.",
    )
    parser.add_argument(
        "--allow-groups",
        nargs="+",
        default=None,
        help="[server] Groupes autorises a se connecter (AllowGroups).",
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

    if args.role:
        config["role"] = args.role
    if args.port is not None:
        config["port"] = args.port
    if args.allow_groups is not None:
        config["allow_groups"] = args.allow_groups

    return config


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_presets:
        print("Presets disponibles :")
        for name in list_presets():
            preset = PRESETS[name]
            print(f"  - {name:<18} [{preset['role']}] {preset['label']}")
        return 0

    config = _load_config(args)
    if config is None:
        return 1

    if args.dry_run:
        try:
            files = generate_ssh(config)
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
        paths = write_ssh(config, output_dir)
    except ValueError as e:
        print(f"Erreur : {e}")
        return 1

    print("\nFichier(s) genere(s) avec succes :")
    for path in paths:
        print(f"  - {path}")

    if config.get("role", "client") == "client":
        print("\nInstallation : copie le contenu dans ~/.ssh/config puis chmod 600 ~/.ssh/config")
        print("Test : ssh -G <alias> affiche la config effective sans se connecter.")
    else:
        print("\nInstallation : copie le fragment dans /etc/ssh/sshd_config.d/ (root:root, 644)")
        print("Verifie AVANT de recharger : sudo sshd -t")
        print("Puis : sudo systemctl reload ssh   (garde ta session ouverte le temps de tester)")

    return 0
