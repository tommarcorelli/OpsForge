"""
core.py
-------
Generation d'unites systemd (.service et .timer) a partir d'une config JSON.
Prolonge naturellement le module Ansible : ce qu'on deploie, systemd le
supervise (redemarrage auto, durcissement, taches planifiees).

Deux modes :

  - "service" : une unite <name>.service (long-running ou oneshot), avec
                type, utilisateur, environnement, politique de redemarrage
                et options de durcissement (sandboxing).
  - "timer"   : une unite <name>.service (oneshot) + une unite <name>.timer
                qui la declenche (remplacant moderne de cron), avec
                OnCalendar et rattrapage des executions manquees (Persistent).

Usage basique :
    from modules.systemd.core import generate_units

    config = {
        "mode": "service",
        "name": "myapp",
        "exec_start": "/opt/myapp/venv/bin/gunicorn app:app",
        "restart": "on-failure",
    }
    units = generate_units(config)   # {"myapp.service": "...texte..."}
"""

import copy
import os
import re

SUPPORTED_MODES = ["service", "timer"]
SERVICE_TYPES = ["simple", "exec", "forking", "oneshot", "notify"]
RESTART_POLICIES = ["no", "on-failure", "on-abnormal", "always"]

DEFAULT_SERVICE_TYPE = "simple"
DEFAULT_RESTART = "on-failure"
DEFAULT_RESTART_SEC = 5
DEFAULT_WANTED_BY = "multi-user.target"

# Nom d'unite systemd : lettres, chiffres, et - _ . @ (pas d'espace).
_NAME_RE = re.compile(r"^[A-Za-z0-9_.@-]+$")


def _clean(value):
    return (value or "").strip() if isinstance(value, str) else value


def validate_config(config):
    """
    Verifie la coherence d'une config avant generation.
    Retourne une liste d'erreurs (vide si tout est valide).
    """
    errors = []
    mode = config.get("mode")

    if mode not in SUPPORTED_MODES:
        errors.append(
            f"Mode non supporte : '{mode}'. Modes disponibles : {', '.join(SUPPORTED_MODES)}."
        )
        return errors  # le reste depend du mode, inutile d'aller plus loin

    name = _clean(config.get("name"))
    if not name:
        errors.append("Le nom de l'unite (name) est requis.")
    elif not _NAME_RE.match(name):
        errors.append(
            f"Nom d'unite invalide : '{name}'. "
            "Caracteres autorises : lettres, chiffres, - _ . @ (sans espace)."
        )

    if not _clean(config.get("exec_start")):
        errors.append("La commande a executer (exec_start / ExecStart) est requise.")

    service_type = config.get("service_type", DEFAULT_SERVICE_TYPE)
    if service_type not in SERVICE_TYPES:
        errors.append(
            f"Type de service invalide : '{service_type}'. "
            f"Disponibles : {', '.join(SERVICE_TYPES)}."
        )

    restart = config.get("restart", DEFAULT_RESTART)
    if restart not in RESTART_POLICIES:
        errors.append(
            f"Politique de redemarrage invalide : '{restart}'. "
            f"Disponibles : {', '.join(RESTART_POLICIES)}."
        )

    restart_sec = config.get("restart_sec", DEFAULT_RESTART_SEC)
    if not isinstance(restart_sec, int) or restart_sec < 0:
        errors.append(f"RestartSec invalide : '{restart_sec}' (attendu : entier >= 0).")

    if mode == "timer":
        has_schedule = any(
            _clean(config.get(key))
            for key in ("on_calendar", "on_boot_sec", "on_unit_active_sec")
        )
        if not has_schedule:
            errors.append(
                "Le mode 'timer' requiert au moins une planification "
                "(on_calendar, on_boot_sec ou on_unit_active_sec)."
            )

    return errors


# --------------------------------------------------------------------------
# Rendu INI (format des unites systemd)
# --------------------------------------------------------------------------
def _render_section(title, entries):
    """entries : liste de (cle, valeur). Les cles peuvent se repeter."""
    lines = [f"[{title}]"]
    for key, value in entries:
        lines.append(f"{key}={value}")
    return "\n".join(lines)


def _render_unit(sections, header=""):
    """sections : liste de (titre, entries). Les sections vides sont omises."""
    blocks = [_render_section(title, entries) for title, entries in sections if entries]
    body = "\n\n".join(blocks) + "\n"
    return (header + "\n" + body) if header else body


