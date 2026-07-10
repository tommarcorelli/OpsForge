"""
modules/k8s/core.py
-------------------
Cœur du module Kubernetes/Helm d'OpsForge.

Deux modes de generation a partir d'une meme config :
  - generate_manifests(config)   -> dict {fichier: contenu} de manifests bruts
                                    (Deployment + Service + Ingress/Namespace optionnels),
                                    YAML valide PAR CONSTRUCTION (dicts -> yaml.dump)
  - generate_helm_chart(config)  -> dict {fichier: contenu} d'un squelette de chart
                                    Helm (Chart.yaml + values.yaml generes, templates
                                    Go statiques charges depuis templates/helm/)

Fonctions cles :
  - valider_config(config)             -> (erreurs, avertissements)
  - generate_manifests_combined(config)-> str : manifests joints par '---'
                                          (pret pour `kubectl apply -f`)
  - write_manifests / write_helm_chart -> ecriture sur disque

Config attendue (seuls name et image sont obligatoires) :
    {
        "name": "mon-app",                  # nom DNS-1123 (minuscules, chiffres, '-')
        "image": "monuser/mon-app:1.0.0",
        "replicas": 2,
        "container_port": 8080,
        "service_type": "ClusterIP",        # ClusterIP | NodePort | LoadBalancer
        "service_port": 80,
        "namespace": "mon-ns",              # optionnel
        "env": {"LOG_LEVEL": "info"},       # optionnel
        "resources": {                      # optionnel (defauts raisonnables)
            "cpu_request": "100m", "mem_request": "128Mi",
            "cpu_limit": "500m",  "mem_limit": "256Mi",
        },
        "probe_path": "/health",            # optionnel -> liveness + readiness HTTP
        "ingress": {                        # optionnel
            "host": "app.example.com",
            "path": "/",
            "class": "nginx",
            "tls": False,
        },
    }
"""

import os
import re

import yaml

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

SERVICE_TYPES = ["ClusterIP", "NodePort", "LoadBalancer"]

DEFAULT_RESOURCES = {
    "cpu_request": "100m",
    "mem_request": "128Mi",
    "cpu_limit": "500m",
    "mem_limit": "256Mi",
}

# Nom DNS-1123 (label) : impose par Kubernetes pour les noms d'objets.
_DNS1123_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def valider_config(config):
    """Retourne (erreurs, avertissements) pour la config fournie."""
    erreurs = []
    avertissements = []

    name = (config.get("name") or "").strip()
    if not name:
        erreurs.append("Le champ 'name' est obligatoire.")
    elif len(name) > 63 or not _DNS1123_RE.match(name):
        erreurs.append(
            f"Nom '{name}' invalide : minuscules, chiffres et '-' uniquement "
            "(max 63 caracteres, doit commencer et finir par un alphanumerique)."
        )

    image = (config.get("image") or "").strip()
    if not image:
        erreurs.append("Le champ 'image' est obligatoire (ex: monuser/mon-app:1.0.0).")
    elif ":" not in image.split("/")[-1]:
        avertissements.append(
            f"L'image '{image}' n'a pas de tag explicite : Kubernetes utilisera "
            "':latest', ce qui rend les deploiements non reproductibles."
        )

    replicas = config.get("replicas", 2)
    if not isinstance(replicas, int) or replicas < 1:
        erreurs.append("'replicas' doit etre un entier >= 1.")

    for champ in ("container_port", "service_port"):
        port = config.get(champ)
        if port is not None and (not isinstance(port, int) or not (1 <= port <= 65535)):
            erreurs.append(f"'{champ}' doit etre un entier entre 1 et 65535.")

    service_type = config.get("service_type", "ClusterIP")
    if service_type not in SERVICE_TYPES:
        erreurs.append(
            f"Type de service '{service_type}' inconnu. "
            f"Choix possibles : {', '.join(SERVICE_TYPES)}."
        )

    namespace = (config.get("namespace") or "").strip()
    if namespace and (len(namespace) > 63 or not _DNS1123_RE.match(namespace)):
        erreurs.append(f"Namespace '{namespace}' invalide (memes regles que le nom).")

    ingress = config.get("ingress")
    if ingress:
        host = (ingress.get("host") or "").strip()
        if not host:
            erreurs.append("Ingress active mais sans 'host' (ex: app.example.com).")
        if ingress.get("tls") and service_type == "LoadBalancer":
            avertissements.append(
                "TLS via Ingress + Service LoadBalancer : verifie que c'est voulu, "
                "en general on expose l'un OU l'autre."
            )

    probe_path = config.get("probe_path")
    if probe_path and not str(probe_path).startswith("/"):
        erreurs.append("'probe_path' doit commencer par '/' (ex: /health).")

    return erreurs, avertissements


