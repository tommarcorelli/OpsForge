"""
core.py
-------
Generation de configuration de monitoring a partir d'une config JSON.
Complete la suite : ce que Vagrant/Terraform provisionne et que systemd
supervise, ce module l'observe.

Trois modes :

  - "prometheus" : fichier `prometheus.yml` (global scrape/eval interval,
                   scrape_configs multi-jobs, wiring Alertmanager + rule_files
                   en option).
  - "alerts"     : fichier de regles d'alerte Prometheus (`alert.rules.yml`)
                   a partir d'un catalogue (instance down, CPU/mem/disk, charge)
                   avec seuils configurables.
  - "grafana"    : fichier de provisioning de datasources Grafana
                   (`datasource.yml`) : Prometheus, Loki, InfluxDB...

Le YAML est produit via PyYAML (garanti valide), puis chaque fichier est
prefixe d'un pense-bete d'installation en commentaire.

Usage basique :
    from modules.monitoring.core import generate_files

    config = {
        "mode": "prometheus",
        "jobs": [{"job_name": "node", "targets": ["localhost:9100"]}],
    }
    files = generate_files(config)   # {"prometheus.yml": "...texte..."}
"""

import copy
import os
import re

import yaml

SUPPORTED_MODES = ["prometheus", "alerts", "grafana"]
DATASOURCE_TYPES = ["prometheus", "loki", "influxdb", "postgres", "tempo", "elasticsearch"]

DEFAULT_INTERVAL = "15s"
DEFAULT_CPU_THRESHOLD = 85
DEFAULT_MEMORY_THRESHOLD = 85
DEFAULT_DISK_THRESHOLD = 85

# Durees Prometheus : 30s, 5m, 1h, 2d, 1w, 1y... (et ms).
_DURATION_RE = re.compile(r"^\d+(ms|[smhdwy])$")
# Cible scrape : hote:port (hote = nom/ip, tolerant).
_TARGET_RE = re.compile(r"^[A-Za-z0-9_.\-]+:\d{1,5}$")

# Catalogue de regles d'alerte (base node_exporter). Les seuils sont injectes
# via des sentinelles <<cpu>>/<<mem>>/<<disk>> : on n'utilise PAS str.format,
# car les expressions PromQL contiennent des accolades ({mode="idle"}...).
RULES_CATALOG = {
    "instance_down": {
        "label": "Instance injoignable",
        "alert": "InstanceDown",
        "expr": "up == 0",
        "for": "5m",
        "severity": "critical",
        "summary": "Instance {{ $labels.instance }} injoignable",
        "description": "{{ $labels.instance }} (job {{ $labels.job }}) ne repond plus depuis 5 minutes.",
    },
    "high_cpu": {
        "label": "CPU eleve",
        "alert": "HighCpuUsage",
        "expr": '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > <<cpu>>',
        "for": "10m",
        "severity": "warning",
        "summary": "CPU eleve sur {{ $labels.instance }}",
        "description": "L'utilisation CPU depasse <<cpu>>% depuis 10 minutes.",
    },
    "high_memory": {
        "label": "Memoire elevee",
        "alert": "HighMemoryUsage",
        "expr": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > <<mem>>",
        "for": "10m",
        "severity": "warning",
        "summary": "Memoire elevee sur {{ $labels.instance }}",
        "description": "L'utilisation memoire depasse <<mem>>% depuis 10 minutes.",
    },
    "disk_full": {
        "label": "Disque presque plein",
        "alert": "DiskAlmostFull",
        "expr": '(1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / '
                'node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})) * 100 > <<disk>>',
        "for": "10m",
        "severity": "warning",
        "summary": "Disque presque plein sur {{ $labels.instance }}",
        "description": "L'espace disque utilise depasse <<disk>>% sur {{ $labels.mountpoint }}.",
    },
    "high_load": {
        "label": "Charge systeme elevee",
        "alert": "HighSystemLoad",
        "expr": 'node_load15 > count by(instance)(node_cpu_seconds_total{mode="idle"}) * 1.5',
        "for": "10m",
        "severity": "warning",
        "summary": "Charge systeme elevee sur {{ $labels.instance }}",
        "description": "La charge sur 15 min depasse 1.5x le nombre de coeurs depuis 10 minutes.",
    },
}


def _clean(value):
    return value.strip() if isinstance(value, str) else value


def _duration_ok(value):
    return bool(_DURATION_RE.match(str(value)))


