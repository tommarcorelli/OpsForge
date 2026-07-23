"""
modules/packer/core.py
----------------------
Coeur du module Packer d'OpsForge — dernier maillon de la chaine
Packer (construit l'image) -> Vagrant/Terraform (l'instancie) -> cloud-init
(la configure au premier boot) -> Ansible (deploiement applicatif).

Genere un template HCL2 (`build.pkr.hcl`) a partir d'une config :
  - un builder ("source")   : virtualbox-iso, qemu, amazon-ebs ou docker
  - des arguments source    : { "iso_url": "...", "ssh_username": "...", ... }
  - des variables Packer    : [{ "name", "type", "default", "sensitive" }]
  - des provisioners        : shell-inline / shell-script / file
  - des post-processors     : vagrant / docker-tag / compress

Fonctions cles :
  - generate_packer_template(config) -> contenu HCL2 (un seul fichier)
  - validate_config(config)          -> liste d'erreurs (vide si valide)
  - PRESETS / get_preset             -> configs pretes a l'emploi
  - BUILDER_CATALOG                  -> builders geres + args requis/defauts

Le rendu HCL est fait a la main (pas de lib HCL2 fiable cote generation),
sur le meme principe que modules/terraform/core.py : alignement des `=`
façon `terraform fmt`, et prefixe "=" pour ecrire une valeur brute (reference
Packer, ex. "=var.ssh_password" -> var.ssh_password non guillemete).
"""

import copy
import os
import re

OUTPUT_FILENAME = "build.pkr.hcl"

# Nom de build / variable Packer : identifiant HCL simple.
_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]*$")

# --------------------------------------------------------------------------
# Catalogue des builders (= blocs "source") geres
# --------------------------------------------------------------------------
BUILDER_CATALOG = {
    "virtualbox-iso": {
        "label": "VirtualBox (ISO → box local)",
        "plugin": {"source": "github.com/hashicorp/virtualbox", "version": ">= 1.0.0"},
        "required": ["iso_url", "iso_checksum", "ssh_username", "ssh_password"],
        "defaults": {
            "guest_os_type": "Ubuntu_64",
            "disk_size": 20000,
            "headless": True,
            "communicator": "ssh",
            "boot_wait": "5s",
            "shutdown_command": "echo 'packer' | sudo -S shutdown -P now",
        },
        "post_processors": ["vagrant", "compress"],
    },
    "qemu": {
        "label": "QEMU / KVM (ISO → image qcow2)",
        "plugin": {"source": "github.com/hashicorp/qemu", "version": ">= 1.0.0"},
        "required": ["iso_url", "iso_checksum", "ssh_username", "ssh_password"],
        "defaults": {
            "disk_size": 20000,
            "accelerator": "kvm",
            "format": "qcow2",
            "headless": True,
            "communicator": "ssh",
            "boot_wait": "5s",
            "shutdown_command": "echo 'packer' | sudo -S shutdown -P now",
        },
        "post_processors": ["vagrant", "compress"],
    },
    "amazon-ebs": {
        "label": "Amazon AMI (EBS-backed)",
        "plugin": {"source": "github.com/hashicorp/amazon", "version": ">= 1.3.0"},
        "required": ["region", "source_ami", "instance_type", "ssh_username", "ami_name"],
        "defaults": {"communicator": "ssh"},
        "post_processors": ["compress"],
    },
    "docker": {
        "label": "Docker (image conteneur)",
        "plugin": {"source": "github.com/hashicorp/docker", "version": ">= 1.0.0"},
        "required": ["image"],
        "defaults": {"commit": True},
        "post_processors": ["docker-tag", "compress"],
    },
}

# Provisioners geres.
PROVISIONER_TYPES = ("shell-inline", "shell-script", "file")

# Post-processors geres, avec leurs arguments requis eventuels.
POST_PROCESSOR_CATALOG = {
    "vagrant": {"label": "Export .box Vagrant", "required": []},
    "docker-tag": {"label": "Tag d'image Docker", "required": ["repository", "tag"]},
    "compress": {"label": "Compression de l'artefact (.tar.gz)", "required": []},
}


