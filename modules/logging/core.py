"""
core.py
-------
Generation de configs de collecte/expedition de logs (Fluent Bit ou Vector)
a partir d'une config JSON. Complete le module `monitoring` (metriques) :
monitoring couvre les chiffres, logging couvre le texte — les deux moities
classiques de l'observabilite, jusqu'ici absentes cote logs dans OpsForge.

Deux backends :

  - "fluent-bit" : agent leger en C, tres repandu (config .conf de type INI).
  - "vector"     : agent moderne en Rust (config .toml), pipelines plus
                   flexibles, souvent prefere pour des transformations riches.

Chaque config est definie par :
  - une liste de SOURCES (d'ou viennent les logs) : fichier (tail),
    conteneurs Docker, ou syslog reseau.
  - une DESTINATION (ou les logs partent) : Loki, Elasticsearch, stdout
    (debug local) ou fichier local.

Usage basique :
    from modules.logging.core import generate_logging

    config = {
        "preset": "docker-loki",
        "backend": "fluent-bit",
    }
    files = generate_logging(config)   # {"fluent-bit.conf": "..."}
"""

import copy
import re

SUPPORTED_BACKENDS = ["fluent-bit", "vector"]
SOURCE_TYPES = ["tail", "docker", "syslog"]
DESTINATION_TYPES = ["loki", "elasticsearch", "stdout", "file"]

_PORT_RE = re.compile(r"^\d{1,5}$")


# --------------------------------------------------------------------------
# Presets : chaque preset definit des sources et une destination pretes a
# l'emploi pour un scenario courant. "custom" part d'une liste vide.
# --------------------------------------------------------------------------
PRESETS = {
    "docker-loki": {
        "label": "Logs de tous les conteneurs Docker -> Loki",
        "sources": [
            {"type": "docker", "tag": "docker.*"},
        ],
        "destination": {
            "type": "loki", "host": "localhost", "port": 3100,
            "labels": {"job": "docker"},
        },
    },
    "nginx-loki": {
        "label": "Logs nginx (access + error) -> Loki",
        "sources": [
            {"type": "tail", "path": "/var/log/nginx/*.log", "tag": "nginx.*"},
        ],
        "destination": {
            "type": "loki", "host": "localhost", "port": 3100,
            "labels": {"job": "nginx"},
        },
    },
    "syslog-elasticsearch": {
        "label": "Syslog reseau (UDP) -> Elasticsearch",
        "sources": [
            {"type": "syslog", "port": 5140, "tag": "syslog"},
        ],
        "destination": {
            "type": "elasticsearch", "host": "localhost", "port": 9200,
            "index": "syslog",
        },
    },
    "app-json-loki": {
        "label": "Logs applicatifs JSON -> Loki",
        "sources": [
            {"type": "tail", "path": "/var/log/myapp/*.json", "tag": "app", "parser": "json"},
        ],
        "destination": {
            "type": "loki", "host": "localhost", "port": 3100,
            "labels": {"job": "app"},
        },
    },
    "custom": {
        "label": "Personnalise (sources/destination fournies manuellement)",
        "sources": [],
        "destination": None,
    },
}


def list_presets():
    """Liste les noms de presets disponibles (dans un ordre stable)."""
    return list(PRESETS.keys())


def get_preset(name):
    """
    Retourne une config de depart prete a generer pour le preset donne
    (copie profonde : modifiable sans affecter PRESETS).
    """
    if name not in PRESETS:
        raise ValueError(
            f"Preset inconnu : '{name}'. Disponibles : {', '.join(PRESETS)}."
        )
    preset_def = PRESETS[name]
    return {
        "preset": name,
        "backend": "fluent-bit",
        "sources": copy.deepcopy(preset_def["sources"]),
        "destination": copy.deepcopy(preset_def["destination"]),
    }