def _dump_yaml(data):
    return yaml.dump(
        data,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=4096,
    )


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
        return errors

    if mode == "prometheus":
        for key in ("scrape_interval", "evaluation_interval", "scrape_timeout"):
            value = config.get(key)
            if value and not _duration_ok(value):
                errors.append(
                    f"Duree invalide pour {key} : '{value}' (ex. valides : 15s, 1m, 1h)."
                )
        jobs = config.get("jobs") or []
        if not jobs:
            errors.append("Au moins un job de scrape est requis.")
        for i, job in enumerate(jobs):
            if not _clean(job.get("job_name")):
                errors.append(f"Job #{i + 1} : le nom (job_name) est requis.")
            targets = job.get("targets") or []
            if not targets:
                errors.append(f"Job #{i + 1} : au moins une cible (target) est requise.")
            for target in targets:
                if not _TARGET_RE.match(str(target)):
                    errors.append(
                        f"Job #{i + 1} : cible invalide '{target}' (attendu : hote:port)."
                    )

    elif mode == "alerts":
        rules = config.get("rules") or []
        if not rules:
            errors.append("Selectionne au moins une regle d'alerte.")
        for key in rules:
            if key not in RULES_CATALOG:
                errors.append(f"Regle d'alerte inconnue : '{key}'.")
        for key in ("cpu_threshold", "memory_threshold", "disk_threshold"):
            value = config.get(key)
            if value is not None and (
                not isinstance(value, (int, float)) or isinstance(value, bool)
                or not (0 < value <= 100)
            ):
                errors.append(f"Seuil invalide pour {key} : '{value}' (attendu : 1-100).")

    elif mode == "grafana":
        datasources = config.get("datasources") or []
        if not datasources:
            errors.append("Au moins une datasource est requise.")
        for i, ds in enumerate(datasources):
            if not _clean(ds.get("name")):
                errors.append(f"Datasource #{i + 1} : le nom est requis.")
            if not _clean(ds.get("url")):
                errors.append(f"Datasource #{i + 1} : l'URL est requise.")
            ds_type = _clean(ds.get("type"))
            if ds_type and ds_type not in DATASOURCE_TYPES:
                errors.append(
                    f"Datasource #{i + 1} : type '{ds_type}' non reconnu "
                    f"(disponibles : {', '.join(DATASOURCE_TYPES)})."
                )

    return errors


# --------------------------------------------------------------------------
# Construction par mode
# --------------------------------------------------------------------------
def _build_prometheus(config):
    global_block = {
        "scrape_interval": config.get("scrape_interval") or DEFAULT_INTERVAL,
        "evaluation_interval": config.get("evaluation_interval") or DEFAULT_INTERVAL,
    }
    if _clean(config.get("scrape_timeout")):
        global_block["scrape_timeout"] = config["scrape_timeout"]

    data = {"global": global_block}

    if config.get("alertmanager"):
        targets = config.get("alertmanager_targets") or ["localhost:9093"]
        data["alerting"] = {
            "alertmanagers": [{"static_configs": [{"targets": list(targets)}]}]
        }

    if config.get("rule_files"):
        files = config.get("rule_files_list") or ["alert.rules.yml"]
        data["rule_files"] = list(files)

    scrape_configs = []
    for job in config["jobs"]:
        entry = {"job_name": _clean(job["job_name"])}
        if _clean(job.get("metrics_path")):
            entry["metrics_path"] = job["metrics_path"]
        if _clean(job.get("scheme")):
            entry["scheme"] = job["scheme"]
        if _clean(job.get("scrape_interval")):
            entry["scrape_interval"] = job["scrape_interval"]
        entry["static_configs"] = [{"targets": [str(t) for t in job["targets"]]}]
        scrape_configs.append(entry)
    data["scrape_configs"] = scrape_configs

    header = (
        "# Genere par OpsForge — module monitoring (prometheus.yml)\n"
        "# Placer dans /etc/prometheus/prometheus.yml puis recharger :\n"
        "#   sudo systemctl reload prometheus   (ou : curl -X POST http://localhost:9090/-/reload)\n"
        "#   Verifier la config : promtool check config prometheus.yml"
    )
    return header + "\n" + _dump_yaml(data)


def _apply_thresholds(text, thresholds):
    return (
        text.replace("<<cpu>>", str(thresholds["cpu"]))
        .replace("<<mem>>", str(thresholds["mem"]))
        .replace("<<disk>>", str(thresholds["disk"]))
    )


