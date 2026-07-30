"""
modules/backup/core.py
------------------------
Coeur du module Backup/Restore d'OpsForge — genere un script de sauvegarde
idempotent, un script de restauration, la planification (systemd timer ou
cron) et un fichier d'environnement modele (secrets JAMAIS en dur), pour
deux outils :

  - **restic**  : backends local / sftp / s3.
  - **Borg**    : backends local / sftp (pas de S3 natif sans rclone-mount,
                   volontairement non propose pour rester honnete sur les
                   capacites reelles de l'outil).

Fonctions cles :
  - generate_backup_script(config)   -> str (backup.sh)
  - generate_restore_script(config)  -> str (restore.sh)
  - generate_systemd_units(config)   -> {nom_fichier: contenu} (si scheduler=systemd)
  - generate_cron_entry(config)      -> str (ligne crontab, si scheduler=cron)
  - generate_env_template(config)    -> str (backup.env.example)
  - generate_files(config)           -> {nom_fichier: contenu} (dispatch complet)
  - validate_config(config)          -> liste d'erreurs (vide si valide)
  - PRESETS / get_preset             -> configs pretes a l'emploi
"""

import copy
import os
import re

TOOLS = ("restic", "borg")
BACKENDS = ("local", "sftp", "s3")
SCHEDULERS = ("systemd", "cron")

_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")

DEFAULT_RETENTION = {"keep_daily": 7, "keep_weekly": 4, "keep_monthly": 6, "keep_yearly": 0}


def _clean(value):
    return value.strip() if isinstance(value, str) else value


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate_config(config):
    errors = []
    if not isinstance(config, dict):
        return ["La configuration doit etre un objet JSON."]

    tool = _clean(config.get("tool"))
    if not tool:
        errors.append("Le champ 'tool' est obligatoire.")
    elif tool not in TOOLS:
        errors.append(f"tool inconnu : '{tool}'. Disponibles : {', '.join(TOOLS)}.")

    app_name = _clean(config.get("app_name")) or "opsforge-backup"
    if not _NAME_RE.match(app_name):
        errors.append(
            "app_name invalide : lettres, chiffres, points, tirets et underscores uniquement."
        )

    repo_backend = _clean(config.get("repo_backend")) or "local"
    if repo_backend not in BACKENDS:
        errors.append(f"repo_backend inconnu : '{repo_backend}'. Disponibles : {', '.join(BACKENDS)}.")
    elif repo_backend == "s3" and tool == "borg":
        errors.append(
            "Borg ne gere pas nativement le backend S3 (contrairement a restic) : "
            "utilise 'local' ou 'sftp', ou passe par un montage rclone en dehors d'OpsForge."
        )

    if not _clean(config.get("repo_path")):
        errors.append("Le champ 'repo_path' est obligatoire (chemin du repository).")

    source_paths = config.get("source_paths")
    if not source_paths or not isinstance(source_paths, list) or not all(source_paths):
        errors.append("Le champ 'source_paths' est obligatoire (liste non vide de chemins a sauvegarder).")

    if repo_backend == "sftp":
        if not _clean(config.get("sftp_host")):
            errors.append("sftp_host est requis quand repo_backend='sftp'.")
        if not _clean(config.get("sftp_user")):
            errors.append("sftp_user est requis quand repo_backend='sftp'.")

    if repo_backend == "s3" and tool == "restic" and not _clean(config.get("s3_bucket")):
        errors.append("s3_bucket est requis quand repo_backend='s3'.")

    scheduler = _clean(config.get("scheduler")) or "systemd"
    if scheduler not in SCHEDULERS:
        errors.append(f"scheduler inconnu : '{scheduler}'. Disponibles : {', '.join(SCHEDULERS)}.")

    retention = config.get("retention") or {}
    if not isinstance(retention, dict):
        errors.append("Le champ 'retention' doit etre un objet (keep_daily/keep_weekly/keep_monthly/keep_yearly).")
    else:
        for key, value in retention.items():
            if key not in DEFAULT_RETENTION:
                errors.append(f"Cle de retention inconnue : '{key}'. Disponibles : {', '.join(DEFAULT_RETENTION)}.")
            elif not isinstance(value, int) or value < 0:
                errors.append(f"retention.{key} doit etre un entier positif ou nul.")

    return errors


