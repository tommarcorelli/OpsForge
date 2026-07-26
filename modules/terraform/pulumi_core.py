"""
modules/terraform/pulumi_core.py
----------------------------------
Troisieme moteur de sortie du module Terraform d'OpsForge : genere un
programme **Pulumi (Python)** a partir de la MEME liste de ressources que
le moteur HCL (core.py) — contrairement a CloudFormation (AWS uniquement,
catalogue a part), Pulumi reutilise directement le RESOURCE_CATALOG de
core.py pour aws/google/azurerm/docker (les SDK pulumi_aws/pulumi_gcp/
pulumi_azure sont derives des memes schemas de provider Terraform, d'ou
des noms d'arguments identiques en snake_case).

`local` n'est volontairement PAS supporte ici : Terraform a un provider
`hashicorp/local` dedie (local_file...), mais Pulumi n'a pas d'equivalent
officiel direct — inventer un faux nom de paquet serait pire que de ne
pas le proposer.

Reference entre ressources : meme echappatoire '=' que les autres
moteurs, mais en **Python brut** ici (ex: "=aws_instance_web.public_ip"),
a faire pointer vers le nom de variable Python du builder — deterministe :
`sanitize(f"{type}_{name}")` (evite les collisions si deux ressources de
types differents partagent le meme "name", ce qu'autorise le builder
partage puisque l'unicite n'est verifiee que par couple (type, name)).

Fonctions cles :
  - generate_pulumi(config)   -> contenu __main__.py
  - valider_config(config)    -> (erreurs, avertissements)
  - PRESETS / obtenir_preset  -> configs pretes a l'emploi
"""

import copy
import os
import re

OUTPUT_FILENAME = "__main__.py"

# Provider Terraform -> (paquet pip, alias d'import Python)
PULUMI_PROVIDERS = {
    "aws": ("pulumi_aws", "aws"),
    "google": ("pulumi_gcp", "gcp"),
    "azurerm": ("pulumi_azure", "azure"),
    "docker": ("pulumi_docker", "docker"),
}

# (provider, type Terraform) -> chemin Python sous l'alias importe
# (ex: "ec2.Instance" -> aws.ec2.Instance(...)). Le sous-ensemble Azure est
# fait au mieux : le SDK classique `pulumi_azure` (derive de l'ancien
# schema azurerm) ne colle pas toujours 1:1 aux ressources Terraform les
# plus recentes (ex: azurerm_linux_virtual_machine vs compute.VirtualMachine).
RESOURCE_TYPE_MAP = {
    ("aws", "aws_instance"): "ec2.Instance",
    ("aws", "aws_s3_bucket"): "s3.Bucket",
    ("aws", "aws_security_group"): "ec2.SecurityGroup",
    ("aws", "aws_vpc"): "ec2.Vpc",
    ("aws", "aws_subnet"): "ec2.Subnet",
    ("aws", "aws_db_instance"): "rds.Instance",
    ("aws", "aws_internet_gateway"): "ec2.InternetGateway",
    ("aws", "aws_route_table"): "ec2.RouteTable",
    ("aws", "aws_route_table_association"): "ec2.RouteTableAssociation",
    ("aws", "aws_iam_role"): "iam.Role",
    ("aws", "aws_lambda_function"): "lambda_.Function",
    ("google", "google_compute_instance"): "compute.Instance",
    ("google", "google_storage_bucket"): "storage.Bucket",
    ("google", "google_compute_network"): "compute.Network",
    ("google", "google_compute_firewall"): "compute.Firewall",
    ("google", "google_sql_database_instance"): "sql.DatabaseInstance",
    ("azurerm", "azurerm_resource_group"): "core.ResourceGroup",
    ("azurerm", "azurerm_storage_account"): "storage.Account",
    ("azurerm", "azurerm_virtual_network"): "network.VirtualNetwork",
    ("azurerm", "azurerm_linux_virtual_machine"): "compute.VirtualMachine",
    ("docker", "docker_image"): "Image",
    ("docker", "docker_container"): "Container",
    ("docker", "docker_network"): "Network",
    ("docker", "docker_volume"): "Volume",
}

_IDENT_RE = re.compile(r"[^0-9a-zA-Z_]")


def _var_name(rtype, rname):
    """Nom de variable Python deterministe pour une ressource : evite les
    collisions entre deux ressources de types differents partageant le
    meme 'name' (autorise par la validation du builder partage)."""
    base = _IDENT_RE.sub("_", f"{rtype}_{rname}")
    if base[:1].isdigit():
        base = "_" + base
    return base