def _clean(value):
    return value.strip() if isinstance(value, str) else value


def _as_list(value):
    """Accepte une liste, ou une chaine (separateurs retour ligne)."""
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split("\n") if part.strip()]
    return []


# --------------------------------------------------------------------------
# Rendu HCL2 (alignement façon `packer fmt`)
# --------------------------------------------------------------------------
def _indent(text, spaces):
    pad = " " * spaces
    return "\n".join((pad + ligne if ligne else ligne) for ligne in text.split("\n"))


def _hcl_value(value):
    """Rend une valeur Python en HCL2 (chaine, bool, nombre, liste, bloc imbrique)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # Une valeur prefixee par '=' est ecrite brute (reference Packer,
        # ex. "=var.ssh_password" -> var.ssh_password ; "=timestamp()" -> timestamp()).
        if value.startswith("="):
            return value[1:]
        echappe = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{echappe}"'
    if isinstance(value, list):
        if not value:
            return "[]"
        elements = ", ".join(_hcl_value(v) for v in value)
        # Liste courte (inline) si tout tient sur une ligne raisonnable.
        if len(elements) <= 70 and "\n" not in elements:
            return "[" + elements + "]"
        corps = ",\n".join(_hcl_value(v) for v in value)
        return "[\n" + _indent(corps, 2) + "\n]"
    if isinstance(value, dict):
        return "{\n" + _indent(_hcl_body(value), 2) + "\n}"
    if value is None:
        return "null"
    return f'"{value}"'


def _hcl_body(args):
    """Rend un dict d'arguments en corps de bloc HCL2, `=` alignes par bloc."""
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


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate_config(config):
    """Verifie la coherence d'une config avant generation. Retourne une liste d'erreurs."""
    errors = []

    builder = _clean(config.get("builder"))
    if not builder:
        errors.append("Choisis un builder (virtualbox-iso, qemu, amazon-ebs ou docker).")
        return errors
    if builder not in BUILDER_CATALOG:
        errors.append(
            f"Builder inconnu : '{builder}'. Disponibles : {', '.join(BUILDER_CATALOG.keys())}."
        )
        return errors

    name = _clean(config.get("name"))
    if not name:
        errors.append("Le nom du build est requis (ex : ubuntu-base).")
    elif not _NAME_RE.match(name):
        errors.append(f"Nom de build invalide : '{name}' (lettres, chiffres, - et _ uniquement).")

    catalog = BUILDER_CATALOG[builder]
    args = config.get("args") or {}
    manquants = [
        champ for champ in catalog["required"]
        if not str(args.get(champ, "")).strip()
    ]
    if manquants:
        errors.append(
            f"Champs requis manquants pour {builder} : {', '.join(manquants)}."
        )

    for i, var in enumerate(config.get("variables") or []):
        vname = _clean(var.get("name"))
        if not vname:
            errors.append(f"Variable #{i + 1} : le nom est requis.")
        elif not _NAME_RE.match(vname):
            errors.append(f"Variable #{i + 1} : nom invalide '{vname}'.")

    for i, prov in enumerate(config.get("provisioners") or []):
        ptype = prov.get("type")
        if ptype not in PROVISIONER_TYPES:
            errors.append(
                f"Provisioner #{i + 1} : type inconnu '{ptype}' "
                f"(attendu : {', '.join(PROVISIONER_TYPES)})."
            )
            continue
        if ptype == "shell-inline" and not _as_list(prov.get("inline")):
            errors.append(f"Provisioner #{i + 1} (shell-inline) : au moins une commande est requise.")
        if ptype == "shell-script" and not _clean(prov.get("script")):
            errors.append(f"Provisioner #{i + 1} (shell-script) : le chemin du script est requis.")
        if ptype == "file" and (not _clean(prov.get("source")) or not _clean(prov.get("destination"))):
            errors.append(f"Provisioner #{i + 1} (file) : source et destination sont requises.")

    for i, pp in enumerate(config.get("post_processors") or []):
        pname = pp.get("type") if isinstance(pp, dict) else pp
        if pname not in POST_PROCESSOR_CATALOG:
            errors.append(f"Post-processor #{i + 1} : inconnu '{pname}'.")
            continue
        if pname not in catalog.get("post_processors", []):
            errors.append(
                f"Post-processor '{pname}' incompatible avec le builder '{builder}'."
            )
            continue
        if isinstance(pp, dict):
            pp_required = POST_PROCESSOR_CATALOG[pname]["required"]
            pp_manquants = [c for c in pp_required if not str(pp.get(c, "")).strip()]
            if pp_manquants:
                errors.append(
                    f"Post-processor #{i + 1} ({pname}) : champs manquants {', '.join(pp_manquants)}."
                )

    return errors


