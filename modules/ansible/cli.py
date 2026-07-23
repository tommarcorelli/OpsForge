"""
modules/ansible/cli.py
----------------------
Logique CLI du module Ansible d'OpsForge (provisioning + deploiement).
Appele via `python main.py ansible ...`.
"""

import argparse
import os
import sys

from modules.ansible.core import (
    generate_inventory,
    generate_playbook,
    write_playbook,
    write_vault_file,
    write_role_based_project,
    generate_multi_group_inventory,
    write_multi_group_project,
    SUPPORTED_LANGUAGES,
    DATABASE_ENGINES,
    TARGET_OSES,
)

# Dossier de sortie par defaut : output/ a la racine du projet OpsForge
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="opsforge ansible",
        description="Genere un playbook Ansible (provisioning + deploiement).",
    )

    parser.add_argument(
        "--lang",
        choices=SUPPORTED_LANGUAGES,
        default=None,
        help="Langage/runtime de l'application a deployer (ignore si --groups-file est fourni)",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="URL du depot Git a deployer (ignore si --groups-file est fourni)",
    )
    parser.add_argument("--branch", default="main", help="Branche a deployer (defaut: main)")
    parser.add_argument(
        "--app-dir",
        default="/opt/mon-application",
        help="Chemin de deploiement sur le serveur (defaut: /opt/mon-application)",
    )
    parser.add_argument(
        "--service-name",
        default="mon-application",
        help="Nom du service systemd a redemarrer",
    )
    parser.add_argument(
        "--build-cmd",
        default=None,
        help="Commande de build a executer apres l'installation des dependances",
    )
    parser.add_argument(
        "--hosts-group",
        default="webservers",
        help="Nom du groupe d'hotes Ansible (defaut: webservers)",
    )

    parser.add_argument(
        "--provisioning",
        nargs="+",
        choices=["update_system", "base_packages", "timezone", "swap", "unattended_upgrades", "users", "docker", "nginx", "https", "database", "backups", "firewall", "ssh_hardening", "fail2ban", "monitoring", "runtime"],
        default=["update_system", "base_packages", "runtime"],
        help="Etapes de provisioning a inclure",
    )
    parser.add_argument(
        "--deployment",
        nargs="+",
        choices=["backup_previous", "git_clone", "zero_downtime_deploy", "install_deps", "build", "restart_service", "reload_nginx", "health_check", "notify"],
        default=["git_clone", "install_deps", "restart_service"],
        help="Etapes de deploiement a inclure",
    )
    parser.add_argument("--notify-webhook-url", default=None, help="URL webhook Slack/Discord pour l'etape 'notify'")
    parser.add_argument("--domain-name", default=None, help="Nom de domaine pour Let's Encrypt (etape 'https')")
    parser.add_argument("--letsencrypt-email", default=None, help="Email pour Let's Encrypt (etape 'https')")
    parser.add_argument(
        "--database-engine",
        choices=DATABASE_ENGINES,
        default=None,
        help="Moteur de base de donnees pour l'etape 'database' (postgresql, mysql, redis, mongodb)",
    )
    parser.add_argument("--db-name", default=None, help="Nom de la base de donnees applicative")
    parser.add_argument("--db-user", default=None, help="Utilisateur applicatif de la base de donnees")
    parser.add_argument("--backup-dir", default=None, help="Dossier de sauvegarde pour l'etape 'backups' (defaut: /opt/backups)")
    parser.add_argument("--backup-retention-days", default=None, help="Retention des sauvegardes en jours (defaut: 7)")
    parser.add_argument("--backup-hour", default=None, help="Heure d'execution quotidienne de la sauvegarde, 0-23 (defaut: 2)")
    parser.add_argument(
        "--target-os",
        choices=TARGET_OSES,
        default="linux",
        help="OS cible : 'linux' (defaut, SSH) ou 'windows' (WinRM). "
             "Seul un sous-ensemble d'etapes est disponible cote Windows "
             "(voir --list-windows-steps).",
    )
    parser.add_argument(
        "--list-windows-steps",
        action="store_true",
        help="Affiche les etapes de provisioning/deploiement disponibles pour une cible Windows, et quitte.",
    )
    parser.add_argument("--winrm-transport", default="ntlm", help="Transport WinRM : ntlm (defaut), basic, kerberos ou credssp")
    parser.add_argument("--winrm-port", type=int, default=None, help="Port WinRM (defaut : 5986 en HTTPS, 5985 en transport 'basic')")
    parser.add_argument("--winrm-password", default=None, help="Mot de passe WinRM ecrit dans l'inventaire (a eviter en clair en production : prefere le vault)")
    parser.add_argument(
        "--health-check-port",
        default=None,
        help="Port a verifier pour l'etape health_check (defaut: 80)",
    )

    parser.add_argument(
        "--output",
        default=None,
        help="Chemin de sortie du playbook (defaut : output/playbook.yml)",
    )

    parser.add_argument(
        "--inventory-host",
        default=None,
        help="Si fourni, genere aussi un fichier inventory.ini avec cet hote",
    )
    parser.add_argument("--ssh-user", default="deploy", help="Utilisateur SSH / de deploiement (defaut: deploy)")
    parser.add_argument("--ssh-public-key", default=None, help="Cle SSH publique a autoriser pour l'etape 'users'")

    parser.add_argument(
        "--vault-var",
        action="append",
        metavar="CLE=VALEUR",
        help="Secret a chiffrer avec Ansible Vault (repetable, ex: --vault-var db_password=hunter2)",
    )
    parser.add_argument(
        "--vault-password",
        default=None,
        help="Mot de passe du vault (attention : visible dans l'historique du shell)",
    )
    parser.add_argument(
        "--vault-password-file",
        default=None,
        help="Chemin vers un fichier contenant le mot de passe du vault (recommande)",
    )

    parser.add_argument(
        "--layout",
        choices=["flat", "roles"],
        default="flat",
        help=(
            "Structure du projet genere : 'flat' (un seul playbook.yml, defaut) "
            "ou 'roles' (un role Ansible independant par etape, bonnes pratiques)"
        ),
    )

    parser.add_argument(
        "--groups-file",
        default=None,
        help=(
            "Mode multi-serveurs : chemin vers un fichier JSON decrivant plusieurs "
            "groupes de serveurs (voir README). Si fourni, ignore --lang/--repo/etc. "
            "et force la structure en roles."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Affiche le playbook genere dans le terminal sans rien ecrire sur disque. "
            "Disponible uniquement pour le layout 'flat' (pas pour --layout roles "
            "ni --groups-file)."
        ),
    )

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.list_windows_steps:
        from modules.ansible.core import (
            WINDOWS_SUPPORTED_PROVISIONING,
            WINDOWS_SUPPORTED_DEPLOYMENT,
            WINDOWS_SUPPORTED_LANGUAGES,
        )
        print("Etapes de provisioning disponibles pour --target-os windows :")
        print("  " + ", ".join(WINDOWS_SUPPORTED_PROVISIONING))
        print("Etapes de deploiement disponibles pour --target-os windows :")
        print("  " + ", ".join(WINDOWS_SUPPORTED_DEPLOYMENT))
        print("Langages disponibles (runtime / install_deps) pour --target-os windows :")
        print("  " + ", ".join(WINDOWS_SUPPORTED_LANGUAGES))
        return

    if args.dry_run and (args.groups_file or args.layout == "roles"):
        print("Erreur : --dry-run n'est disponible que pour le layout 'flat' "
              "(pas --layout roles ni --groups-file).")
        sys.exit(1)

    vault_vars = {}
    if args.vault_var:
        for item in args.vault_var:
            if "=" not in item:
                print(f"Erreur : --vault-var attend un format CLE=VALEUR, recu : {item}")
                sys.exit(1)
            key, value = item.split("=", 1)
            vault_vars[key.strip()] = value

    vault_password = None
    if vault_vars:
        vault_password = args.vault_password
        if not vault_password and args.vault_password_file:
            with open(args.vault_password_file, "r", encoding="utf-8") as f:
                vault_password = f.read().strip()
        if not vault_password:
            print("Erreur : --vault-var necessite --vault-password ou --vault-password-file")
            sys.exit(1)

    # -------------------- Mode "multi-serveurs" (--groups-file) --------------------
    if args.groups_file:
        import json

        with open(args.groups_file, "r", encoding="utf-8") as f:
            try:
                groups = json.load(f)
            except json.JSONDecodeError as e:
                print(f"Erreur : {args.groups_file} n'est pas un JSON valide ({e})")
                sys.exit(1)

        if not isinstance(groups, list):
            print("Erreur : le fichier --groups-file doit contenir une liste de groupes (JSON array).")
            sys.exit(1)

        output_dir = args.output or OUTPUT_DIR

        try:
            written = write_multi_group_project(
                groups, output_dir, vault_vars=vault_vars or None, vault_password=vault_password
            )
        except ValueError as e:
            print(f"Erreur : {e}")
            sys.exit(1)

        print(f"Projet multi-serveurs genere dans : {output_dir}/")
        print(f"Groupes : {', '.join(g.get('hosts_group', '?') for g in groups)}")
        print(f"Fichiers ecrits : {len(written)}")

        inventory_content = generate_multi_group_inventory(groups)
        inventory_path = os.path.join(output_dir, "inventory.ini")
        with open(inventory_path, "w", encoding="utf-8") as f:
            f.write(inventory_content)
        print(f"Inventaire genere : {inventory_path}")

        print(
            "Pour executer le playbook : cd "
            f"{output_dir} && ansible-playbook -i inventory.ini playbook.yml"
            + (" --ask-vault-pass" if vault_vars else "")
        )
        return

    # -------------------- Mode simple (un seul groupe/cible) --------------------
    if not args.lang or not args.repo:
        print("Erreur : --lang et --repo sont requis (sauf en mode --groups-file).")
        sys.exit(1)

    config = {
        "hosts_group": args.hosts_group,
        "provisioning": args.provisioning,
        "runtime_language": args.lang,
        "deployment": args.deployment,
        "deployment_language": args.lang,
        "repo_url": args.repo,
        "branch": args.branch,
        "app_dir": args.app_dir,
        "service_name": args.service_name,
        "build_cmd": args.build_cmd or f"echo 'Aucune commande de build definie pour {args.lang}'",
        "vault_vars": vault_vars or None,
        "health_check_port": args.health_check_port,
        "domain_name": args.domain_name,
        "letsencrypt_email": args.letsencrypt_email,
        "database_engine": args.database_engine,
        "db_name": args.db_name,
        "db_user": args.db_user,
        "backup_dir": args.backup_dir,
        "backup_retention_days": args.backup_retention_days,
        "backup_hour": args.backup_hour,
        "notify_webhook_url": args.notify_webhook_url,
        "deploy_user": args.ssh_user,
        "ssh_public_key": args.ssh_public_key,
        "target_os": args.target_os,
    }

    if args.layout == "roles":
        # Mode "roles" : --output est traite comme un DOSSIER de sortie
        output_dir = args.output or OUTPUT_DIR

        try:
            written = write_role_based_project(config, output_dir)
        except ValueError as e:
            print(f"Erreur : {e}")
            sys.exit(1)

        print(f"Projet en roles genere dans : {output_dir}/")
        print("  - playbook.yml, vars.yml, ansible.cfg")
        print(f"  - {len(written) - 3} fichiers de roles ({', '.join(config['provisioning'] + config['deployment'])})")

        if vault_vars:
            vault_path = os.path.join(output_dir, "vault.yml")
            try:
                write_vault_file(vault_vars, vault_password, vault_path)
            except ImportError as e:
                print(f"Erreur : {e}")
                sys.exit(1)
            print(f"Vault genere : {vault_path} ({', '.join(vault_vars.keys())})")

        if args.inventory_host:
            inventory_content = generate_inventory(
                args.hosts_group, args.inventory_host, args.ssh_user,
                target_os=args.target_os,
                winrm_password=args.winrm_password,
                winrm_transport=args.winrm_transport,
                winrm_port=args.winrm_port,
            )
            inventory_path = os.path.join(output_dir, "inventory.ini")
            with open(inventory_path, "w", encoding="utf-8") as f:
                f.write(inventory_content)
            print(f"Inventaire genere : {inventory_path}")

        print(
            "Pour executer le playbook : cd "
            f"{output_dir} && ansible-playbook -i inventory.ini playbook.yml"
            + (" --ask-vault-pass" if vault_vars else "")
        )
        return

    # -------------------- Mode "flat" (comportement historique) --------------------
    output_path = args.output or os.path.join(OUTPUT_DIR, "playbook.yml")

    if args.dry_run:
        try:
            content = generate_playbook(config)
        except ValueError as e:
            print(f"Erreur : {e}")
            sys.exit(1)
        print(f"\n--- Apercu (dry-run) : {output_path} ---\n")
        print(content)
        print("--- Fin de l'apercu : rien n'a ete ecrit sur disque ---")
        if vault_vars:
            print(
                f"\nNote : {len(vault_vars)} variable(s) vault ({', '.join(vault_vars.keys())}) "
                "ne sont pas chiffrees ni affichees ici. Lance sans --dry-run pour generer "
                "vault.yml."
            )
        return

    try:
        write_playbook(config, output_path)
    except ValueError as e:
        print(f"Erreur : {e}")
        sys.exit(1)

    print(f"Playbook genere : {output_path}")
    print(f"Provisioning : {', '.join(args.provisioning)}")
    print(f"Deploiement : {', '.join(args.deployment)}")

    if vault_vars:
        vault_path = os.path.join(os.path.dirname(output_path), "vault.yml")
        try:
            write_vault_file(vault_vars, vault_password, vault_path)
        except ImportError as e:
            print(f"Erreur : {e}")
            sys.exit(1)
        print(f"Vault genere : {vault_path} ({', '.join(vault_vars.keys())})")
        print(
            "Pour executer le playbook : "
            "ansible-playbook -i inventory.ini playbook.yml --ask-vault-pass"
        )

    if args.inventory_host:
        inventory_content = generate_inventory(
            args.hosts_group, args.inventory_host, args.ssh_user,
            target_os=args.target_os,
            winrm_password=args.winrm_password,
            winrm_transport=args.winrm_transport,
            winrm_port=args.winrm_port,
        )
        inventory_path = os.path.join(os.path.dirname(output_path), "inventory.ini")
        with open(inventory_path, "w", encoding="utf-8") as f:
            f.write(inventory_content)
        print(f"Inventaire genere : {inventory_path}")