# --------------------------------------------------------------------------
# Construction de l'URL/chemin du repository
# --------------------------------------------------------------------------
def _repo_url(config):
    tool = _clean(config["tool"])
    backend = _clean(config.get("repo_backend")) or "local"
    repo_path = _clean(config["repo_path"])

    if backend == "local":
        return repo_path

    if backend == "sftp":
        host = _clean(config["sftp_host"])
        user = _clean(config["sftp_user"])
        if tool == "restic":
            return f"sftp:{user}@{host}:{repo_path}"
        return f"{user}@{host}:{repo_path}"  # borg : syntaxe ssh classique

    # backend == "s3" (restic uniquement, deja valide en amont)
    bucket = _clean(config["s3_bucket"])
    endpoint = _clean(config.get("s3_endpoint")) or "s3.amazonaws.com"
    prefix = repo_path.strip("/")
    return f"s3:{endpoint}/{bucket}/{prefix}" if prefix else f"s3:{endpoint}/{bucket}"


def _retention_flags(config, tool):
    retention = {**DEFAULT_RETENTION, **(config.get("retention") or {})}
    flags = []
    for key, cli_flag in (
        ("keep_daily", "--keep-daily"),
        ("keep_weekly", "--keep-weekly"),
        ("keep_monthly", "--keep-monthly"),
        ("keep_yearly", "--keep-yearly"),
    ):
        value = retention.get(key, 0)
        if value:
            flags.append(f"{cli_flag} {value}")
    return flags


def _notify_block(config, success):
    """Bloc shell optionnel de notification webhook (ex: healthchecks.io,
    ntfy.sh, ou n'importe quel endpoint acceptant un POST)."""
    if not config.get("notify_webhook_url"):
        return ""
    if success:
        return (
            "\n# Notifie le endpoint de monitoring en cas de succes (ex: healthchecks.io)\n"
            'curl -fsS -m 10 --retry 3 "${NOTIFY_WEBHOOK_URL}" >/dev/null 2>&1 || true\n'
        )
    return (
        "\nnotify_echec() {\n"
        '  curl -fsS -m 10 -X POST "${NOTIFY_WEBHOOK_URL}/fail" '
        '-d "Echec de la sauvegarde $(date -Iseconds)" >/dev/null 2>&1 || true\n'
        "}\n"
        "trap notify_echec ERR\n"
    )