# --------------------------------------------------------------------------
# Construction des blocs
# --------------------------------------------------------------------------
def _plugin_block(builder):
    plugin = BUILDER_CATALOG[builder]["plugin"]
    plugin_key = builder.split("-")[0]  # virtualbox-iso -> virtualbox, amazon-ebs -> amazon
    corps = _hcl_body({"version": plugin["version"], "source": plugin["source"]})
    inner = f"{plugin_key} {{\n" + _indent(corps, 2) + "\n}"
    return "packer {\n" + _indent("required_plugins {\n" + _indent(inner, 2) + "\n}", 2) + "\n}"


def _variable_blocks(variables):
    blocs = []
    for var in variables or []:
        name = _clean(var.get("name"))
        if not name:
            continue
        args = {"type": f"={var.get('type', 'string')}"}
        if "default" in var and var["default"] not in (None, ""):
            args["default"] = var["default"]
        if var.get("sensitive"):
            args["sensitive"] = True
        blocs.append(_render_block("variable", [name], args))
    return blocs


def _source_block(builder, name, args):
    catalog = BUILDER_CATALOG[builder]
    merged = dict(catalog["defaults"])
    merged.update(args or {})
    return _render_block("source", [builder, name], merged)


def _provisioner_block(prov):
    ptype = prov["type"]
    if ptype == "shell-inline":
        return _render_block("provisioner", ["shell"], {"inline": _as_list(prov.get("inline"))})
    if ptype == "shell-script":
        args = {"script": _clean(prov["script"])}
        env = prov.get("env_vars") or {}
        if env:
            args["environment_vars"] = [f"{k}={v}" for k, v in env.items()]
        return _render_block("provisioner", ["shell"], args)
    if ptype == "file":
        return _render_block("provisioner", ["file"], {
            "source": _clean(prov["source"]),
            "destination": _clean(prov["destination"]),
        })
    raise ValueError(f"Type de provisioner non gere : {ptype}")


def _post_processor_block(pp):
    name = pp.get("type") if isinstance(pp, dict) else pp
    args = {k: v for k, v in pp.items() if k != "type"} if isinstance(pp, dict) else {}
    return _render_block("post-processor", [name], args)


def _build_block(builder, name, config):
    lignes = [f'sources = ["source.{builder}.{name}"]', ""]

    for prov in config.get("provisioners") or []:
        lignes.append(_provisioner_block(prov))
        lignes.append("")

    for pp in config.get("post_processors") or []:
        lignes.append(_post_processor_block(pp))
        lignes.append("")

    corps = "\n".join(lignes).rstrip("\n")
    return "build {\n" + _indent(corps, 2) + "\n}"


# --------------------------------------------------------------------------
# API publique
# --------------------------------------------------------------------------
def generate_packer_template(config):
    """
    Genere le contenu complet d'un template Packer HCL2 (`build.pkr.hcl`).

    Args:
        config (dict): voir validate_config() pour les cles attendues.

    Returns:
        str: contenu HCL2 pret pour `packer build`.

    Raises:
        ValueError: si la config est invalide.
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    builder = _clean(config["builder"])
    name = _clean(config["name"])

    blocs = [
        _plugin_block(builder),
        *_variable_blocks(config.get("variables")),
        _source_block(builder, name, config.get("args") or {}),
        _build_block(builder, name, config),
    ]
    return "\n\n".join(blocs) + "\n"


def generate_files(config):
    """Retourne {nom_de_fichier: contenu} (une seule entree : build.pkr.hcl)."""
    return {OUTPUT_FILENAME: generate_packer_template(config)}


def generate_combined(config):
    return generate_packer_template(config)


def write_files(config, output_dir):
    """Genere le fichier et l'ecrit dans output_dir. Retourne les chemins."""
    content = generate_packer_template(config)
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, OUTPUT_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return [path]


