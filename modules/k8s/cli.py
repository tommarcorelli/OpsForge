"""
modules/k8s/cli.py
------------------
Logique CLI du module Kubernetes/Helm d'OpsForge.
Appele via `python main.py k8s ...`.
"""

import argparse
import os
import sys

from modules.k8s.core import (
    generate_manifests_combined,
    generate_helm_chart,
    write_manifests,
    write_helm_chart,
    valider_config,
    SERVICE_TYPES,
)

# Dossier de sortie par defaut : output/ a la racine du projet OpsForge
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge k8s",
        description=(
            "Genere des manifests Kubernetes (Deployment + Service + Ingress) "
            "ou un squelette de chart Helm."
        ),
    )
    parser.add_argument("--name", required=True,
                        help="Nom de l'application (DNS-1123 : minuscules, chiffres, '-').")
    parser.add_argument("--image", required=True,
                        help="Image du conteneur (ex: monuser/mon-app:1.0.0).")
    parser.add_argument("--replicas", type=int, default=2,
                        help="Nombre de replicas (defaut : 2).")
    parser.add_argument("--port", dest="container_port", type=int, default=8080,
                        help="Port du conteneur (defaut : 8080).")
    parser.add_argument("--service-type", choices=SERVICE_TYPES, default="ClusterIP",
                        help="Type de Service Kubernetes (defaut : ClusterIP).")
    parser.add_argument("--service-port", type=int, default=80,
                        help="Port du Service (defaut : 80).")
    parser.add_argument("--namespace", default=None,
                        help="Namespace cible (genere aussi son manifest en mode manifests).")
    parser.add_argument("--env", action="append", default=[], metavar="CLE=VALEUR",
                        help="Variable d'environnement (repetable) : --env LOG_LEVEL=info")
    parser.add_argument("--probe-path", default=None,
                        help="Chemin HTTP des probes liveness/readiness (ex: /health).")
    parser.add_argument("--ingress-host", default=None,
                        help="Active l'Ingress avec ce host (ex: app.example.com).")
    parser.add_argument("--ingress-path", default="/",
                        help="Chemin de l'Ingress (defaut : /).")
    parser.add_argument("--ingress-class", default="",
                        help="ingressClassName (ex: nginx).")
    parser.add_argument("--tls", action="store_true",
                        help="Active le TLS sur l'Ingress (secret <name>-tls).")
    parser.add_argument("--helm", action="store_true",
                        help="Genere un squelette de chart Helm au lieu de manifests bruts.")
    parser.add_argument("--output", default=None,
                        help="Dossier de sortie (defaut : output/k8s/ ou output/<name>-chart/).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche le resultat dans le terminal sans rien ecrire sur disque.")
    return parser


def _parse_env_args(env_args):
    env = {}
    for item in env_args:
        if "=" not in item:
            print(f"Erreur : --env attend CLE=VALEUR, recu '{item}'.")
            sys.exit(1)
        key, value = item.split("=", 1)
        env[key.strip()] = value
    return env


def _config_from_args(args):
    config = {
        "name": args.name.strip(),
        "image": args.image.strip(),
        "replicas": args.replicas,
        "container_port": args.container_port,
        "service_type": args.service_type,
        "service_port": args.service_port,
        "namespace": args.namespace,
        "env": _parse_env_args(args.env),
        "probe_path": args.probe_path,
    }
    if args.ingress_host:
        config["ingress"] = {
            "host": args.ingress_host.strip(),
            "path": args.ingress_path,
            "class": args.ingress_class,
            "tls": args.tls,
        }
    return config


def main(argv=None):
    args = build_parser().parse_args(argv)
    config = _config_from_args(args)

    erreurs, avertissements = valider_config(config)
    if erreurs:
        for e in erreurs:
            print(f"Erreur : {e}")
        sys.exit(1)
    for a in avertissements:
        print(f"Attention : {a}")

    if args.dry_run:
        if args.helm:
            files = generate_helm_chart(config)
            print(f"\n--- Apercu (dry-run) : chart Helm '{config['name']}' ---")
            for rel_path in sorted(files):
                print(f"\n### {rel_path} " + "#" * max(0, 60 - len(rel_path)))
                print(files[rel_path])
        else:
            print(f"\n--- Apercu (dry-run) : manifests '{config['name']}' ---\n")
            print(generate_manifests_combined(config))
        print("--- Fin de l'apercu : rien n'a ete ecrit sur disque ---")
        return

    if args.helm:
        output_dir = args.output or os.path.join(OUTPUT_DIR, f"{config['name']}-chart")
        written = write_helm_chart(config, output_dir)
        print(f"\nChart Helm genere : {output_dir}")
        for path in written:
            print(f"  - {path}")
        print(f"\nPour deployer : helm install {config['name']} {output_dir}")
    else:
        output_dir = args.output or os.path.join(OUTPUT_DIR, "k8s")
        written = write_manifests(config, output_dir)
        print(f"\nManifests generes : {output_dir}")
        for path in written:
            print(f"  - {path}")
        print(f"\nPour deployer : kubectl apply -f {output_dir}/")
