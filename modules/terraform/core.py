"""
modules/terraform/core.py
-------------------------
Cœur du module Terraform d'OpsForge.

Génère un `main.tf` à partir d'une config :
  - un provider (aws, google, azurerm, docker, local...)
  - une liste de ressources { "type", "name", "args": {...} }
  - (optionnel) des variables et des outputs

Fonctions clés :
  - generate_terraform(config)  -> contenu HCL (aligné façon `terraform fmt`)
  - valider_config(config)      -> (erreurs, avertissements) avec check des args
                                   requis par type de ressource (RESOURCE_CATALOG)
  - PRESETS / obtenir_preset    -> configs prêtes à l'emploi
  - RESOURCE_CATALOG            -> types de ressources courants + templates
"""

# ---------------------------------------------------------------------------
# Providers connus : nom Terraform -> (source registry, config par defaut)
# ---------------------------------------------------------------------------
SUPPORTED_PROVIDERS = {
    "aws":     {"source": "hashicorp/aws",       "version": "~> 5.0", "defaults": {"region": "eu-west-1"}},
    "google":  {"source": "hashicorp/google",    "version": "~> 5.0", "defaults": {"project": "mon-projet", "region": "europe-west1"}},
    "azurerm": {"source": "hashicorp/azurerm",   "version": "~> 3.0", "defaults": {"features": {}}},
    "docker":  {"source": "kreuzwerker/docker",  "version": "~> 3.0", "defaults": {}},
    "local":   {"source": "hashicorp/local",     "version": "~> 2.0", "defaults": {}},
}

# ---------------------------------------------------------------------------
# Catalogue des ressources courantes par provider.
# required : arguments obligatoires (validation). template : valeurs d'exemple.
# ---------------------------------------------------------------------------
RESOURCE_CATALOG = {
    "aws": [
        {"type": "aws_instance", "label": "Instance EC2", "required": ["ami", "instance_type"],
         "template": {"ami": "ami-0abcdef1234567890", "instance_type": "t3.micro", "tags": {"Name": "serveur-web"}}},
        {"type": "aws_s3_bucket", "label": "Bucket S3", "required": ["bucket"],
         "template": {"bucket": "mon-bucket-unique-123", "tags": {"Env": "prod"}}},
        {"type": "aws_security_group", "label": "Security Group", "required": ["name"],
         "template": {"name": "web-sg", "description": "Autorise HTTP/HTTPS"}},
        {"type": "aws_vpc", "label": "VPC", "required": ["cidr_block"],
         "template": {"cidr_block": "10.0.0.0/16", "tags": {"Name": "main"}}},
        {"type": "aws_subnet", "label": "Subnet", "required": ["vpc_id", "cidr_block"],
         "template": {"vpc_id": "=aws_vpc.main.id", "cidr_block": "10.0.1.0/24"}},
        {"type": "aws_db_instance", "label": "Base RDS", "required": ["allocated_storage", "engine", "instance_class", "username", "password"],
         "template": {"allocated_storage": 20, "engine": "postgres", "instance_class": "db.t3.micro",
                      "username": "admin", "password": "=var.db_password", "db_name": "app", "skip_final_snapshot": True}},
    ],
    "google": [
        {"type": "google_compute_instance", "label": "VM Compute Engine", "required": ["name", "machine_type", "zone"],
         "template": {"name": "vm-1", "machine_type": "e2-micro", "zone": "europe-west1-b"}},
        {"type": "google_storage_bucket", "label": "Bucket Storage", "required": ["name", "location"],
         "template": {"name": "mon-bucket-gcp", "location": "EU"}},
        {"type": "google_compute_network", "label": "Réseau VPC", "required": ["name"],
         "template": {"name": "vpc-1", "auto_create_subnetworks": False}},
    ],
    "azurerm": [
        {"type": "azurerm_resource_group", "label": "Resource Group", "required": ["name", "location"],
         "template": {"name": "rg-app", "location": "West Europe"}},
        {"type": "azurerm_storage_account", "label": "Storage Account", "required": ["name", "resource_group_name", "location", "account_tier", "account_replication_type"],
         "template": {"name": "storacct123", "resource_group_name": "rg-app", "location": "West Europe", "account_tier": "Standard", "account_replication_type": "LRS"}},
    ],
    "docker": [
        {"type": "docker_image", "label": "Image Docker", "required": ["name"],
         "template": {"name": "nginx:latest"}},
        {"type": "docker_container", "label": "Conteneur Docker", "required": ["name", "image"],
         "template": {"name": "nginx", "image": "nginx:latest"}},
    ],
    "local": [
        {"type": "local_file", "label": "Fichier local", "required": ["filename", "content"],
         "template": {"filename": "hello.txt", "content": "Hello depuis Terraform"}},
    ],
}