def list_builders():
    return list(BUILDER_CATALOG.keys())


def get_builder_info(builder):
    if builder not in BUILDER_CATALOG:
        raise ValueError(f"Builder inconnu : '{builder}'.")
    catalog = BUILDER_CATALOG[builder]
    return {
        "label": catalog["label"],
        "required": catalog["required"],
        "defaults": catalog["defaults"],
        "post_processors": catalog["post_processors"],
    }


# --------------------------------------------------------------------------
# Presets prets a l'emploi
# --------------------------------------------------------------------------
PRESETS = {
    "ubuntu-vagrant-box": {
        "builder": "virtualbox-iso",
        "name": "ubuntu-base",
        "args": {
            "iso_url": "https://releases.ubuntu.com/22.04/ubuntu-22.04.4-live-server-amd64.iso",
            "iso_checksum": "file:https://releases.ubuntu.com/22.04/SHA256SUMS",
            "ssh_username": "vagrant",
            "ssh_password": "vagrant",
            "vm_name": "ubuntu-base",
            "output_directory": "output/ubuntu-base",
            "boot_command": [
                "<esc><wait>e<wait>",
                "<down><down><down><end> autoinstall ds=nocloud;<f10>",
            ],
            "http_directory": "http",
        },
        "variables": [
            {"name": "ssh_password", "type": "string", "default": "vagrant", "sensitive": True},
        ],
        "provisioners": [
            {"type": "shell-inline", "inline": [
                "apt-get update",
                "apt-get upgrade -y",
                "apt-get install -y qemu-guest-agent curl",
            ]},
            {"type": "shell-inline", "inline": ["rm -f /etc/ssh/ssh_host_*"]},
        ],
        "post_processors": ["vagrant"],
    },
    "debian-qemu-image": {
        "builder": "qemu",
        "name": "debian-base",
        "args": {
            "iso_url": "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-12.5.0-amd64-netinst.iso",
            "iso_checksum": "file:https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/SHA256SUMS",
            "ssh_username": "debian",
            "ssh_password": "debian",
            "vm_name": "debian-base",
            "output_directory": "output/debian-base",
            "memory": 2048,
            "cpus": 2,
        },
        "provisioners": [
            {"type": "shell-inline", "inline": [
                "apt-get update",
                "apt-get install -y curl vim git",
            ]},
        ],
        "post_processors": ["vagrant", "compress"],
    },
    "aws-ami-webserver": {
        "builder": "amazon-ebs",
        "name": "webserver-ami",
        "args": {
            "region": "eu-west-1",
            "source_ami": "ami-0c1c30571d2dae5c9",
            "instance_type": "t3.micro",
            "ssh_username": "ubuntu",
            "ami_name": "webserver-{{timestamp}}",
        },
        "variables": [
            {"name": "region", "type": "string", "default": "eu-west-1"},
        ],
        "provisioners": [
            {"type": "shell-inline", "inline": [
                "sudo apt-get update",
                "sudo apt-get install -y nginx",
                "sudo systemctl enable nginx",
            ]},
        ],
        "post_processors": [],
    },
    "docker-app-image": {
        "builder": "docker",
        "name": "app-image",
        "args": {
            "image": "python:3.12-slim",
            "commit": True,
        },
        "provisioners": [
            {"type": "file", "source": "app/", "destination": "/app"},
            {"type": "shell-inline", "inline": [
                "pip install --no-cache-dir -r /app/requirements.txt",
            ]},
        ],
        "post_processors": [
            {"type": "docker-tag", "repository": "mon-org/app", "tag": "latest"},
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