def _resolve(config):
    preset = config.get("preset", "custom")
    if preset not in PRESETS:
        preset = "custom"
    if preset == "custom":
        return config.get("sources", []), config.get("destination")
    preset_def = PRESETS[preset]
    return preset_def["sources"], preset_def["destination"]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate_config(config):
    """
    Verifie la coherence d'une config avant generation.
    Retourne une liste d'erreurs (vide si tout est valide).
    """
    errors = []

    preset = config.get("preset", "custom")
    if preset not in PRESETS:
        errors.append(
            f"Preset non supporte : '{preset}'. Disponibles : {', '.join(PRESETS)}."
        )
        preset = "custom"

    backend = config.get("backend", "fluent-bit")
    if backend not in SUPPORTED_BACKENDS:
        errors.append(
            f"Backend non supporte : '{backend}'. Disponibles : {', '.join(SUPPORTED_BACKENDS)}."
        )

    sources, destination = _resolve(config)

    if preset == "custom" and not sources:
        errors.append("Preset 'custom' choisi mais aucune source fournie (sources).")

    for i, src in enumerate(sources or []):
        stype = src.get("type")
        if stype not in SOURCE_TYPES:
            errors.append(f"Source #{i + 1} : type invalide ({stype!r}), attendu {'/'.join(SOURCE_TYPES)}.")
            continue
        if stype == "tail" and not src.get("path"):
            errors.append(f"Source #{i + 1} (tail) : champ 'path' manquant.")
        if stype == "syslog":
            port = src.get("port")
            if not port or not _PORT_RE.match(str(port)) or not (0 < int(port) <= 65535):
                errors.append(f"Source #{i + 1} (syslog) : port invalide ({port!r}).")
        if not src.get("tag"):
            errors.append(f"Source #{i + 1} : champ 'tag' manquant (identifie le flux dans les logs).")

    if preset == "custom" and not destination:
        errors.append("Preset 'custom' choisi mais aucune destination fournie.")
    elif destination:
        dtype = destination.get("type")
        if dtype not in DESTINATION_TYPES:
            errors.append(f"Destination : type invalide ({dtype!r}), attendu {'/'.join(DESTINATION_TYPES)}.")
        if dtype in ("loki", "elasticsearch"):
            port = destination.get("port")
            if not port or not _PORT_RE.match(str(port)) or not (0 < int(port) <= 65535):
                errors.append(f"Destination ({dtype}) : port invalide ({port!r}).")
            if not destination.get("host"):
                errors.append(f"Destination ({dtype}) : champ 'host' manquant.")
        if dtype == "elasticsearch" and not destination.get("index"):
            errors.append("Destination (elasticsearch) : champ 'index' manquant.")
        if dtype == "file" and not destination.get("path"):
            errors.append("Destination (file) : champ 'path' manquant.")

    return errors


# --------------------------------------------------------------------------
# Backend fluent-bit : fichier .conf (format INI-like propre a Fluent Bit).
# --------------------------------------------------------------------------
def _fluentbit_input_block(src):
    stype = src["type"]
    tag = src.get("tag", "*")

    if stype == "tail":
        lines = [
            "[INPUT]",
            "    Name   tail",
            f"    Path   {src['path']}",
            f"    Tag    {tag}",
        ]
        if src.get("parser") == "json":
            lines.append("    Parser json")
        return "\n".join(lines)

    if stype == "docker":
        return "\n".join([
            "[INPUT]",
            "    Name   tail",
            "    Path   /var/lib/docker/containers/*/*.log",
            f"    Tag    {tag}",
            "    Parser docker",
        ])

    if stype == "syslog":
        return "\n".join([
            "[INPUT]",
            "    Name   syslog",
            "    Mode   udp",
            "    Listen 0.0.0.0",
            f"    Port   {src['port']}",
            f"    Tag    {tag}",
        ])

    raise ValueError(f"Type de source inconnu : {stype!r}")


def _fluentbit_output_block(dest, match="*"):
    dtype = dest["type"]

    if dtype == "loki":
        lines = [
            "[OUTPUT]",
            "    Name   loki",
            f"    Match  {match}",
            f"    Host   {dest['host']}",
            f"    Port   {dest['port']}",
        ]
        for key, value in (dest.get("labels") or {}).items():
            lines.append(f"    Labels {key}={value}")
        return "\n".join(lines)

    if dtype == "elasticsearch":
        return "\n".join([
            "[OUTPUT]",
            "    Name   es",
            f"    Match  {match}",
            f"    Host   {dest['host']}",
            f"    Port   {dest['port']}",
            f"    Index  {dest['index']}",
        ])

    if dtype == "stdout":
        return "\n".join(["[OUTPUT]", "    Name   stdout", f"    Match  {match}"])

    if dtype == "file":
        return "\n".join([
            "[OUTPUT]",
            "    Name   file",
            f"    Match  {match}",
            f"    Path   {dest['path']}",
        ])

    raise ValueError(f"Type de destination inconnu : {dtype!r}")


