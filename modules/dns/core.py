"""
core.py
-------
Generation d'enregistrements DNS a partir d'une config JSON. Seul domaine
qui ne touchait aucun des modules existants : vault gere les secrets,
ssh l'acces, nginx le trafic HTTP, firewall le filtrage — rien ne produisait
un enregistrement A/CNAME/MX.

Les memes enregistrements peuvent etre rendus dans deux formats (le moteur
ne change pas le CONTENU, seulement la SERIALISATION — contrairement au
module ssh ou "role" change fondamentalement la forme de la config) :

  - "bind"    : fichier de zone maitre standard (RFC 1035), universel —
                BIND, PowerDNS, Knot, et la plupart des registrars qui
                acceptent un import/export de zone.
  - "route53" : lot de changements JSON pret pour
                `aws route53 change-resource-record-sets`.

Usage basique :
    from modules.dns.core import generate_dns

    config = {"preset": "site-statique", "engine": "bind"}
    files = generate_dns(config)   # {"exemple.com.zone": "..."}
"""

import copy
import ipaddress
import os
import re
from datetime import date

SUPPORTED_ENGINES = ["bind", "route53"]
RECORD_TYPES = ["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA"]
CAA_TAGS = ["issue", "issuewild", "iodef"]

DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$", re.I)
# Nom de record : "@" (apex), un label/sous-domaine, ou un nom compose de
# labels commencant par "_" (verification SRV/DKIM : _sip._tcp, _dmarc...),
# jokers "*" pour un wildcard.
NAME_RE = re.compile(r"^(@|\*|[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?(\.[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?)*)$", re.I)


def _fqdn(name, domain):
    """Nom pleinement qualifie (avec point final) pour un enregistrement."""
    if name == "@":
        return f"{domain}."
    return f"{name}.{domain}."


def _today_serial():
    """
    Numero de serie SOA au format standard YYYYMMDDnn. Genere a la date du
    jour : si la zone est regeneree plusieurs fois le meme jour, le "00"
    doit etre incremente a la main avant de publier (rappele en commentaire
    dans le fichier de zone) — les serveurs secondaires ne resynchronisent
    que si le serial a strictement augmente.
    """
    return f"{date.today().strftime('%Y%m%d')}00"