def _py_value(value, indent=1):
    """Rend une valeur Python config en litteral de code Python. Une chaine
    prefixee par '=' est ecrite BRUTE (reference Python, ex: "=web.id" ->
    web.id) ; le reste passe par repr()/construction recursive, qui gere
    deja correctement l'echappement des guillemets."""
    if isinstance(value, str):
        if value.startswith("="):
            return value[1:]
        return repr(value)
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        items = ", ".join(_py_value(v, indent) for v in value)
        return f"[{items}]"
    if isinstance(value, dict):
        pad = "    " * indent
        closing_pad = "    " * (indent - 1)
        lignes = [f'{pad}"{k}": {_py_value(v, indent + 1)},' for k, v in value.items()]
        return "{\n" + "\n".join(lignes) + f"\n{closing_pad}" + "}"
    if value is None:
        return "None"
    return repr(value)


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
        erreurs.append("Aucun provider specifie.")
    elif provider == "local":
        erreurs.append(
            "Pulumi n'a pas d'equivalent officiel au provider Terraform 'local' "
            "— choisis aws, google, azurerm ou docker."
        )
    elif provider not in PULUMI_PROVIDERS:
        erreurs.append(
            f"Provider inconnu pour l'export Pulumi : '{provider}'. "
            f"Disponibles : {', '.join(PULUMI_PROVIDERS)}."
        )

    resources = config.get("resources") or []
    if not resources:
        avertissements.append("Aucune ressource : le programme genere ne contiendra que les imports.")

    if provider in PULUMI_PROVIDERS:
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
                continue
            cle = (rtype, rname)
            if cle in noms_vus:
                erreurs.append(f"{etiquette} : {rtype}.{rname} est defini en double.")
            noms_vus.add(cle)

            if (provider, rtype) not in RESOURCE_TYPE_MAP:
                erreurs.append(
                    f"{rtype} : type non pris en charge par l'export Pulumi pour '{provider}' "
                    f"(mapping manquant vers une classe pulumi_{provider if provider != 'azurerm' else 'azure'})."
                )

    return erreurs, avertissements


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def generate_pulumi(config):
    """Construit le contenu d'un `__main__.py` Pulumi. Leve ValueError si
    la config est invalide ou contient un type de ressource non mappe."""
    config = config or {}
    erreurs, _ = valider_config(config)
    if erreurs:
        raise ValueError(" ; ".join(erreurs))

    provider = config["provider"]
    module_name, alias = PULUMI_PROVIDERS[provider]

    blocs = []
    for res in config.get("resources") or []:
        rtype = res["type"]
        rname = res["name"]
        args = res.get("args") or {}
        pulumi_path = RESOURCE_TYPE_MAP[(provider, rtype)]
        var_name = _var_name(rtype, rname)

        if args:
            kwargs_lignes = "\n".join(
                f"    {cle}={_py_value(valeur, 2)}," for cle, valeur in args.items()
            )
            bloc = (
                f'{var_name} = {alias}.{pulumi_path}("{rname}",\n'
                f"{kwargs_lignes}\n"
                f")"
            )
        else:
            bloc = f'{var_name} = {alias}.{pulumi_path}("{rname}")'
        blocs.append(bloc)

    entete = [
        "# Genere par OpsForge (module Terraform - export Pulumi)",
        "",
        "import pulumi",
        f"import {module_name} as {alias}",
    ]

    provider_config = config.get("provider_config") or {}
    if provider_config:
        entete.append("")
        entete.append("# Configuration provider : a definir via la config de stack Pulumi plutot")
        entete.append("# que dans le code, ex:")
        for cle, valeur in provider_config.items():
            entete.append(f"#   pulumi config set {provider}:{cle} {valeur}")

    parties = ["\n".join(entete)]
    if blocs:
        parties.append("\n\n".join(blocs))

    outputs = config.get("outputs") or {}
    if outputs:
        lignes_export = [f'pulumi.export("{nom}", {_py_value(valeur)})' for nom, valeur in outputs.items()]
        parties.append("\n".join(lignes_export))

    return "\n\n".join(parties) + "\n"


def write_pulumi(config, output_path):
    contenu = generate_pulumi(config)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(contenu)
    return output_path


# ---------------------------------------------------------------------------
# Presets prets a l'emploi (proprietaires a Pulumi : les references entre
# ressources y sont deja exprimees en Python brut via '=', pas en HCL).
# ---------------------------------------------------------------------------
PRESETS = {
    "ec2-web": {
        "label": "EC2 + Security Group (web)",
        "config": {
            "provider": "aws",
            "provider_config": {"region": "eu-west-1"},
            "resources": [
                {"type": "aws_security_group", "name": "web", "args": {
                    "description": "Autorise HTTP/HTTPS"}},
                {"type": "aws_instance", "name": "web", "args": {
                    "ami": "ami-0abcdef1234567890", "instance_type": "t3.micro",
                    "vpc_security_group_ids": ["=aws_security_group_web.id"],
                    "tags": {"Name": "serveur-web"}}},
            ],
            "outputs": {"public_ip": "=aws_instance_web.public_ip"},
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
            "outputs": {"bucket_name": "=aws_s3_bucket_site.bucket"},
        },
    },
    "vpc-basic": {
        "label": "VPC + subnet public",
        "config": {
            "provider": "aws",
            "provider_config": {"region": "eu-west-1"},
            "resources": [
                {"type": "aws_vpc", "name": "main", "args": {
                    "cidr_block": "10.0.0.0/16", "tags": {"Name": "main"}}},
                {"type": "aws_subnet", "name": "public", "args": {
                    "vpc_id": "=aws_vpc_main.id", "cidr_block": "10.0.1.0/24"}},
            ],
            "outputs": {
                "vpc_id": "=aws_vpc_main.id",
                "subnet_id": "=aws_subnet_public.id",
            },
        },
    },
    "docker-nginx": {
        "label": "Conteneur Docker Nginx",
        "config": {
            "provider": "docker",
            "resources": [
                {"type": "docker_image", "name": "nginx", "args": {"name": "nginx:latest"}},
                {"type": "docker_container", "name": "web", "args": {
                    "name": "web", "image": "=docker_image_nginx.image_id",
                    "ports": [{"internal": 80, "external": 8080}]}},
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


def list_presets():
    return list(PRESETS.keys())


def obtenir_preset(nom):
    if nom not in PRESETS:
        raise KeyError(nom)
    return copy.deepcopy(PRESETS[nom]["config"])
