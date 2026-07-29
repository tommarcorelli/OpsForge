"""
modules/gitops/core.py
------------------------
Coeur du module GitOps d'OpsForge — genere les manifests de deploiement
continu (CD) pour Kubernetes, sur le meme principe que modules/vault
(rendu YAML "a la main", indentation controlee, validation avant generation).

Deux outils geres :

  - **ArgoCD**  : un seul manifest `Application` (CRD `argoproj.io/v1alpha1`).
  - **FluxCD**  : deux/trois manifests (`GitRepository` + `Kustomization`,
                   ou `GitRepository` + `HelmRelease` pour les charts Helm
                   herberges dans le meme repo Git — evite d'avoir a gerer
                   un second type de source `HelmRepository`, et garde une
                   configuration symetrique entre les deux outils : un seul
                   `repo_url`/`path`/`revision` suffit dans tous les cas).

Trois types de source geres pour les deux outils (`source_type`) :
  - "raw"       : manifests Kubernetes bruts dans `path`.
  - "kustomize" : overlay Kustomize dans `path` (kustomization.yaml attendu).
  - "helm"      : chart Helm herberge dans `path` du meme repo Git.

Fonctions cles :
  - generate_argocd_application(config) -> contenu YAML de l'Application
  - generate_flux_manifests(config)     -> {nom_fichier: contenu YAML}
  - generate_files(config)              -> {nom_fichier: contenu} (dispatch selon config["tool"])
  - validate_config(config)             -> liste d'erreurs (vide si valide)
  - PRESETS / get_preset                -> configs pretes a l'emploi
"""

import copy
import os
import re

_DNS1123_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")

TOOLS = ("argocd", "flux")
SOURCE_TYPES = ("raw", "kustomize", "helm")


def _clean(value):
    return value.strip() if isinstance(value, str) else value


def _yaml_str(value):
    """Rend une chaine en litteral YAML, entre guillemets si necessaire
    (evite les soucis d'interpretation de valeurs ambigues comme des
    booleens/nombres/dates par le parseur YAML)."""
    s = str(value)
    needs_quotes = (
        s == ""
        or s.lower() in ("true", "false", "null", "yes", "no", "on", "off")
        or re.match(r"^[-+]?[0-9]", s)
        or any(c in s for c in ":#{}[],&*!|>'\"%@`")
    )
    if needs_quotes:
        return '"' + s.replace('"', '\\"') + '"'
    return s