# --------------------------------------------------------------------------
# Presets : les enregistrements sont independants du moteur de sortie (les
# memes records se rendent en zone BIND ou en lot Route53). "engine" ne
# fixe que la valeur par defaut, modifiable independamment du preset.
# --------------------------------------------------------------------------
PRESETS = {
    "site-statique": {
        "label": "Site statique (apex + www)",
        "config": {
            "domain": "exemple.com",
            "ttl": 3600,
            "nameservers": ["ns1.exemple.com.", "ns2.exemple.com."],
            "soa": {
                "primary_ns": "ns1.exemple.com.",
                "admin_email": "admin.exemple.com.",
                "refresh": 3600, "retry": 900, "expire": 1209600, "minimum": 3600,
            },
            "records": [
                {"type": "A", "name": "@", "value": "203.0.113.10"},
                {"type": "CNAME", "name": "www", "value": "exemple.com."},
            ],
        },
    },
    "domaine-mail": {
        "label": "Domaine avec email (MX, SPF, DKIM, DMARC)",
        "config": {
            "domain": "exemple.com",
            "ttl": 3600,
            "nameservers": ["ns1.exemple.com.", "ns2.exemple.com."],
            "soa": {
                "primary_ns": "ns1.exemple.com.",
                "admin_email": "admin.exemple.com.",
                "refresh": 3600, "retry": 900, "expire": 1209600, "minimum": 3600,
            },
            "records": [
                {"type": "A", "name": "@", "value": "203.0.113.10"},
                {"type": "MX", "name": "@", "value": "mail.exemple.com.", "priority": 10},
                {"type": "TXT", "name": "@", "value": "v=spf1 mx ~all"},
                {"type": "TXT", "name": "_dmarc", "value": "v=DMARC1; p=quarantine; rua=mailto:dmarc@exemple.com"},
                {"type": "TXT", "name": "mail._domainkey", "value": "v=DKIM1; k=rsa; p=REMPLACE_PAR_TA_CLE_PUBLIQUE_DKIM"},
            ],
        },
    },
    "sous-domaines-services": {
        "label": "Services auto-heberges (plusieurs sous-domaines, un serveur)",
        "config": {
            "domain": "exemple.com",
            "ttl": 3600,
            "nameservers": ["ns1.exemple.com.", "ns2.exemple.com."],
            "soa": {
                "primary_ns": "ns1.exemple.com.",
                "admin_email": "admin.exemple.com.",
                "refresh": 3600, "retry": 900, "expire": 1209600, "minimum": 3600,
            },
            "records": [
                {"type": "A", "name": "@", "value": "203.0.113.10"},
                {"type": "CNAME", "name": "www", "value": "exemple.com."},
                {"type": "CNAME", "name": "auth", "value": "exemple.com."},
                {"type": "CNAME", "name": "git", "value": "exemple.com."},
                {"type": "CNAME", "name": "cloud", "value": "exemple.com."},
            ],
        },
    },
    "verification-domaine": {
        "label": "Vérification de propriété (TXT seul + apex)",
        "config": {
            "domain": "exemple.com",
            "ttl": 3600,
            "nameservers": ["ns1.exemple.com.", "ns2.exemple.com."],
            "soa": {
                "primary_ns": "ns1.exemple.com.",
                "admin_email": "admin.exemple.com.",
                "refresh": 3600, "retry": 900, "expire": 1209600, "minimum": 3600,
            },
            "records": [
                {"type": "A", "name": "@", "value": "203.0.113.10"},
                {"type": "TXT", "name": "@", "value": "REMPLACE_PAR_LE_JETON_DE_VERIFICATION"},
            ],
        },
    },
    "custom": {
        "label": "Personnalisé (enregistrements fournis manuellement)",
        "config": {
            "domain": "exemple.com",
            "ttl": 3600,
            "nameservers": ["ns1.exemple.com.", "ns2.exemple.com."],
            "soa": {
                "primary_ns": "ns1.exemple.com.",
                "admin_email": "admin.exemple.com.",
                "refresh": 3600, "retry": 900, "expire": 1209600, "minimum": 3600,
            },
            "records": [],
        },
    },
}

DEFAULT_ENGINE = "bind"


def list_presets():
    """Liste les noms de presets disponibles (dans un ordre stable)."""
    return list(PRESETS.keys())


def get_preset(name, engine=None):
    """
    Retourne une config de depart prete a generer pour le preset donne
    (copie profonde : modifiable sans affecter PRESETS).
    """
    if name not in PRESETS:
        raise ValueError(
            f"Preset inconnu : '{name}'. Disponibles : {', '.join(PRESETS)}."
        )
    config = copy.deepcopy(PRESETS[name]["config"])
    config["preset"] = name
    config["engine"] = engine or DEFAULT_ENGINE
    return config


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def _validate_record(record, index, errors):
    label = f"Enregistrement #{index}"

    rtype = record.get("type", "")
    if rtype not in RECORD_TYPES:
        errors.append(f"{label} : type non supporte ('{rtype}'). Disponibles : {', '.join(RECORD_TYPES)}.")
        return

    name = (record.get("name") or "").strip()
    if not name:
        errors.append(f"{label} : nom manquant ('@' pour la racine du domaine).")
    elif not NAME_RE.match(name):
        errors.append(f"{label} : nom invalide ('{name}').")

    value = (record.get("value") or "").strip()
    if not value:
        errors.append(f"{label} ({rtype} {name}) : valeur manquante.")
        return

    if rtype == "A":
        try:
            ipaddress.IPv4Address(value)
        except ValueError:
            errors.append(f"{label} ({rtype} {name}) : '{value}' n'est pas une adresse IPv4 valide.")
    elif rtype == "AAAA":
        try:
            ipaddress.IPv6Address(value)
        except ValueError:
            errors.append(f"{label} ({rtype} {name}) : '{value}' n'est pas une adresse IPv6 valide.")
    elif rtype in ("CNAME", "NS", "MX"):
        if not value.endswith("."):
            errors.append(
                f"{label} ({rtype} {name}) : la cible '{value}' devrait se terminer par un point "
                "(nom pleinement qualifie), sinon elle serait interpretee comme relative au domaine."
            )

    if rtype == "MX":
        priority = record.get("priority")
        if priority is None or not isinstance(priority, int) or not (0 <= priority <= 65535):
            errors.append(f"{label} (MX {name}) : priorite manquante ou invalide (entier entre 0 et 65535).")

    if rtype == "SRV":
        for field in ("priority", "weight", "port"):
            v = record.get(field)
            if v is None or not isinstance(v, int) or not (0 <= v <= 65535):
                errors.append(f"{label} (SRV {name}) : champ '{field}' manquant ou invalide (entier entre 0 et 65535).")

    if rtype == "CAA":
        tag = record.get("tag", "")
        if tag not in CAA_TAGS:
            errors.append(f"{label} (CAA {name}) : tag invalide ('{tag}'). Disponibles : {', '.join(CAA_TAGS)}.")
        flag = record.get("flag", 0)
        if not isinstance(flag, int) or flag not in (0, 128):
            errors.append(f"{label} (CAA {name}) : flag invalide ('{flag}'). Attendu : 0 ou 128.")