def _valider_ou_lever(config):
    erreurs, _ = valider_config(config)
    if erreurs:
        raise ValueError(" ".join(erreurs))


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _labels(name):
    return {"app.kubernetes.io/name": name, "app.kubernetes.io/managed-by": "opsforge"}


def _resources_block(config):
    res = {**DEFAULT_RESOURCES, **(config.get("resources") or {})}
    return {
        "requests": {"cpu": res["cpu_request"], "memory": res["mem_request"]},
        "limits": {"cpu": res["cpu_limit"], "memory": res["mem_limit"]},
    }


def _dump(obj, header=None):
    """Serialise un dict en YAML lisible (ordre des cles preserve)."""
    text = yaml.dump(obj, sort_keys=False, default_flow_style=False, allow_unicode=True)
    if header:
        return f"# {header}\n{text}"
    return text


# ---------------------------------------------------------------------------
# Mode 1 : manifests bruts
# ---------------------------------------------------------------------------

def generate_deployment(config):
    """Construit le manifest Deployment (dict Python)."""
    name = config["name"].strip()
    container_port = config.get("container_port", 8080)

    container = {
        "name": name,
        "image": config["image"].strip(),
        "ports": [{"containerPort": container_port}],
        "resources": _resources_block(config),
    }

    env = config.get("env") or {}
    if env:
        container["env"] = [{"name": k, "value": str(v)} for k, v in env.items()]

    probe_path = config.get("probe_path")
    if probe_path:
        container["livenessProbe"] = {
            "httpGet": {"path": probe_path, "port": container_port},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
        }
        container["readinessProbe"] = {
            "httpGet": {"path": probe_path, "port": container_port},
            "initialDelaySeconds": 5,
            "periodSeconds": 5,
        }

    metadata = {"name": name, "labels": _labels(name)}
    namespace = (config.get("namespace") or "").strip()
    if namespace:
        metadata["namespace"] = namespace

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": metadata,
        "spec": {
            "replicas": config.get("replicas", 2),
            "selector": {"matchLabels": {"app.kubernetes.io/name": name}},
            "template": {
                "metadata": {"labels": _labels(name)},
                "spec": {"containers": [container]},
            },
        },
    }


def generate_service(config):
    """Construit le manifest Service (dict Python)."""
    name = config["name"].strip()
    metadata = {"name": name, "labels": _labels(name)}
    namespace = (config.get("namespace") or "").strip()
    if namespace:
        metadata["namespace"] = namespace

    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": metadata,
        "spec": {
            "type": config.get("service_type", "ClusterIP"),
            "selector": {"app.kubernetes.io/name": name},
            "ports": [{
                "port": config.get("service_port", 80),
                "targetPort": config.get("container_port", 8080),
                "protocol": "TCP",
            }],
        },
    }


def generate_ingress(config):
    """Construit le manifest Ingress (dict Python), ou None si non demande."""
    ingress_cfg = config.get("ingress")
    if not ingress_cfg:
        return None

    name = config["name"].strip()
    host = ingress_cfg["host"].strip()
    path = ingress_cfg.get("path", "/") or "/"

    metadata = {"name": name, "labels": _labels(name)}
    namespace = (config.get("namespace") or "").strip()
    if namespace:
        metadata["namespace"] = namespace

    ingress_class = (ingress_cfg.get("class") or "").strip()
    spec = {
        "rules": [{
            "host": host,
            "http": {
                "paths": [{
                    "path": path,
                    "pathType": "Prefix",
                    "backend": {
                        "service": {
                            "name": name,
                            "port": {"number": config.get("service_port", 80)},
                        }
                    },
                }]
            },
        }]
    }
    if ingress_class:
        spec["ingressClassName"] = ingress_class
    if ingress_cfg.get("tls"):
        spec["tls"] = [{"hosts": [host], "secretName": f"{name}-tls"}]

    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": metadata,
        "spec": spec,
    }


def generate_namespace(config):
    """Construit le manifest Namespace (dict Python), ou None si non defini."""
    namespace = (config.get("namespace") or "").strip()
    if not namespace:
        return None
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {"name": namespace},
    }