def _yaml_scalar(value):
    """Rend une valeur Helm (values.yaml) en respectant son type natif :
    bool/int/float ne sont PAS entre guillemets (sinon Helm les recoit
    comme des chaines au lieu du type attendu par le chart), seules les
    chaines de caracteres passent par _yaml_str (qui les guillemete si
    ambigues)."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    return _yaml_str(value)


def _indent(text, spaces):
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in text.split("\n"))


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate_config(config):
    errors = []
    if not isinstance(config, dict):
        return ["La configuration doit etre un objet JSON."]

    tool = _clean(config.get("tool"))
    if not tool:
        errors.append("Le champ 'tool' est obligatoire.")
    elif tool not in TOOLS:
        errors.append(f"tool inconnu : '{tool}'. Disponibles : {', '.join(TOOLS)}.")

    app_name = _clean(config.get("app_name"))
    if not app_name:
        errors.append("Le champ 'app_name' est obligatoire.")
    elif len(app_name) > 63 or not _DNS1123_RE.match(app_name):
        errors.append(
            "app_name invalide : doit respecter le format DNS-1123 "
            "(minuscules, chiffres, tirets, 63 caracteres max)."
        )

    namespace = _clean(config.get("namespace")) or app_name
    if namespace and (len(namespace) > 63 or not _DNS1123_RE.match(namespace)):
        errors.append(
            "namespace invalide : doit respecter le format DNS-1123 "
            "(minuscules, chiffres, tirets, 63 caracteres max)."
        )

    if not _clean(config.get("repo_url")):
        errors.append("Le champ 'repo_url' est obligatoire (URL du depot Git).")

    source_type = _clean(config.get("source_type")) or "raw"
    if source_type not in SOURCE_TYPES:
        errors.append(
            f"source_type inconnu : '{source_type}'. Disponibles : {', '.join(SOURCE_TYPES)}."
        )

    if source_type == "helm" and not _clean(config.get("helm_chart_name")):
        # Requis uniquement cote Flux (HelmRelease.spec.chart.spec.chart) ;
        # ArgoCD detecte le chart via la presence de Chart.yaml dans 'path'
        # et n'en a pas besoin, mais on l'exige dans les deux cas pour
        # garder une config portable d'un outil a l'autre sans surprise.
        errors.append(
            "helm_chart_name est requis quand source_type='helm' "
            "(nom du chart, ex: le contenu du champ 'name' de Chart.yaml)."
        )

    return errors


# --------------------------------------------------------------------------
# ArgoCD — Application (manifest unique)
# --------------------------------------------------------------------------
def generate_argocd_application(config):
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    app_name = _clean(config["app_name"])
    namespace = _clean(config.get("namespace")) or app_name
    project = _clean(config.get("project")) or "default"
    repo_url = _clean(config["repo_url"])
    path = _clean(config.get("path")) or "."
    revision = _clean(config.get("revision")) or "main"
    dest_server = _clean(config.get("dest_server")) or "https://kubernetes.default.svc"
    source_type = _clean(config.get("source_type")) or "raw"

    auto_sync = config.get("auto_sync", True)
    self_heal = config.get("self_heal", True)
    prune = config.get("prune", True)
    create_namespace = config.get("create_namespace", True)
    retries = config.get("retries", 5)

    lignes = [
        "apiVersion: argoproj.io/v1alpha1",
        "kind: Application",
        "metadata:",
        f"  name: {app_name}",
        "  namespace: argocd",
        "  finalizers:",
        "    - resources-finalizer.argocd.argoproj.io",
        "spec:",
        f"  project: {project}",
        "  source:",
        f"    repoURL: {_yaml_str(repo_url)}",
        f"    targetRevision: {_yaml_str(revision)}",
        f"    path: {_yaml_str(path)}",
    ]

    if source_type == "helm":
        helm_chart_name = _clean(config.get("helm_chart_name"))
        lignes.append("    helm:")
        value_files = config.get("helm_value_files") or []
        if value_files:
            lignes.append("      valueFiles:")
            for vf in value_files:
                lignes.append(f"        - {_yaml_str(vf)}")
        inline_values = config.get("helm_values") or {}
        if inline_values:
            lignes.append("      values: |")
            for key, value in inline_values.items():
                lignes.append(f"        {key}: {_yaml_scalar(value)}")
        # ArgoCD detecte le chart via Chart.yaml dans 'path' ; on documente
        # tout de meme le nom attendu pour rester coherent avec Flux.
        lignes.append(f"      # chart attendu dans 'path' : {helm_chart_name}")

    lignes += [
        "  destination:",
        f"    server: {_yaml_str(dest_server)}",
        f"    namespace: {namespace}",
        "  syncPolicy:",
    ]

    if auto_sync:
        lignes.append("    automated:")
        lignes.append(f"      selfHeal: {str(bool(self_heal)).lower()}")
        lignes.append(f"      prune: {str(bool(prune)).lower()}")

    sync_options = []
    if create_namespace:
        sync_options.append("CreateNamespace=true")
    if source_type == "kustomize":
        sync_options.append("PrunePropagationPolicy=foreground")

    if sync_options:
        lignes.append("    syncOptions:")
        for opt in sync_options:
            lignes.append(f"      - {opt}")

    lignes += [
        "    retry:",
        f"      limit: {int(retries)}",
        "      backoff:",
        "        duration: 5s",
        "        factor: 2",
        "        maxDuration: 3m",
    ]

    return "\n".join(lignes) + "\n"


# --------------------------------------------------------------------------
# FluxCD — GitRepository + (Kustomization | HelmRelease)
# --------------------------------------------------------------------------
def _flux_git_repository(config):
    app_name = _clean(config["app_name"])
    namespace = _clean(config.get("namespace")) or app_name
    repo_url = _clean(config["repo_url"])
    revision = _clean(config.get("revision")) or "main"
    interval = _clean(config.get("interval")) or "5m"

    return "\n".join([
        "apiVersion: source.toolkit.fluxcd.io/v1",
        "kind: GitRepository",
        "metadata:",
        f"  name: {app_name}",
        f"  namespace: {namespace}",
        "spec:",
        f"  interval: {interval}",
        f"  url: {_yaml_str(repo_url)}",
        "  ref:",
        f"    branch: {_yaml_str(revision)}",
    ]) + "\n"


def _flux_kustomization(config):
    app_name = _clean(config["app_name"])
    namespace = _clean(config.get("namespace")) or app_name
    path = _clean(config.get("path")) or "."
    interval = _clean(config.get("interval")) or "5m"
    prune = config.get("prune", True)

    lignes = [
        "apiVersion: kustomize.toolkit.fluxcd.io/v1",
        "kind: Kustomization",
        "metadata:",
        f"  name: {app_name}",
        f"  namespace: {namespace}",
        "spec:",
        f"  interval: {interval}",
        f"  path: {_yaml_str(path)}",
        f"  prune: {str(bool(prune)).lower()}",
        "  sourceRef:",
        "    kind: GitRepository",
        f"    name: {app_name}",
        f"  targetNamespace: {namespace}",
    ]
    if config.get("create_namespace", True):
        lignes.insert(
            0,
            "# NOTE : contrairement a ArgoCD, la Kustomization Flux n'a pas\n"
            "# d'option \"createNamespace\" native. Inclus un manifest Namespace\n"
            f"# pour '{namespace}' dans le chemin '{path}' du depot, ou cree-la\n"
            "# manuellement avant la premiere synchronisation.",
        )
    return "\n".join(lignes) + "\n"


def _flux_helm_release(config):
    app_name = _clean(config["app_name"])
    namespace = _clean(config.get("namespace")) or app_name
    path = _clean(config.get("path")) or "."
    interval = _clean(config.get("interval")) or "5m"
    helm_chart_name = _clean(config.get("helm_chart_name"))

    lignes = [
        "apiVersion: helm.toolkit.fluxcd.io/v2",
        "kind: HelmRelease",
        "metadata:",
        f"  name: {app_name}",
        f"  namespace: {namespace}",
        "spec:",
        f"  interval: {interval}",
        "  chart:",
        "    spec:",
        f"      chart: {_yaml_str(path)}",
        "      sourceRef:",
        "        kind: GitRepository",
        f"        name: {app_name}",
        f"        namespace: {namespace}",
        f"  releaseName: {app_name}",
        f"  targetNamespace: {namespace}",
    ]

    value_files = config.get("helm_value_files") or []
    inline_values = config.get("helm_values") or {}
    if value_files or inline_values:
        lignes.append("  values:")
        for key, value in inline_values.items():
            lignes.append(f"    {key}: {_yaml_scalar(value)}")
        if value_files:
            lignes.append(f"  # fichiers de valeurs additionnels (chart : {helm_chart_name}) :")
            for vf in value_files:
                lignes.append(f"  #   - {vf}")

    lignes += [
        "  install:",
        "    createNamespace: " + str(bool(config.get("create_namespace", True))).lower(),
        "  upgrade:",
        "    remediation:",
        "      retries: 3",
    ]
    return "\n".join(lignes) + "\n"


def generate_flux_manifests(config):
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    source_type = _clean(config.get("source_type")) or "raw"
    fichiers = {"flux-gitrepository.yaml": _flux_git_repository(config)}

    if source_type == "helm":
        fichiers["flux-helmrelease.yaml"] = _flux_helm_release(config)
    else:
        fichiers["flux-kustomization.yaml"] = _flux_kustomization(config)

    return fichiers


# --------------------------------------------------------------------------
# API publique
# --------------------------------------------------------------------------
def generate_files(config):
    """Retourne {nom_fichier: contenu}, dispatch selon config['tool']."""
    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration invalide : " + " | ".join(errors))

    tool = _clean(config["tool"])
    if tool == "argocd":
        return {"argocd-application.yaml": generate_argocd_application(config)}
    return generate_flux_manifests(config)


def write_files(config, output_dir):
    fichiers = generate_files(config)
    chemins = []
    os.makedirs(output_dir, exist_ok=True)
    for nom, contenu in fichiers.items():
        path = os.path.join(output_dir, nom)
        with open(path, "w", encoding="utf-8") as f:
            f.write(contenu)
        chemins.append(path)
    return chemins


def list_tools():
    return list(TOOLS)


def list_source_types():
    return list(SOURCE_TYPES)


# --------------------------------------------------------------------------
# Presets prets a l'emploi
# --------------------------------------------------------------------------
PRESETS = {
    "argocd-raw-manifests": {
        "tool": "argocd",
        "app_name": "mon-app",
        "namespace": "mon-app",
        "repo_url": "https://github.com/monorg/mon-repo.git",
        "path": "k8s/overlays/prod",
        "revision": "main",
        "source_type": "raw",
        "project": "default",
        "auto_sync": True,
        "self_heal": True,
        "prune": True,
        "create_namespace": True,
    },
    "argocd-kustomize": {
        "tool": "argocd",
        "app_name": "mon-app",
        "namespace": "mon-app",
        "repo_url": "https://github.com/monorg/mon-repo.git",
        "path": "k8s/overlays/staging",
        "revision": "main",
        "source_type": "kustomize",
        "project": "default",
        "auto_sync": True,
        "self_heal": True,
        "prune": True,
        "create_namespace": True,
    },
    "argocd-helm-chart": {
        "tool": "argocd",
        "app_name": "mon-app",
        "namespace": "mon-app",
        "repo_url": "https://github.com/monorg/mon-repo.git",
        "path": "charts/mon-app",
        "revision": "main",
        "source_type": "helm",
        "helm_chart_name": "mon-app",
        "helm_value_files": ["values-prod.yaml"],
        "helm_values": {"replicaCount": 3},
        "project": "default",
        "auto_sync": True,
        "self_heal": True,
        "prune": True,
        "create_namespace": True,
    },
    "flux-raw-manifests": {
        "tool": "flux",
        "app_name": "mon-app",
        "namespace": "mon-app",
        "repo_url": "https://github.com/monorg/mon-repo.git",
        "path": "k8s/overlays/prod",
        "revision": "main",
        "source_type": "raw",
        "interval": "5m",
        "prune": True,
        "create_namespace": True,
    },
    "flux-helm-chart": {
        "tool": "flux",
        "app_name": "mon-app",
        "namespace": "mon-app",
        "repo_url": "https://github.com/monorg/mon-repo.git",
        "path": "charts/mon-app",
        "revision": "main",
        "source_type": "helm",
        "helm_chart_name": "mon-app",
        "helm_values": {"replicaCount": 3},
        "interval": "5m",
        "create_namespace": True,
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
