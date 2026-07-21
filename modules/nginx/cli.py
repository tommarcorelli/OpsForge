"""
modules/nginx/cli.py
---------------------
Logique CLI du module Nginx d'OpsForge.
Appele via `python main.py nginx ...`.
"""

import argparse
import json
import os
import sys

from modules.nginx.core import (
    generate,
    list_presets,
    get_preset,
    SUPPORTED_MODES,
    SUPPORTED_TARGETS,
)

# Dossier de sortie par defaut : output/ a la racine du projet OpsForge
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge nginx",
        description=(
            "Genere un bloc de configuration Nginx (server{} / upstream{}) : "
            "site statique, reverse proxy, ou load balancer."
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
        help="Surcharge le mode (static / reverse_proxy / load_balancer).",
    )
    parser.add_argument(
        "--target",
        choices=SUPPORTED_TARGETS,
        default="nginx",
        help="Format de sortie : nginx (defaut, server{}/upstream{}), "
             "caddy (Caddyfile) ou traefik (config dynamique YAML). "
             "Traefik ne supporte pas le mode 'static'.",
    )
    parser.add_argument(
        "--server-name",
        default=None,
        help="Surcharge le nom de domaine (server_name).",
    )
    parser.add_argument(
        "--https",
        action="store_true",
        help="Active HTTPS (redirection 80->443 + bloc ssl_certificate Let's Encrypt).",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Chemin de sortie (defaut : output/<server_name>.conf).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche la config generee dans le terminal sans rien ecrire sur disque.",
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
    if args.server_name:
        config["server_name"] = args.server_name
    if args.https:
        config["https"] = True

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
            content = generate(config, target=args.target)
        except ValueError as e:
            print(f"Erreur : {e}")
            return 1
        print("\n--- Apercu (dry-run) ---\n")
        print(content)
        print("--- Fin de l'apercu : rien n'a ete ecrit sur disque ---")
        return 0

    server_name = (config.get("server_name") or "app").strip()
    ext = {"nginx": "conf", "caddy": "Caddyfile", "traefik": "yml"}.get(args.target, "conf")
    default_name = "Caddyfile" if args.target == "caddy" else f"{server_name}.{ext}"
    output_path = args.output or os.path.join(OUTPUT_DIR, default_name)

    try:
        content = generate(config, target=args.target)
    except ValueError as e:
        print(f"Erreur : {e}")
        return 1

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\nConfig generee avec succes (cible: {args.target}) : {output_path}")
    if args.target == "nginx":
        print(
            f"Pour l'activer : sudo cp {output_path} /etc/nginx/sites-available/{server_name} "
            f"&& sudo ln -s /etc/nginx/sites-available/{server_name} /etc/nginx/sites-enabled/ "
            f"&& sudo nginx -t && sudo systemctl reload nginx"
        )
    elif args.target == "caddy":
        print(f"Pour l'activer : ajoute le contenu de {output_path} a ton Caddyfile, puis `caddy reload`.")
    else:
        print(
            f"Pour l'activer : copie {output_path} dans le dossier surveille par le provider "
            "\"file\" de Traefik (ex: /etc/traefik/dynamic/)."
        )
    return 0