def _normalize_env(raw):
    """Accepte une liste de 'CLE=valeur' ou de {'key':.., 'value':..}."""
    result = []
    for item in raw or []:
        if isinstance(item, dict):
            key = _clean(item.get("key"))
            value = item.get("value", "")
            if key:
                result.append((key, value))
        else:
            text = _clean(item)
            if text and "=" in text:
                key, value = text.split("=", 1)
                result.append((key.strip(), value.strip()))
    return result


def _hardening_entries(config):
    """Directives de sandboxing (durcissement) optionnelles."""
    entries = []
    if config.get("no_new_privileges"):
        entries.append(("NoNewPrivileges", "true"))
    if config.get("private_tmp"):
        entries.append(("PrivateTmp", "true"))
    if config.get("protect_system"):
        entries.append(("ProtectSystem", "strict"))
    if config.get("protect_home"):
        entries.append(("ProtectHome", "true"))
    return entries


def _build_service(config):
    mode = config["mode"]
    name = _clean(config["name"])
    service_type = config.get("service_type", DEFAULT_SERVICE_TYPE)

    # [Unit]
    unit = [("Description", _clean(config.get("description")) or name)]
    after = _clean(config.get("after"))
    if not after and mode == "service":
        after = "network.target"
    if after:
        unit.append(("After", after))
    if _clean(config.get("requires")):
        unit.append(("Requires", _clean(config.get("requires"))))
    if _clean(config.get("wants")):
        unit.append(("Wants", _clean(config.get("wants"))))

    # [Service]
    service = [("Type", service_type)]
    if _clean(config.get("user")):
        service.append(("User", _clean(config.get("user"))))
    if _clean(config.get("group")):
        service.append(("Group", _clean(config.get("group"))))
    if _clean(config.get("working_directory")):
        service.append(("WorkingDirectory", _clean(config.get("working_directory"))))
    if _clean(config.get("environment_file")):
        service.append(("EnvironmentFile", _clean(config.get("environment_file"))))
    for key, value in _normalize_env(config.get("environment")):
        service.append(("Environment", f'"{key}={value}"'))

    if _clean(config.get("exec_start_pre")):
        service.append(("ExecStartPre", _clean(config.get("exec_start_pre"))))
    service.append(("ExecStart", _clean(config["exec_start"])))
    if _clean(config.get("exec_start_post")):
        service.append(("ExecStartPost", _clean(config.get("exec_start_post"))))
    if _clean(config.get("exec_reload")):
        service.append(("ExecReload", _clean(config.get("exec_reload"))))
    if _clean(config.get("exec_stop")):
        service.append(("ExecStop", _clean(config.get("exec_stop"))))

    # Restart n'a pas de sens pour un oneshot (le process n'est pas long-running).
    restart = config.get("restart", DEFAULT_RESTART)
    if service_type != "oneshot" and restart != "no":
        service.append(("Restart", restart))
        restart_sec = config.get("restart_sec", DEFAULT_RESTART_SEC)
        service.append(("RestartSec", str(restart_sec)))

    service.extend(_hardening_entries(config))

    # [Install] : en mode timer, c'est le .timer qui active le service.
    install = []
    if mode == "service":
        install.append(("WantedBy", _clean(config.get("wanted_by")) or DEFAULT_WANTED_BY))

    header = (
        f"# Genere par OpsForge — module systemd ({name}.service)\n"
        f"# Installer : sudo cp {name}.service /etc/systemd/system/\n"
        f"#   sudo systemctl daemon-reload && sudo systemctl enable --now {name}.service\n"
        f"#   Verifier : systemctl status {name}.service"
    )

    return _render_unit(
        [("Unit", unit), ("Service", service), ("Install", install)],
        header=header,
    )