# --------------------------------------------------------------------------
# backup.sh
# --------------------------------------------------------------------------
def generate_backup_script(config):
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    tool = _clean(config["tool"])
    app_name = _clean(config.get("app_name")) or "opsforge-backup"
    repo_url = _repo_url(config)
    passphrase_var = _clean(config.get("passphrase_env_var")) or "BACKUP_PASSPHRASE"
    source_paths = config["source_paths"]
    exclude_patterns = config.get("exclude_patterns") or []

    lignes = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        f"# OpsForge - sauvegarde automatique ({app_name}, {tool})",
        "# Genere par OpsForge. NE JAMAIS committer backup.env dans Git.",
        "",
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        'ENV_FILE="${SCRIPT_DIR}/backup.env"',
        'if [ -f "${ENV_FILE}" ]; then',
        "  set -a",
        '  source "${ENV_FILE}"',
        "  set +a",
        "fi",
        "",
    ]

    lignes.append(_notify_block(config, success=False).rstrip("\n"))

    if tool == "restic":
        lignes += [
            "",
            f'export RESTIC_REPOSITORY="{repo_url}"',
            f'export RESTIC_PASSWORD="${{{passphrase_var}:?variable {passphrase_var} manquante dans backup.env}}"',
            "",
            "# Initialise le repository au premier lancement (idempotent)",
            "restic snapshots >/dev/null 2>&1 || restic init",
            "",
            "restic backup \\",
        ]
        for path in source_paths:
            lignes.append(f'  "{path}" \\')
        for pattern in exclude_patterns:
            lignes.append(f"  --exclude '{pattern}' \\")
        lignes.append(f'  --tag "{app_name}"')

        retention_flags = _retention_flags(config, tool)
        if retention_flags:
            lignes += [
                "",
                "restic forget \\",
                *[f"  {flag} \\" for flag in retention_flags],
                "  --prune",
            ]

    else:  # borg
        lignes += [
            "",
            f'export BORG_REPO="{repo_url}"',
            f'export BORG_PASSPHRASE="${{{passphrase_var}:?variable {passphrase_var} manquante dans backup.env}}"',
            "",
            "# Initialise le repository au premier lancement (idempotent)",
            'borg info "${BORG_REPO}" >/dev/null 2>&1 || borg init --encryption=repokey "${BORG_REPO}"',
            "",
            'borg create --stats --compression lz4 \\',
            f'  "${{BORG_REPO}}::{app_name}-{{now:%Y-%m-%d_%H%M%S}}" \\',
        ]
        for path in source_paths[:-1]:
            lignes.append(f'  "{path}" \\')
        lignes.append(f'  "{source_paths[-1]}"' + (" \\" if exclude_patterns else ""))
        for i, pattern in enumerate(exclude_patterns):
            suffix = " \\" if i < len(exclude_patterns) - 1 else ""
            lignes.append(f"  --exclude '{pattern}'{suffix}")

        retention_flags = _retention_flags(config, tool)
        if retention_flags:
            lignes += [
                "",
                "borg prune \\",
                *[f"  {flag} \\" for flag in retention_flags],
                '  "${BORG_REPO}"',
            ]

    lignes.append(_notify_block(config, success=True).rstrip("\n"))
    lignes += [
        "",
        'echo "Sauvegarde terminee : $(date -Iseconds)"',
    ]

    return "\n".join(l for l in lignes if l is not None) + "\n"


# --------------------------------------------------------------------------
# restore.sh
# --------------------------------------------------------------------------
def generate_restore_script(config):
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    tool = _clean(config["tool"])
    app_name = _clean(config.get("app_name")) or "opsforge-backup"
    repo_url = _repo_url(config)
    passphrase_var = _clean(config.get("passphrase_env_var")) or "BACKUP_PASSPHRASE"

    lignes = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        f"# OpsForge - restauration ({app_name}, {tool})",
        "# Usage : ./restore.sh [identifiant_snapshot] [dossier_de_destination]",
        "",
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        'ENV_FILE="${SCRIPT_DIR}/backup.env"',
        'if [ -f "${ENV_FILE}" ]; then',
        "  set -a",
        '  source "${ENV_FILE}"',
        "  set +a",
        "fi",
        "",
        f'DEST="${{2:-/tmp/restore-{app_name}}}"',
        'mkdir -p "${DEST}"',
        "",
    ]

    if tool == "restic":
        lignes += [
            f'export RESTIC_REPOSITORY="{repo_url}"',
            f'export RESTIC_PASSWORD="${{{passphrase_var}:?variable {passphrase_var} manquante dans backup.env}}"',
            "",
            'SNAPSHOT="${1:-latest}"',
            "",
            "# Liste les snapshots disponibles si aucun identifiant n'est passe",
            'if [ "${SNAPSHOT}" = "latest" ]; then',
            '  echo "Snapshots disponibles :"',
            "  restic snapshots",
            "fi",
            "",
            'restic restore "${SNAPSHOT}" --target "${DEST}"',
        ]
    else:  # borg
        lignes += [
            f'export BORG_REPO="{repo_url}"',
            f'export BORG_PASSPHRASE="${{{passphrase_var}:?variable {passphrase_var} manquante dans backup.env}}"',
            "",
            'ARCHIVE="${1:-}"',
            'if [ -z "${ARCHIVE}" ]; then',
            "  echo \"Archives disponibles :\"",
            '  borg list "${BORG_REPO}"',
            '  ARCHIVE="$(borg list "${BORG_REPO}" --last 1 --short)"',
            '  echo "Aucun identifiant fourni : utilisation de la derniere archive : ${ARCHIVE}"',
            "fi",
            "",
            '(cd "${DEST}" && borg extract "${BORG_REPO}::${ARCHIVE}")',
        ]

    lignes += [
        "",
        'echo "Restauration terminee dans ${DEST}"',
    ]

    return "\n".join(lignes) + "\n"