def generate_fluentbit(config):
    sources, destination = _resolve(config)

    lines = [
        "# Genere par OpsForge (module logging).",
        "",
        "[SERVICE]",
        "    Flush        5",
        "    Daemon       off",
        "    Log_Level    info",
        "",
    ]

    for src in sources:
        lines.append(_fluentbit_input_block(src))
        lines.append("")

    lines.append(_fluentbit_output_block(destination))
    lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Backend vector : fichier .toml (sources / sinks, pipeline explicite).
# --------------------------------------------------------------------------
def _toml_string(value):
    return '"' + str(value).replace('"', '\\"') + '"'


def _vector_source_block(name, src):
    stype = src["type"]

    if stype == "tail":
        lines = [
            f"[sources.{name}]",
            'type = "file"',
            f"include = [{_toml_string(src['path'])}]",
        ]
        return "\n".join(lines)

    if stype == "docker":
        return "\n".join([f"[sources.{name}]", 'type = "docker_logs"'])

    if stype == "syslog":
        return "\n".join([
            f"[sources.{name}]",
            'type = "syslog"',
            'mode = "udp"',
            f"address = \"0.0.0.0:{src['port']}\"",
        ])

    raise ValueError(f"Type de source inconnu : {stype!r}")


def _vector_sink_block(name, dest, input_names):
    dtype = dest["type"]
    inputs_toml = "[" + ", ".join(_toml_string(n) for n in input_names) + "]"

    if dtype == "loki":
        lines = [
            f"[sinks.{name}]",
            'type = "loki"',
            f"inputs = {inputs_toml}",
            f"endpoint = \"http://{dest['host']}:{dest['port']}\"",
            "encoding.codec = \"json\"",
        ]
        for key, value in (dest.get("labels") or {}).items():
            lines.append(f'labels.{key} = {_toml_string(value)}')
        return "\n".join(lines)

    if dtype == "elasticsearch":
        return "\n".join([
            f"[sinks.{name}]",
            'type = "elasticsearch"',
            f"inputs = {inputs_toml}",
            f"endpoint = \"http://{dest['host']}:{dest['port']}\"",
            f"bulk.index = {_toml_string(dest['index'])}",
        ])

    if dtype == "stdout":
        return "\n".join([f"[sinks.{name}]", 'type = "console"', f"inputs = {inputs_toml}", 'encoding.codec = "json"'])

    if dtype == "file":
        return "\n".join([
            f"[sinks.{name}]",
            'type = "file"',
            f"inputs = {inputs_toml}",
            f"path = {_toml_string(dest['path'])}",
            'encoding.codec = "json"',
        ])

    raise ValueError(f"Type de destination inconnu : {dtype!r}")


def generate_vector(config):
    sources, destination = _resolve(config)

    lines = ["# Genere par OpsForge (module logging).", ""]

    names = []
    for i, src in enumerate(sources):
        name = src.get("tag", f"source_{i}").replace(".", "_").replace("*", "all")
        names.append(name)
        lines.append(_vector_source_block(name, src))
        lines.append("")

    lines.append(_vector_sink_block("out", destination, names))
    lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Point d'entree principal.
# --------------------------------------------------------------------------
def generate_logging(config):
    """
    Genere le fichier de config de logging a partir d'une config validee.
    Retourne {nom_fichier: contenu texte}.
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))

    config = copy.deepcopy(config)
    backend = config.get("backend", "fluent-bit")

    if backend == "fluent-bit":
        return {"fluent-bit.conf": generate_fluentbit(config)}
    return {"vector.toml": generate_vector(config)}


def write_logging(config, output_dir):
    """Ecrit le fichier genere dans output_dir. Retourne la liste des chemins ecrits."""
    import os

    files = generate_logging(config)
    os.makedirs(output_dir, exist_ok=True)

    written = []
    for filename, content in files.items():
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(path)

    return written