def _catalog_index():
    """Retourne { (provider, type): entry } pour lookup rapide."""
    idx = {}
    for provider, entries in RESOURCE_CATALOG.items():
        for e in entries:
            idx[(provider, e["type"])] = e
    return idx


# ---------------------------------------------------------------------------
# Presets prêts à l'emploi
# ---------------------------------------------------------------------------
PRESETS = {
    "ec2-web": {
        "label": "EC2 + Security Group (web)",
        "config": {
            "provider": "aws",
            "provider_config": {"region": "eu-west-1"},
            "resources": [
                {"type": "aws_security_group", "name": "web", "args": {"name": "web-sg", "description": "HTTP/HTTPS"}},
                {"type": "aws_instance", "name": "web", "args": {
                    "ami": "ami-0abcdef1234567890", "instance_type": "t3.micro",
                    "vpc_security_group_ids": ["=[aws_security_group.web.id]"],
                    "tags": {"Name": "serveur-web"}}},
            ],
            "outputs": {"ip_publique": {"value": "=aws_instance.web.public_ip"}},
        },
    },
    "s3-static": {
        "label": "Bucket S3 (site statique)",
        "config": {
            "provider": "aws",
            "provider_config": {"region": "eu-west-1"},
            "resources": [
                {"type": "aws_s3_bucket", "name": "site", "args": {"bucket": "mon-site-statique-123"}},
            ],
        },
    },
    "docker-nginx": {
        "label": "Conteneur Docker Nginx",
        "config": {
            "provider": "docker",
            "provider_config": {},
            "resources": [
                {"type": "docker_image", "name": "nginx", "args": {"name": "nginx:latest"}},
                {"type": "docker_container", "name": "web", "args": {
                    "name": "web", "image": "=docker_image.nginx.image_id",
                    "ports": {"internal": 80, "external": 8080}}},
            ],
        },
    },
    "gcp-vm": {
        "label": "VM Google Compute",
        "config": {
            "provider": "google",
            "provider_config": {"project": "mon-projet", "region": "europe-west1"},
            "resources": [
                {"type": "google_compute_instance", "name": "vm", "args": {
                    "name": "vm-1", "machine_type": "e2-micro", "zone": "europe-west1-b"}},
            ],
        },
    },
}


def obtenir_preset(nom):
    if nom not in PRESETS:
        raise KeyError(nom)
    # copie profonde simple (JSON round-trip) pour ne pas muter le preset
    import json
    return json.loads(json.dumps(PRESETS[nom]["config"]))


# ---------------------------------------------------------------------------
# Rendu HCL
# ---------------------------------------------------------------------------
def _indent(text, spaces):
    pad = " " * spaces
    return "\n".join((pad + ligne if ligne else ligne) for ligne in text.split("\n"))


