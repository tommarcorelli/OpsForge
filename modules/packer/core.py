"""
modules/packer/core.py
----------------------
Coeur du module Packer d'OpsForge — dernier maillon de la chaine
Packer (construit l'image) -> Vagrant/Terraform (l'instancie) -> cloud-init
(la configure au premier boot) -> Ansible (deploiement applicatif).

Genere un template HCL2 (`build.pkr.hcl`) a partir d'une config :
  - un builder ("source")   : virtualbox-iso, qemu, amazon-ebs ou docker
  - des arguments source    : { "iso_url": "...", "ssh_username": "...", ... }
  - des datasources         : amazon-ami (recherche dynamique par filtres)
  - des variables Packer    : [{ "name", "type", "default", "sensitive" }]
  - des provisioners        : shell-inline / shell-script / powershell-inline / file / ansible
  - des post-processors     : vagrant / docker-tag / compress
  - une publication HCP     : hcp_registry (bucket_name, description, labels)

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
PROVISIONER_TYPES = ("shell-inline", "shell-script", "file", "powershell-inline", "ansible")

# Plugin requis par un provisioner, s'il en faut un en plus de celui du builder.
PROVISIONER_PLUGINS = {
    "ansible": {"source": "github.com/hashicorp/ansible", "version": ">= 1.1.1"},
}

# Post-processors geres, avec leurs arguments requis eventuels.
POST_PROCESSOR_CATALOG = {
    "vagrant": {"label": "Export .box Vagrant", "required": []},
    "docker-tag": {"label": "Tag d'image Docker", "required": ["repository", "tag"]},
    "compress": {"label": "Compression de l'artefact (.tar.gz)", "required": []},
}

# Datasources geres (blocs `data "..." "..."`), pour piocher des valeurs
# dynamiques (ex : dernier AMI Ubuntu officiel) au lieu d'un ID code en dur.
# Reutilise le plugin "amazon" (deja requis par le builder amazon-ebs).
DATASOURCE_CATALOG = {
    "amazon-ami": {
        "label": "Amazon AMI (recherche dynamique par filtres)",
        "plugin_key": "amazon",
        "plugin": {"source": "github.com/hashicorp/amazon", "version": ">= 1.3.0"},
        "required": ["filters"],
        "defaults": {"most_recent": True},
    },
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
        if ptype in ("shell-inline", "powershell-inline") and not _as_list(prov.get("inline")):
            libelle = "shell-inline" if ptype == "shell-inline" else "powershell-inline"
            errors.append(f"Provisioner #{i + 1} ({libelle}) : au moins une commande est requise.")
        if ptype == "shell-script" and not _clean(prov.get("script")):
            errors.append(f"Provisioner #{i + 1} (shell-script) : le chemin du script est requis.")
        if ptype == "file" and (not _clean(prov.get("source")) or not _clean(prov.get("destination"))):
            errors.append(f"Provisioner #{i + 1} (file) : source et destination sont requises.")
        if ptype == "ansible" and not _clean(prov.get("playbook_file")):
            errors.append(f"Provisioner #{i + 1} (ansible) : le chemin du playbook est requis.")

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

    for i, ds in enumerate(config.get("datasources") or []):
        dtype = ds.get("type")
        if dtype not in DATASOURCE_CATALOG:
            errors.append(
                f"Datasource #{i + 1} : type inconnu '{dtype}' "
                f"(attendu : {', '.join(DATASOURCE_CATALOG.keys())})."
            )
            continue
        dname = _clean(ds.get("name"))
        if not dname:
            errors.append(f"Datasource #{i + 1} : le nom est requis.")
        elif not _NAME_RE.match(dname):
            errors.append(f"Datasource #{i + 1} : nom invalide '{dname}'.")
        ds_args = ds.get("args") or {}
        ds_manquants = [
            champ for champ in DATASOURCE_CATALOG[dtype]["required"]
            if not ds_args.get(champ)
        ]
        if ds_manquants:
            errors.append(
                f"Datasource #{i + 1} ({dtype}) : champs manquants {', '.join(ds_manquants)}."
            )

    hcp = config.get("hcp_registry")
    if hcp is not None and not _clean(hcp.get("bucket_name")):
        errors.append("HCP Packer Registry : le nom du bucket (bucket_name) est requis.")

    return errors


# --------------------------------------------------------------------------
# Construction des blocs
# --------------------------------------------------------------------------
def _required_plugins(builder, config):
    """Rassemble tous les plugins requis (builder + datasources + provisioners),
    dedupliques par cle (ex : amazon-ebs et une datasource amazon-ami partagent
    le meme plugin "amazon", un seul bloc est emis)."""
    plugins = {}

    builder_key = builder.split("-")[0]  # virtualbox-iso -> virtualbox, amazon-ebs -> amazon
    plugins[builder_key] = BUILDER_CATALOG[builder]["plugin"]

    for ds in config.get("datasources") or []:
        catalog = DATASOURCE_CATALOG.get(ds.get("type"))
        if catalog:
            plugins[catalog["plugin_key"]] = catalog["plugin"]

    for prov in config.get("provisioners") or []:
        plugin = PROVISIONER_PLUGINS.get(prov.get("type"))
        if plugin:
            plugins[prov["type"]] = plugin

    return plugins


def _plugin_block(plugins):
    entries = []
    for key, plugin in plugins.items():
        corps = _hcl_body({"version": plugin["version"], "source": plugin["source"]})
        entries.append(f"{key} {{\n" + _indent(corps, 2) + "\n}")
    inner = "\n".join(entries)
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


def _datasource_block(ds):
    dtype = ds["type"]
    catalog = DATASOURCE_CATALOG[dtype]
    merged = dict(catalog["defaults"])
    merged.update(ds.get("args") or {})
    return _render_block("data", [dtype, _clean(ds["name"])], merged)


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
    if ptype == "powershell-inline":
        return _render_block("provisioner", ["powershell"], {"inline": _as_list(prov.get("inline"))})
    if ptype == "ansible":
        args = {"playbook_file": _clean(prov["playbook_file"])}
        if prov.get("user"):
            args["user"] = _clean(prov["user"])
        extra = _as_list(prov.get("extra_arguments"))
        if extra:
            args["extra_arguments"] = extra
        return _render_block("provisioner", ["ansible"], args)
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


def _hcp_registry_block(hcp):
    args = {"bucket_name": _clean(hcp["bucket_name"])}
    if hcp.get("description"):
        args["description"] = _clean(hcp["description"])
    if hcp.get("bucket_labels"):
        args["bucket_labels"] = hcp["bucket_labels"]
    if hcp.get("build_labels"):
        args["build_labels"] = hcp["build_labels"]
    return _render_block("hcp_packer_registry", [], args)


def _build_block(builder, name, config):
    lignes = [f'sources = ["source.{builder}.{name}"]', ""]

    hcp = config.get("hcp_registry")
    if hcp and _clean(hcp.get("bucket_name")):
        lignes.append(_hcp_registry_block(hcp))
        lignes.append("")

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
        _plugin_block(_required_plugins(builder, config)),
        *[_datasource_block(ds) for ds in config.get("datasources") or []],
        *_variable_blocks(config.get("variables")),
        _source_block(builder, name, config.get("args") or {}),
        _build_block(builder, name, config),
    ]
    return "\n\n".join(blocs) + "\n"


def generate_files(config):
    """Retourne {nom_de_fichier: contenu} (une seule entree : build.pkr.hcl)."""
    return {OUTPUT_FILENAME: generate_packer_template(config)}


def generate_split_files(config):
    """
    Genere le projet Packer en fichiers separes, a la convention officielle
    (`packer init` cherche tous les `*.pkr.hcl` d'un dossier) :
      - variables.pkr.hcl  (uniquement si des variables sont definies)
      - sources.pkr.hcl    (bloc `packer { required_plugins {...} }` + `source`)
      - build.pkr.hcl      (bloc `build`)

    Returns:
        dict: {nom_de_fichier: contenu}, dans l'ordre d'ecriture logique.

    Raises:
        ValueError: si la config est invalide.
    """
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    builder = _clean(config["builder"])
    name = _clean(config["name"])

    fichiers = {}

    variables = _variable_blocks(config.get("variables"))
    if variables:
        fichiers["variables.pkr.hcl"] = "\n\n".join(variables) + "\n"

    fichiers["sources.pkr.hcl"] = "\n\n".join([
        _plugin_block(_required_plugins(builder, config)),
        *[_datasource_block(ds) for ds in config.get("datasources") or []],
        _source_block(builder, name, config.get("args") or {}),
    ]) + "\n"

    fichiers["build.pkr.hcl"] = _build_block(builder, name, config) + "\n"

    return fichiers


def generate_combined(config):
    return generate_packer_template(config)


def write_files(config, output_dir):
    """Genere le fichier combine et l'ecrit dans output_dir. Retourne les chemins."""
    content = generate_packer_template(config)
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, OUTPUT_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return [path]


def write_split_files(config, output_dir):
    """Genere les fichiers separes (variables/sources/build) dans output_dir."""
    fichiers = generate_split_files(config)
    os.makedirs(output_dir, exist_ok=True)
    chemins = []
    for nom, contenu in fichiers.items():
        path = os.path.join(output_dir, nom)
        with open(path, "w", encoding="utf-8") as f:
            f.write(contenu)
        chemins.append(path)
    return chemins


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
        "datasources": [
            {
                "type": "amazon-ami",
                "name": "ubuntu",
                "args": {
                    "filters": {
                        "name": "ubuntu/images/*ubuntu-jammy-22.04-amd64-server-*",
                        "root-device-type": "ebs",
                        "virtualization-type": "hvm",
                    },
                    "owners": ["099720109477"],
                    "most_recent": True,
                },
            },
        ],
        "args": {
            "region": "eu-west-1",
            "source_ami": "=data.amazon-ami.ubuntu.id",
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
            {"type": "ansible", "playbook_file": "playbooks/harden.yml", "user": "ubuntu"},
        ],
        "post_processors": [],
    },
    "windows-server-ami": {
        "builder": "amazon-ebs",
        "name": "windows-webserver-ami",
        "args": {
            "region": "eu-west-1",
            "source_ami": "ami-0c2b8ca1dad447f8a",
            "instance_type": "t3.medium",
            "ssh_username": "Administrator",
            "ami_name": "windows-webserver-{{timestamp}}",
            "communicator": "winrm",
            "winrm_username": "Administrator",
            "winrm_insecure": True,
            "winrm_use_ssl": True,
            "user_data_file": "scripts/bootstrap-winrm.txt",
        },
        "provisioners": [
            {"type": "powershell-inline", "inline": [
                "Install-WindowsFeature -Name Web-Server -IncludeManagementTools",
                "Write-Output 'IIS installe'",
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
        "hcp_registry": {
            "bucket_name": "mon-org-app",
            "description": "Image applicative Python, publiee depuis OpsForge.",
            "bucket_labels": {"team": "platform"},
        },
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