def generate_manifests(config):
    """
    Genere tous les manifests bruts.

    Returns:
        dict {nom_de_fichier: contenu_yaml} — les cles sont prefixees par un
        numero d'ordre d'application (namespace d'abord, ingress en dernier).
    """
    _valider_ou_lever(config)

    files = {}

    ns = generate_namespace(config)
    if ns:
        files["00-namespace.yaml"] = _dump(ns, "Genere par OpsForge — namespace")

    files["10-deployment.yaml"] = _dump(
        generate_deployment(config), "Genere par OpsForge — deployment"
    )
    files["20-service.yaml"] = _dump(generate_service(config), "Genere par OpsForge — service")

    ing = generate_ingress(config)
    if ing:
        files["30-ingress.yaml"] = _dump(ing, "Genere par OpsForge — ingress")

    return files


def generate_manifests_combined(config):
    """Manifests joints par '---' : un seul fichier pret pour `kubectl apply -f`."""
    files = generate_manifests(config)
    return "---\n".join(files[k] for k in sorted(files))


# ---------------------------------------------------------------------------
# Mode 2 : squelette de chart Helm
# ---------------------------------------------------------------------------

def _load_helm_template(filename):
    path = os.path.join(TEMPLATES_DIR, "helm", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _app_version_from_image(image):
    """Extrait le tag de l'image pour servir d'appVersion ('latest' sinon)."""
    last = image.strip().split("/")[-1]
    return last.split(":", 1)[1] if ":" in last else "latest"


def generate_helm_chart(config):
    """
    Genere un squelette de chart Helm complet.

    Returns:
        dict {chemin_relatif: contenu} — Chart.yaml et values.yaml sont
        construits depuis la config ; les templates Go (deployment, service,
        ingress, _helpers.tpl) sont statiques et pilotes par values.yaml.
    """
    _valider_ou_lever(config)

    name = config["name"].strip()
    image = config["image"].strip()

    # image "repo:tag" -> repository / tag separes (convention Helm)
    last = image.split("/")[-1]
    if ":" in last:
        repository = image.rsplit(":", 1)[0]
        tag = image.rsplit(":", 1)[1]
    else:
        repository, tag = image, "latest"

    chart = {
        "apiVersion": "v2",
        "name": name,
        "description": f"Chart Helm pour {name} — genere par OpsForge",
        "type": "application",
        "version": "0.1.0",
        "appVersion": _app_version_from_image(image),
    }

    ingress_cfg = config.get("ingress") or {}
    values = {
        "replicaCount": config.get("replicas", 2),
        "image": {
            "repository": repository,
            "tag": tag,
            "pullPolicy": "IfNotPresent",
        },
        "containerPort": config.get("container_port", 8080),
        "service": {
            "type": config.get("service_type", "ClusterIP"),
            "port": config.get("service_port", 80),
        },
        "env": {str(k): str(v) for k, v in (config.get("env") or {}).items()},
        "probePath": config.get("probe_path") or "",
        "resources": _resources_block(config),
        "ingress": {
            "enabled": bool(ingress_cfg),
            "className": ingress_cfg.get("class", "") if ingress_cfg else "",
            "host": ingress_cfg.get("host", "") if ingress_cfg else "",
            "path": (ingress_cfg.get("path") or "/") if ingress_cfg else "/",
            "tls": bool(ingress_cfg.get("tls")) if ingress_cfg else False,
        },
    }

    return {
        "Chart.yaml": _dump(chart, f"Chart {name} — genere par OpsForge"),
        "values.yaml": _dump(values, "Valeurs par defaut — genere par OpsForge"),
        ".helmignore": _load_helm_template("helmignore"),
        "templates/_helpers.tpl": _load_helm_template("_helpers.tpl"),
        "templates/deployment.yaml": _load_helm_template("deployment.yaml"),
        "templates/service.yaml": _load_helm_template("service.yaml"),
        "templates/ingress.yaml": _load_helm_template("ingress.yaml"),
    }


# ---------------------------------------------------------------------------
# Ecriture sur disque
# ---------------------------------------------------------------------------

def _write_files(files, output_dir):
    written = []
    for rel_path, content in files.items():
        full_path = os.path.join(output_dir, rel_path)
        os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(full_path)
    return written


def write_manifests(config, output_dir):
    """Ecrit les manifests bruts dans un dossier. Retourne les chemins ecrits."""
    return _write_files(generate_manifests(config), output_dir)


def write_helm_chart(config, output_dir):
    """Ecrit le chart Helm dans un dossier. Retourne les chemins ecrits."""
    return _write_files(generate_helm_chart(config), output_dir)