def validate_config(config):
    """
    Verifie la coherence d'une config avant generation.
    Retourne une liste d'erreurs (vide si tout est valide).
    """
    errors = []

    engine = config.get("engine", DEFAULT_ENGINE)
    if engine not in SUPPORTED_ENGINES:
        errors.append(f"Moteur non supporte : '{engine}'. Disponibles : {', '.join(SUPPORTED_ENGINES)}.")

    domain = (config.get("domain") or "").strip().rstrip(".")
    if not domain:
        errors.append("Domaine manquant.")
    elif not DOMAIN_RE.match(domain):
        errors.append(f"Domaine invalide : '{domain}'.")

    soa = config.get("soa") or {}
    if not (soa.get("primary_ns") or "").strip():
        errors.append("SOA : serveur de noms principal manquant (primary_ns).")
    if not (soa.get("admin_email") or "").strip():
        errors.append("SOA : contact administrateur manquant (admin_email).")

    if not config.get("nameservers"):
        errors.append("Aucun serveur de noms declare (nameservers) : la delegation ne fonctionnerait pas.")

    records = config.get("records") or []
    if not records:
        errors.append("Aucun enregistrement defini : ajoute au moins un enregistrement.")

    for index, record in enumerate(records, start=1):
        _validate_record(record, index, errors)

    # Regle DNS : un nom portant un CNAME ne peut porter AUCUN autre
    # enregistrement, et l'apex (@) ne peut jamais avoir de CNAME (il lui
    # faut un SOA/NS, incompatibles avec un CNAME au meme niveau).
    names_by_type = {}
    for record in records:
        name = (record.get("name") or "").strip()
        names_by_type.setdefault(name, set()).add(record.get("type"))

    for name, types in names_by_type.items():
        if "CNAME" in types:
            if name == "@":
                errors.append("La racine du domaine (@) ne peut pas porter de CNAME (incompatible avec SOA/NS).")
            elif len(types) > 1:
                autres = ", ".join(sorted(types - {"CNAME"}))
                errors.append(f"'{name}' porte un CNAME et d'autres enregistrements ({autres}) : un nom avec CNAME ne peut avoir que ça.")

    return errors


# --------------------------------------------------------------------------
# Backend BIND : fichier de zone maitre
# --------------------------------------------------------------------------
def _bind_record_line(record, ttl_column_width=6):
    rtype = record["type"]
    name = record["name"] if record["name"] != "@" else "@"

    if rtype == "MX":
        rdata = f"{record['priority']}\t{record['value']}"
    elif rtype == "TXT":
        rdata = f'"{record["value"]}"'
    elif rtype == "SRV":
        rdata = f"{record['priority']} {record['weight']} {record['port']} {record['value']}"
    elif rtype == "CAA":
        rdata = f'{record.get("flag", 0)} {record["tag"]} "{record["value"]}"'
    else:
        rdata = record["value"]

    return f"{name}\tIN\t{rtype}\t{rdata}"