# --------------------------------------------------------------------------
# Planification : systemd (service + timer) ou cron
# --------------------------------------------------------------------------
def generate_systemd_units(config):
    app_name = _clean(config.get("app_name")) or "opsforge-backup"
    oncalendar = _clean(config.get("schedule_oncalendar")) or "*-*-* 03:00:00"
    install_dir = _clean(config.get("install_dir")) or f"/opt/{app_name}"

    service = "\n".join([
        "[Unit]",
        f"Description=OpsForge - sauvegarde {app_name}",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        "Type=oneshot",
        f"ExecStart={install_dir}/backup.sh",
        "Nice=10",
        "IOSchedulingClass=best-effort",
        "IOSchedulingPriority=7",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
    ]) + "\n"

    timer = "\n".join([
        "[Unit]",
        f"Description=OpsForge - planification de la sauvegarde {app_name}",
        "",
        "[Timer]",
        f"OnCalendar={oncalendar}",
        "Persistent=true",
        "RandomizedDelaySec=300",
        "",
        "[Install]",
        "WantedBy=timers.target",
    ]) + "\n"

    return {
        f"{app_name}-backup.service": service,
        f"{app_name}-backup.timer": timer,
    }


def generate_cron_entry(config):
    app_name = _clean(config.get("app_name")) or "opsforge-backup"
    cron_expr = _clean(config.get("schedule_cron")) or "0 3 * * *"
    install_dir = _clean(config.get("install_dir")) or f"/opt/{app_name}"

    return (
        f"# OpsForge - sauvegarde automatique ({app_name})\n"
        f"# A ajouter via `crontab -e` (utilisateur root ou proprietaire des donnees) :\n"
        f"{cron_expr} {install_dir}/backup.sh >> /var/log/{app_name}-backup.log 2>&1\n"
    )


# --------------------------------------------------------------------------
# backup.env.example
# --------------------------------------------------------------------------
def generate_env_template(config):
    passphrase_var = _clean(config.get("passphrase_env_var")) or "BACKUP_PASSPHRASE"
    backend = _clean(config.get("repo_backend")) or "local"
    tool = _clean(config["tool"])

    lignes = [
        "# Copie ce fichier en 'backup.env' (meme dossier que backup.sh) et",
        "# renseigne les vraies valeurs. NE JAMAIS committer backup.env dans Git",
        "# (ajoute-le a .gitignore).",
        "",
        f"{passphrase_var}=change-moi-avec-une-phrase-de-passe-forte",
    ]

    if backend == "sftp":
        lignes += [
            "",
            "# Backend SFTP : l'authentification passe par une cle SSH",
            f"# (deploiee sur {'restic' if tool == 'restic' else 'Borg'}), pas par mot de passe ici.",
            "# Assure-toi que la cle SSH de cet hote est deja autorisee sur le serveur distant.",
        ]

    if backend == "s3":
        lignes += [
            "",
            "# Backend S3 (restic)",
            "AWS_ACCESS_KEY_ID=change-moi",
            "AWS_SECRET_ACCESS_KEY=change-moi",
        ]

    if config.get("notify_webhook_url"):
        lignes += [
            "",
            "# Notification (deja renseignee dans la config, rappel ici pour reference)",
            f"NOTIFY_WEBHOOK_URL={config['notify_webhook_url']}",
        ]

    return "\n".join(lignes) + "\n"


# --------------------------------------------------------------------------
# API publique
# --------------------------------------------------------------------------
def generate_files(config):
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    fichiers = {
        "backup.sh": generate_backup_script(config),
        "restore.sh": generate_restore_script(config),
        "backup.env.example": generate_env_template(config),
    }

    scheduler = _clean(config.get("scheduler")) or "systemd"
    if scheduler == "systemd":
        fichiers.update(generate_systemd_units(config))
    else:
        fichiers["crontab-entry.txt"] = generate_cron_entry(config)

    return fichiers