def _build_alerts(config):
    thresholds = {
        "cpu": config.get("cpu_threshold", DEFAULT_CPU_THRESHOLD),
        "mem": config.get("memory_threshold", DEFAULT_MEMORY_THRESHOLD),
        "disk": config.get("disk_threshold", DEFAULT_DISK_THRESHOLD),
    }

    rules = []
    for key in config["rules"]:
        spec = RULES_CATALOG[key]
        rules.append({
            "alert": spec["alert"],
            "expr": _apply_thresholds(spec["expr"], thresholds),
            "for": spec["for"],
            "labels": {"severity": spec["severity"]},
            "annotations": {
                "summary": spec["summary"],
                "description": _apply_thresholds(spec["description"], thresholds),
            },
        })

    data = {"groups": [{"name": _clean(config.get("group_name")) or "opsforge-alerts", "rules": rules}]}

    header = (
        "# Genere par OpsForge — module monitoring (alert.rules.yml)\n"
        "# A referencer dans prometheus.yml sous rule_files: puis recharger Prometheus.\n"
        "#   Verifier : promtool check rules alert.rules.yml"
    )
    return header + "\n" + _dump_yaml(data)


def _build_grafana(config):
    datasources = []
    for ds in config["datasources"]:
        entry = {
            "name": _clean(ds["name"]),
            "type": _clean(ds.get("type")) or "prometheus",
            "access": _clean(ds.get("access")) or "proxy",
            "url": _clean(ds["url"]),
        }
        if ds.get("is_default"):
            entry["isDefault"] = True
        entry["editable"] = True
        datasources.append(entry)

    data = {"apiVersion": 1, "datasources": datasources}

    header = (
        "# Genere par OpsForge — module monitoring (datasource.yml)\n"
        "# Placer dans /etc/grafana/provisioning/datasources/ puis redemarrer Grafana :\n"
        "#   sudo systemctl restart grafana-server"
    )
    return header + "\n" + _dump_yaml(data)


_BUILDERS = {
    "prometheus": _build_prometheus,
    "alerts": _build_alerts,
    "grafana": _build_grafana,
}

_FILENAMES = {
    "prometheus": "prometheus.yml",
    "alerts": "alert.rules.yml",
    "grafana": "datasource.yml",
}


def generate_files(config):
    """
    Genere le(s) fichier(s) de monitoring pour la config fournie.

    Args:
        config (dict): voir validate_config() pour les cles attendues par mode.

    Returns:
        dict: {nom_de_fichier: contenu}. Une entree par appel (le nom depend
              du mode : prometheus.yml / alert.rules.yml / datasource.yml).

    Raises:
        ValueError: si la config est invalide (voir validate_config()).
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    mode = config["mode"]
    return {_FILENAMES[mode]: _BUILDERS[mode](config)}


def generate_combined(config):
    """Concatene tous les fichiers en un seul texte (pour affichage/copie)."""
    return "\n".join(generate_files(config).values())


def write_files(config, output_dir):
    """Genere les fichiers et les ecrit dans output_dir. Retourne les chemins."""
    files = generate_files(config)
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for filename, content in files.items():
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        paths.append(path)
    return paths


def list_rules():
    """Catalogue des regles d'alerte, pour l'interface."""
    return [
        {"key": key, "label": spec["label"], "severity": spec["severity"]}
        for key, spec in RULES_CATALOG.items()
    ]


# --------------------------------------------------------------------------
# Presets prets a l'emploi
# --------------------------------------------------------------------------
PRESETS = {
    "prometheus-node": {
        "mode": "prometheus",
        "scrape_interval": "15s",
        "evaluation_interval": "15s",
        "alertmanager": True,
        "rule_files": True,
        "jobs": [
            {"job_name": "prometheus", "targets": ["localhost:9090"]},
            {"job_name": "node", "targets": ["localhost:9100"]},
        ],
    },
    "prometheus-docker": {
        "mode": "prometheus",
        "scrape_interval": "15s",
        "evaluation_interval": "15s",
        "jobs": [
            {"job_name": "prometheus", "targets": ["localhost:9090"]},
            {"job_name": "cadvisor", "targets": ["localhost:8080"]},
            {"job_name": "node", "targets": ["localhost:9100"]},
        ],
    },
    "alerts-basic": {
        "mode": "alerts",
        "group_name": "opsforge-basic",
        "rules": ["instance_down", "high_cpu", "high_memory", "disk_full"],
        "cpu_threshold": 85,
        "memory_threshold": 85,
        "disk_threshold": 85,
    },
    "grafana-prometheus": {
        "mode": "grafana",
        "datasources": [
            {"name": "Prometheus", "type": "prometheus", "url": "http://localhost:9090", "is_default": True},
        ],
    },
    "grafana-prom-loki": {
        "mode": "grafana",
        "datasources": [
            {"name": "Prometheus", "type": "prometheus", "url": "http://localhost:9090", "is_default": True},
            {"name": "Loki", "type": "loki", "url": "http://localhost:3100"},
        ],
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
