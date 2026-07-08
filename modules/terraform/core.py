"""
modules/terraform/core.py
-------------------------
Coeur du module Terraform d'OpsForge (v0 — a enrichir).

Genere un fichier `main.tf` a partir d'une config simple :
  - un provider (aws, google, azurerm, docker, local...)
  - une liste de ressources { "type", "name", "args": {...} }

Le rendu HCL est generique : n'importe quel type de ressource et n'importe
quels arguments sont acceptes, ce qui rend le module facile a etendre plus
tard (presets, validation par provider, modules, variables, outputs...).
"""

# Providers connus : nom Terraform -> (source registry, config par defaut du bloc provider)
SUPPORTED_PROVIDERS = {
    "aws": {
        "source": "hashicorp/aws",
        "defaults": {"region": "eu-west-1"},
    },
    "google": {
        "source": "hashicorp/google",
        "defaults": {"project": "mon-projet", "region": "europe-west1"},
    },
    "azurerm": {
        "source": "hashicorp/azurerm",
        "defaults": {"features": {}},
    },
    "docker": {
        "source": "kreuzwerker/docker",
        "defaults": {},
    },
    "local": {
        "source": "hashicorp/local",
        "defaults": {},
    },
}


def _indent(text, spaces):
    pad = " " * spaces
    return "\n".join((pad + ligne if ligne else ligne) for ligne in text.split("\n"))


def _hcl_value(value):
    """Rend une valeur Python en HCL (chaine, booleen, nombre, liste, bloc imbrique)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # Reference brute (var.x, aws_instance.web.id, "${...}") : pas de guillemets
        # si l'utilisateur a explicitement prefixe par '=' (echappatoire simple).
        if value.startswith("="):
            return value[1:]
        echappe = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{echappe}"'
    if isinstance(value, list):
        elements = ", ".join(_hcl_value(v) for v in value)
        return f"[{elements}]"
    if isinstance(value, dict):
        return "{\n" + _indent(_hcl_body(value), 2) + "\n}"
    if value is None:
        return "null"
    return f'"{value}"'


def _hcl_body(args):
    """Rend un dict d'arguments en corps de bloc HCL (lignes 'cle = valeur')."""
    lignes = []
    for cle, valeur in args.items():
        lignes.append(f"{cle} = {_hcl_value(valeur)}")
    return "\n".join(lignes)


def _render_block(kind, labels, args):
    """Rend un bloc HCL : <kind> "label1" "label2" { ... }."""
    entete = kind
    for label in labels:
        entete += f' "{label}"'
    corps = _hcl_body(args)
    if corps:
        return f"{entete} {{\n" + _indent(corps, 2) + "\n}"
    return f"{entete} {{}}"


def valider_config(config):
    """Retourne (erreurs, avertissements) sans lever d'exception."""
    erreurs = []
    avertissements = []

    provider = (config or {}).get("provider")
    if not provider:
        erreurs.append("Aucun provider specifie.")
    elif provider not in SUPPORTED_PROVIDERS:
        avertissements.append(
            f"Provider '{provider}' non reference dans le catalogue "
            f"({', '.join(SUPPORTED_PROVIDERS)}) : bloc genere quand meme."
        )

    resources = (config or {}).get("resources") or []
    for i, res in enumerate(resources):
        if not res.get("type"):
            erreurs.append(f"Ressource #{i + 1} : champ 'type' manquant.")
        if not res.get("name"):
            erreurs.append(f"Ressource #{i + 1} : champ 'name' manquant.")

    return erreurs, avertissements


def generate_terraform(config):
    """Construit le contenu d'un main.tf a partir de la config.

    Leve ValueError si la config est invalide (provider/ressources).
    """
    config = config or {}
    erreurs, _ = valider_config(config)
    if erreurs:
        raise ValueError(" ; ".join(erreurs))

    provider = config["provider"]
    infos = SUPPORTED_PROVIDERS.get(provider, {"source": f"hashicorp/{provider}", "defaults": {}})

    # Bloc terraform { required_providers { ... } }
    required = {
        provider: {
            "source": f"={infos['source']}",  # source sans re-guillemets via l'echappatoire '='
        }
    }
    # petit rendu manuel pour la version epinglee optionnelle
    required_body = (
        f'{provider} = {{\n'
        f'  source  = "{infos["source"]}"\n'
        f'  version = "~> 5.0"\n'
        f'}}'
    )
    bloc_terraform = (
        "terraform {\n"
        "  required_providers {\n"
        + _indent(required_body, 4) + "\n"
        "  }\n"
        "}"
    )

    # Bloc provider
    provider_args = dict(infos.get("defaults", {}))
    provider_args.update(config.get("provider_config") or {})
    bloc_provider = _render_block("provider", [provider], provider_args)

    # Blocs resource
    blocs_res = []
    for res in config.get("resources") or []:
        blocs_res.append(
            _render_block("resource", [res["type"], res["name"]], res.get("args") or {})
        )

    # Blocs variable / output optionnels (bruts, deja au format dict)
    blocs_extra = []
    for nom, corps in (config.get("variables") or {}).items():
        blocs_extra.append(_render_block("variable", [nom], corps or {}))
    for nom, corps in (config.get("outputs") or {}).items():
        blocs_extra.append(_render_block("output", [nom], corps or {}))

    parties = [bloc_terraform, bloc_provider] + blocs_res + blocs_extra
    entete = "# Genere par OpsForge (module Terraform)\n\n"
    return entete + "\n\n".join(parties) + "\n"


def write_terraform(config, output_path):
    contenu = generate_terraform(config)
    import os
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(contenu)
    return output_path