def write_files(config, output_dir):
    fichiers = generate_files(config)
    chemins = []
    os.makedirs(output_dir, exist_ok=True)
    for nom, contenu in fichiers.items():
        path = os.path.join(output_dir, nom)
        with open(path, "w", encoding="utf-8") as f:
            f.write(contenu)
        if nom.endswith(".sh"):
            os.chmod(path, 0o755)
        chemins.append(path)
    return chemins


def list_tools():
    return list(TOOLS)


def list_backends():
    return list(BACKENDS)


def list_schedulers():
    return list(SCHEDULERS)


# --------------------------------------------------------------------------
# Presets prets a l'emploi
# --------------------------------------------------------------------------
PRESETS = {
    "restic-local-systemd": {
        "tool": "restic",
        "app_name": "app-data",
        "repo_backend": "local",
        "repo_path": "/mnt/backup-drive/restic-repo",
        "source_paths": ["/var/www/app", "/etc/app"],
        "exclude_patterns": ["*.log", "*/node_modules/*", "*/.cache/*"],
        "passphrase_env_var": "BACKUP_PASSPHRASE",
        "retention": {"keep_daily": 7, "keep_weekly": 4, "keep_monthly": 6, "keep_yearly": 0},
        "scheduler": "systemd",
        "schedule_oncalendar": "*-*-* 03:00:00",
    },
    "restic-sftp-cron": {
        "tool": "restic",
        "app_name": "app-data",
        "repo_backend": "sftp",
        "sftp_host": "backup.example.com",
        "sftp_user": "backup",
        "repo_path": "/backups/app-data",
        "source_paths": ["/var/www/app", "/etc/app"],
        "exclude_patterns": ["*.log"],
        "passphrase_env_var": "BACKUP_PASSPHRASE",
        "retention": {"keep_daily": 7, "keep_weekly": 4, "keep_monthly": 6, "keep_yearly": 0},
        "scheduler": "cron",
        "schedule_cron": "0 3 * * *",
    },
    "restic-s3-systemd": {
        "tool": "restic",
        "app_name": "app-data",
        "repo_backend": "s3",
        "s3_bucket": "mon-bucket-backups",
        "s3_endpoint": "s3.amazonaws.com",
        "repo_path": "app-data",
        "source_paths": ["/var/www/app", "/etc/app"],
        "exclude_patterns": ["*.log", "*/node_modules/*"],
        "passphrase_env_var": "BACKUP_PASSPHRASE",
        "retention": {"keep_daily": 14, "keep_weekly": 8, "keep_monthly": 12, "keep_yearly": 2},
        "scheduler": "systemd",
        "schedule_oncalendar": "*-*-* 02:30:00",
        "notify_webhook_url": "https://hc-ping.com/votre-uuid-healthchecks",
    },
    "borg-local-systemd": {
        "tool": "borg",
        "app_name": "app-data",
        "repo_backend": "local",
        "repo_path": "/mnt/backup-drive/borg-repo",
        "source_paths": ["/var/www/app", "/etc/app"],
        "exclude_patterns": ["*.log", "*/node_modules/*"],
        "passphrase_env_var": "BACKUP_PASSPHRASE",
        "retention": {"keep_daily": 7, "keep_weekly": 4, "keep_monthly": 6, "keep_yearly": 0},
        "scheduler": "systemd",
        "schedule_oncalendar": "*-*-* 03:00:00",
    },
    "borg-sftp-cron": {
        "tool": "borg",
        "app_name": "app-data",
        "repo_backend": "sftp",
        "sftp_host": "backup.example.com",
        "sftp_user": "backup",
        "repo_path": "/backups/app-data",
        "source_paths": ["/var/www/app", "/etc/app"],
        "exclude_patterns": ["*.log"],
        "passphrase_env_var": "BACKUP_PASSPHRASE",
        "retention": {"keep_daily": 7, "keep_weekly": 4, "keep_monthly": 6, "keep_yearly": 0},
        "scheduler": "cron",
        "schedule_cron": "0 3 * * *",
    },
}


def list_presets():
    return list(PRESETS.keys())


def get_preset(name):
    if name not in PRESETS:
        raise ValueError(f"Preset inconnu : '{name}'. Presets disponibles : {', '.join(PRESETS.keys())}.")
    return copy.deepcopy(PRESETS[name])