def generate_bind_zone(config):
    """Genere le contenu d'un fichier de zone BIND (RFC 1035)."""
    domain = config["domain"].rstrip(".")
    ttl = config.get("ttl", 3600)
    soa = config["soa"]
    serial = config.get("serial") or _today_serial()

    lines = [
        "; Genere par OpsForge (module dns).",
        f"; A placer dans la zone de {domain}. sur ton serveur DNS (BIND/PowerDNS/Knot)",
        "; ou a importer chez ton registrar si il accepte un fichier de zone.",
        ";",
        "; Le numero de serie ci-dessous est date du jour de generation : si tu",
        "; regeneres et republies plusieurs fois le MEME jour, incremente-le a la",
        "; main (les serveurs secondaires ne resynchronisent que si le serial a",
        "; strictement augmente).",
        f"$ORIGIN {domain}.",
        f"$TTL {ttl}",
        "",
        f"@\tIN\tSOA\t{soa['primary_ns']} {soa['admin_email']} (",
        f"\t\t\t{serial}\t; serial",
        f"\t\t\t{soa.get('refresh', 3600)}\t; refresh",
        f"\t\t\t{soa.get('retry', 900)}\t; retry",
        f"\t\t\t{soa.get('expire', 1209600)}\t; expire",
        f"\t\t\t{soa.get('minimum', 3600)} )\t; minimum",
        "",
    ]

    for ns in config.get("nameservers") or []:
        lines.append(f"\tIN\tNS\t{ns}")
    lines.append("")

    for record in config.get("records") or []:
        lines.append(_bind_record_line(record))

    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Backend Route53 : lot de changements JSON
# --------------------------------------------------------------------------
def _route53_value(record):
    rtype = record["type"]
    if rtype == "MX":
        return f"{record['priority']} {record['value']}"
    if rtype == "TXT":
        # Route53 exige les guillemets entourant la valeur DANS la chaine
        # elle-meme (echappes), sinon la valeur TXT est tronquee au premier
        # espace a la reception par l'API.
        escaped = record["value"].replace('"', '\\"')
        return f'"{escaped}"'
    if rtype == "SRV":
        return f"{record['priority']} {record['weight']} {record['port']} {record['value']}"
    if rtype == "CAA":
        return f'{record.get("flag", 0)} {record["tag"]} "{record["value"]}"'
    return record["value"]


def generate_route53_json(config):
    """Genere un lot de changements JSON pret pour `aws route53 change-resource-record-sets`."""
    import json

    domain = config["domain"].rstrip(".")
    ttl = config.get("ttl", 3600)

    changes = []
    for record in config.get("records") or []:
        fqdn = _fqdn(record["name"], domain)
        changes.append({
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": fqdn,
                "Type": record["type"],
                "TTL": record.get("ttl", ttl),
                "ResourceRecords": [{"Value": _route53_value(record)}],
            },
        })

    batch = {
        "Comment": f"Genere par OpsForge (module dns) pour {domain}.",
        "Changes": changes,
    }

    return json.dumps(batch, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------
# Point d'entree principal.
# --------------------------------------------------------------------------
def generate_dns(config):
    """
    Genere le fichier DNS a partir d'une config validee.
    Retourne {nom_fichier: contenu texte}.
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))

    config = copy.deepcopy(config)
    engine = config.get("engine", DEFAULT_ENGINE)
    domain = config["domain"].rstrip(".")

    if engine == "bind":
        return {f"{domain}.zone": generate_bind_zone(config)}
    return {f"{domain}.route53.json": generate_route53_json(config)}


def write_dns(config, output_dir):
    """Ecrit le fichier genere dans output_dir. Retourne la liste des chemins ecrits."""
    files = generate_dns(config)
    written = []
    for filename, content in files.items():
        path = os.path.join(output_dir, filename)
        os.makedirs(os.path.dirname(path) or output_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(path)

    return written