def _hcl_value(value):
    """Rend une valeur Python en HCL (chaîne, booléen, nombre, liste, bloc imbriqué)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # Échappatoire : une valeur préfixée par '=' est écrite brute (référence
        # Terraform, ex. "=var.region" -> var.region ; "=[a.b.id]" -> [a.b.id]).
        if value.startswith("="):
            return value[1:]
        echappe = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{echappe}"'
    if isinstance(value, list):
        return "[" + ", ".join(_hcl_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{\n" + _indent(_hcl_body(value), 2) + "\n}"
    if value is None:
        return "null"
    return f'"{value}"'


def _hcl_body(args):
    """Rend un dict d'arguments en corps de bloc HCL, avec alignement des '='
    façon `terraform fmt` (colonne commune par bloc)."""
    if not args:
        return ""
    width = max(len(str(k)) for k in args)
    lignes = []
    for cle, valeur in args.items():
        lignes.append(f"{str(cle).ljust(width)} = {_hcl_value(valeur)}")
    return "\n".join(lignes)


def _render_block(kind, labels, args):
    entete = kind
    for label in labels:
        entete += f' "{label}"'
    corps = _hcl_body(args)
    if corps:
        return f"{entete} {{\n" + _indent(corps, 2) + "\n}"
    return f"{entete} {{}}"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def valider_config(config):
    """Retourne (erreurs, avertissements) sans lever d'exception."""
    erreurs = []
    avertissements = []
    config = config or {}

    provider = config.get("provider")
    if not provider:
        erreurs.append("Aucun provider spécifié.")
    elif provider not in SUPPORTED_PROVIDERS:
        avertissements.append(
            f"Provider « {provider} » non référencé ({', '.join(SUPPORTED_PROVIDERS)}) : bloc généré quand même."
        )

    idx = _catalog_index()
    resources = config.get("resources") or []
    if not resources:
        avertissements.append("Aucune ressource : le fichier ne contiendra que les blocs terraform/provider.")

    noms_vus = set()
    for i, res in enumerate(resources):
        rtype = res.get("type")
        rname = res.get("name")
        etiquette = f"Ressource #{i + 1}"
        if not rtype:
            erreurs.append(f"{etiquette} : champ « type » manquant.")
            continue
        if not rname:
            erreurs.append(f"{etiquette} ({rtype}) : champ « name » manquant.")
        cle = (rtype, rname)
        if rname and cle in noms_vus:
            erreurs.append(f"{etiquette} : {rtype}.{rname} est défini en double.")
        noms_vus.add(cle)

        entry = idx.get((provider, rtype))
        if entry:
            args = res.get("args") or {}
            manquants = [a for a in entry["required"] if a not in args]
            if manquants:
                erreurs.append(f"{rtype}.{rname or '?'} : argument(s) requis manquant(s) : {', '.join(manquants)}.")
        elif provider in RESOURCE_CATALOG:
            avertissements.append(f"{rtype} : type non catalogué pour « {provider} » — généré sans validation des arguments.")

    return erreurs, avertissements


# ---------------------------------------------------------------------------
# Génération
# ---------------------------------------------------------------------------
def generate_terraform(config):
    """Construit le contenu d'un main.tf. Lève ValueError si config invalide."""
    config = config or {}
    erreurs, _ = valider_config(config)
    if erreurs:
        raise ValueError(" ; ".join(erreurs))

    provider = config["provider"]
    infos = SUPPORTED_PROVIDERS.get(
        provider, {"source": f"hashicorp/{provider}", "version": ">= 0", "defaults": {}}
    )

    # Bloc terraform { required_providers { ... } [backend "..." { ... }] }
    required_body = (
        f'{provider} = {{\n'
        f'  source  = "{infos["source"]}"\n'
        f'  version = "{infos["version"]}"\n'
        f'}}'
    )
    corps_terraform = "  required_providers {\n" + _indent(required_body, 4) + "\n  }"

    backend = config.get("backend")
    if backend and backend.get("type"):
        backend_block = _render_block("backend", [backend["type"]], backend.get("config") or {})
        corps_terraform += "\n\n" + _indent(backend_block, 2)

    bloc_terraform = "terraform {\n" + corps_terraform + "\n}"

    # Bloc provider
    provider_args = dict(infos.get("defaults", {}))
    provider_args.update(config.get("provider_config") or {})
    bloc_provider = _render_block("provider", [provider], provider_args)

    # Ressources
    blocs_res = []
    for res in config.get("resources") or []:
        blocs_res.append(_render_block("resource", [res["type"], res["name"]], res.get("args") or {}))

    # variables / outputs
    blocs_extra = []
    for nom, corps in (config.get("variables") or {}).items():
        blocs_extra.append(_render_block("variable", [nom], corps or {}))
    for nom, corps in (config.get("outputs") or {}).items():
        blocs_extra.append(_render_block("output", [nom], corps or {}))

    parties = [bloc_terraform, bloc_provider] + blocs_res + blocs_extra
    entete = "# Généré par OpsForge (module Terraform)\n\n"
    return entete + "\n\n".join(parties) + "\n"


def write_terraform(config, output_path):
    import os
    contenu = generate_terraform(config)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(contenu)
    return output_path