def _build_timer(config):
    name = _clean(config["name"])

    unit = [("Description", f"Timer — {_clean(config.get('description')) or name}")]

    timer = []
    if _clean(config.get("on_calendar")):
        timer.append(("OnCalendar", _clean(config.get("on_calendar"))))
    if _clean(config.get("on_boot_sec")):
        timer.append(("OnBootSec", _clean(config.get("on_boot_sec"))))
    if _clean(config.get("on_unit_active_sec")):
        timer.append(("OnUnitActiveSec", _clean(config.get("on_unit_active_sec"))))
    if config.get("persistent"):
        timer.append(("Persistent", "true"))
    timer.append(("Unit", f"{name}.service"))

    install = [("WantedBy", "timers.target")]

    header = (
        f"# Genere par OpsForge — module systemd ({name}.timer)\n"
        f"# Installer les deux fichiers dans /etc/systemd/system/ puis :\n"
        f"#   sudo systemctl daemon-reload && sudo systemctl enable --now {name}.timer\n"
        f"#   Verifier : systemctl list-timers {name}.timer"
    )

    return _render_unit(
        [("Unit", unit), ("Timer", timer), ("Install", install)],
        header=header,
    )


def generate_units(config):
    """
    Genere la ou les unites systemd pour la config fournie.

    Args:
        config (dict): voir validate_config() pour les cles attendues.

    Returns:
        dict: {nom_de_fichier: contenu}. En mode 'service' une seule entree
              (<name>.service) ; en mode 'timer' deux (<name>.service +
              <name>.timer).

    Raises:
        ValueError: si la config est invalide (voir validate_config()).
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    name = _clean(config["name"])
    # En mode timer, le service declenche est par nature un oneshot.
    if config["mode"] == "timer" and not config.get("service_type"):
        config = {**config, "service_type": "oneshot"}

    units = {f"{name}.service": _build_service(config)}
    if config["mode"] == "timer":
        units[f"{name}.timer"] = _build_timer(config)
    return units


def generate_combined(config):
    """Concatene toutes les unites en un seul texte (pour affichage/copie)."""
    units = generate_units(config)
    return "\n".join(units.values())


def write_units(config, output_dir):
    """Genere les unites et les ecrit dans output_dir. Retourne les chemins."""
    units = generate_units(config)
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for filename, content in units.items():
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        paths.append(path)
    return paths


# --------------------------------------------------------------------------
# Presets prets a l'emploi
# --------------------------------------------------------------------------
PRESETS = {
    "web-app": {
        "mode": "service",
        "name": "myapp",
        "description": "Application web (gunicorn)",
        "exec_start": "/opt/myapp/venv/bin/gunicorn -b 127.0.0.1:8000 app:app",
        "service_type": "simple",
        "user": "myapp",
        "group": "myapp",
        "working_directory": "/opt/myapp",
        "environment_file": "/etc/myapp/env",
        "restart": "on-failure",
        "restart_sec": 5,
        "after": "network.target",
        "no_new_privileges": True,
        "private_tmp": True,
        "protect_system": True,
        "protect_home": True,
        "wanted_by": "multi-user.target",
    },
    "background-worker": {
        "mode": "service",
        "name": "worker",
        "description": "Worker de traitement asynchrone",
        "exec_start": "/opt/worker/venv/bin/python worker.py",
        "service_type": "simple",
        "user": "worker",
        "working_directory": "/opt/worker",
        "restart": "always",
        "restart_sec": 3,
        "after": "network.target",
        "private_tmp": True,
    },
    "forking-daemon": {
        "mode": "service",
        "name": "mydaemon",
        "description": "Daemon classique (fork)",
        "exec_start": "/usr/local/bin/mydaemon --daemonize",
        "service_type": "forking",
        "restart": "on-failure",
        "after": "network.target",
    },
    "daily-backup": {
        "mode": "timer",
        "name": "backup",
        "description": "Sauvegarde quotidienne",
        "exec_start": "/usr/local/bin/backup.sh",
        "service_type": "oneshot",
        "user": "root",
        "on_calendar": "*-*-* 02:00:00",
        "persistent": True,
        "private_tmp": True,
    },
    "weekly-maintenance": {
        "mode": "timer",
        "name": "maintenance",
        "description": "Maintenance hebdomadaire",
        "exec_start": "/usr/local/bin/maintenance.sh",
        "service_type": "oneshot",
        "on_calendar": "Mon *-*-* 03:30:00",
        "persistent": True,
    },
}


def list_presets():
    return list(PRESETS.keys())


def get_preset(name):
    if name not in PRESETS:
        raise ValueError(
            f"Preset inconnu : '{name}'. Presets disponibles : {', '.join(PRESETS.keys())}."
        )
    return copy.deepcopy(PRESETS[name])
