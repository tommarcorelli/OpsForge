"""Tests du cœur du module Kubernetes/Helm d'OpsForge."""

import yaml
import pytest

from modules.k8s.core import (
    generate_manifests,
    generate_manifests_combined,
    generate_helm_chart,
    write_manifests,
    write_helm_chart,
    valider_config,
    SERVICE_TYPES,
)


def _config(**overrides):
    base = {"name": "mon-app", "image": "monuser/mon-app:1.2.3"}
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def test_config_minimale_valide():
    erreurs, avertissements = valider_config(_config())
    assert erreurs == []
    assert avertissements == []


def test_nom_manquant():
    erreurs, _ = valider_config({"image": "x:1"})
    assert any("'name'" in e for e in erreurs)


@pytest.mark.parametrize("bad_name", ["Mon-App", "app_1", "-app", "app-", "a" * 64, "app.web"])
def test_nom_non_dns1123_rejete(bad_name):
    erreurs, _ = valider_config(_config(name=bad_name))
    assert erreurs, f"'{bad_name}' aurait du etre rejete"


def test_image_manquante():
    erreurs, _ = valider_config({"name": "app"})
    assert any("'image'" in e for e in erreurs)


def test_image_sans_tag_avertit():
    _, avertissements = valider_config(_config(image="monuser/mon-app"))
    assert any("latest" in a for a in avertissements)


def test_replicas_invalide():
    erreurs, _ = valider_config(_config(replicas=0))
    assert any("replicas" in e for e in erreurs)


def test_port_hors_limites():
    erreurs, _ = valider_config(_config(container_port=70000))
    assert any("container_port" in e for e in erreurs)


def test_service_type_inconnu():
    erreurs, _ = valider_config(_config(service_type="ExternalName"))
    assert any("ExternalName" in e for e in erreurs)


def test_ingress_sans_host():
    erreurs, _ = valider_config(_config(ingress={"path": "/"}))
    assert any("host" in e for e in erreurs)


def test_probe_path_sans_slash():
    erreurs, _ = valider_config(_config(probe_path="health"))
    assert any("probe_path" in e for e in erreurs)


def test_generation_config_invalide_leve_value_error():
    with pytest.raises(ValueError):
        generate_manifests(_config(name="Nom Invalide"))


# --------------------------------------------------------------------------
# Manifests : YAML valide et contenu attendu
# --------------------------------------------------------------------------

def test_manifests_minimaux():
    files = generate_manifests(_config())
    assert set(files) == {"10-deployment.yaml", "20-service.yaml"}
    for content in files.values():
        docs = list(yaml.safe_load_all(content))
        assert len(docs) == 1 and docs[0]


def test_manifests_complets_avec_namespace_et_ingress():
    files = generate_manifests(_config(
        namespace="prod",
        ingress={"host": "app.example.com", "path": "/", "class": "nginx", "tls": True},
    ))
    assert set(files) == {
        "00-namespace.yaml", "10-deployment.yaml", "20-service.yaml", "30-ingress.yaml"
    }


def test_deployment_contenu():
    files = generate_manifests(_config(replicas=5, container_port=9000,
                                       env={"LOG_LEVEL": "debug"}))
    dep = yaml.safe_load(files["10-deployment.yaml"])
    assert dep["kind"] == "Deployment"
    assert dep["spec"]["replicas"] == 5
    container = dep["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "monuser/mon-app:1.2.3"
    assert container["ports"][0]["containerPort"] == 9000
    assert {"name": "LOG_LEVEL", "value": "debug"} in container["env"]
    # resources par defaut toujours presentes
    assert container["resources"]["requests"]["cpu"] == "100m"
    assert container["resources"]["limits"]["memory"] == "256Mi"


def test_deployment_sans_probe_ni_env():
    files = generate_manifests(_config())
    container = yaml.safe_load(files["10-deployment.yaml"])["spec"]["template"]["spec"]["containers"][0]
    assert "livenessProbe" not in container
    assert "env" not in container


def test_probes_generees_sans_ancres_yaml():
    files = generate_manifests(_config(probe_path="/health"))
    raw = files["10-deployment.yaml"]
    assert "&id" not in raw and "*id" not in raw, "ancres YAML indesirables"
    container = yaml.safe_load(raw)["spec"]["template"]["spec"]["containers"][0]
    assert container["livenessProbe"]["httpGet"]["path"] == "/health"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health"
    assert container["livenessProbe"]["initialDelaySeconds"] == 10
    assert container["readinessProbe"]["initialDelaySeconds"] == 5


@pytest.mark.parametrize("service_type", SERVICE_TYPES)
def test_service_types(service_type):
    files = generate_manifests(_config(service_type=service_type))
    svc = yaml.safe_load(files["20-service.yaml"])
    assert svc["spec"]["type"] == service_type


def test_service_ports():
    files = generate_manifests(_config(service_port=443, container_port=8443))
    port = yaml.safe_load(files["20-service.yaml"])["spec"]["ports"][0]
    assert port["port"] == 443
    assert port["targetPort"] == 8443


def test_selector_coherent_entre_deployment_et_service():
    files = generate_manifests(_config())
    dep = yaml.safe_load(files["10-deployment.yaml"])
    svc = yaml.safe_load(files["20-service.yaml"])
    dep_labels = dep["spec"]["template"]["metadata"]["labels"]
    assert dep["spec"]["selector"]["matchLabels"].items() <= dep_labels.items()
    assert svc["spec"]["selector"].items() <= dep_labels.items()


def test_namespace_propage_sur_tous_les_objets():
    files = generate_manifests(_config(
        namespace="prod", ingress={"host": "app.example.com"}
    ))
    for fname in ("10-deployment.yaml", "20-service.yaml", "30-ingress.yaml"):
        doc = yaml.safe_load(files[fname])
        assert doc["metadata"]["namespace"] == "prod", fname
    ns = yaml.safe_load(files["00-namespace.yaml"])
    assert ns["kind"] == "Namespace" and ns["metadata"]["name"] == "prod"


def test_ingress_contenu_avec_tls_et_classe():
    files = generate_manifests(_config(
        ingress={"host": "app.example.com", "path": "/api", "class": "nginx", "tls": True}
    ))
    ing = yaml.safe_load(files["30-ingress.yaml"])
    assert ing["spec"]["ingressClassName"] == "nginx"
    rule = ing["spec"]["rules"][0]
    assert rule["host"] == "app.example.com"
    assert rule["http"]["paths"][0]["path"] == "/api"
    assert rule["http"]["paths"][0]["backend"]["service"]["name"] == "mon-app"
    assert ing["spec"]["tls"][0]["secretName"] == "mon-app-tls"


def test_ingress_sans_classe_ni_tls():
    files = generate_manifests(_config(ingress={"host": "app.example.com"}))
    ing = yaml.safe_load(files["30-ingress.yaml"])
    assert "ingressClassName" not in ing["spec"]
    assert "tls" not in ing["spec"]


def test_combined_multi_documents_dans_lordre():
    combined = generate_manifests_combined(_config(
        namespace="prod", ingress={"host": "app.example.com"}
    ))
    kinds = [d["kind"] for d in yaml.safe_load_all(combined)]
    assert kinds == ["Namespace", "Deployment", "Service", "Ingress"]


# --------------------------------------------------------------------------
# Chart Helm
# --------------------------------------------------------------------------

def test_helm_chart_fichiers_presents():
    files = generate_helm_chart(_config())
    assert set(files) == {
        "Chart.yaml", "values.yaml", ".helmignore",
        "templates/_helpers.tpl", "templates/deployment.yaml",
        "templates/service.yaml", "templates/ingress.yaml",
    }


def test_helm_chart_yaml_et_values_parsables():
    files = generate_helm_chart(_config(env={"TZ": "Europe/Paris"}))
    chart = yaml.safe_load(files["Chart.yaml"])
    values = yaml.safe_load(files["values.yaml"])
    assert chart["apiVersion"] == "v2"
    assert chart["name"] == "mon-app"
    assert chart["appVersion"] == "1.2.3"
    assert values["image"]["repository"] == "monuser/mon-app"
    assert values["image"]["tag"] == "1.2.3"
    assert values["env"] == {"TZ": "Europe/Paris"}


def test_helm_image_sans_tag_donne_latest():
    files = generate_helm_chart({"name": "app", "image": "nginx"})
    chart = yaml.safe_load(files["Chart.yaml"])
    values = yaml.safe_load(files["values.yaml"])
    assert chart["appVersion"] == "latest"
    assert values["image"]["repository"] == "nginx"
    assert values["image"]["tag"] == "latest"


def test_helm_image_registre_avec_port():
    """Un registre avec port (registry:5000/app:2.0) ne doit pas casser le split."""
    files = generate_helm_chart({"name": "app", "image": "registry.local:5000/team/app:2.0"})
    values = yaml.safe_load(files["values.yaml"])
    assert values["image"]["repository"] == "registry.local:5000/team/app"
    assert values["image"]["tag"] == "2.0"


def test_helm_ingress_enabled_selon_config():
    with_ing = generate_helm_chart(_config(ingress={"host": "app.example.com", "tls": True}))
    without_ing = generate_helm_chart(_config())
    assert yaml.safe_load(with_ing["values.yaml"])["ingress"]["enabled"] is True
    assert yaml.safe_load(with_ing["values.yaml"])["ingress"]["tls"] is True
    assert yaml.safe_load(without_ing["values.yaml"])["ingress"]["enabled"] is False


def test_helm_templates_references_coherentes_avec_values():
    """Chaque .Values.x utilise dans les templates doit exister dans values.yaml."""
    import re
    files = generate_helm_chart(_config())
    values = yaml.safe_load(files["values.yaml"])

    refs = set()
    for fname in ("templates/deployment.yaml", "templates/service.yaml",
                  "templates/ingress.yaml"):
        refs |= set(re.findall(r"\.Values\.([A-Za-z][\w.]*)", files[fname]))

    for ref in refs:
        node = values
        for part in ref.split("."):
            assert isinstance(node, dict) and part in node, \
                f".Values.{ref} reference dans un template mais absent de values.yaml"
            node = node[part]


def test_helm_templates_delimiteurs_go_equilibres():
    files = generate_helm_chart(_config())
    for fname, content in files.items():
        if fname.startswith("templates/"):
            assert content.count("{{") == content.count("}}"), f"delimiteurs Go desequilibres: {fname}"


# --------------------------------------------------------------------------
# Ecriture sur disque
# --------------------------------------------------------------------------

def test_write_manifests(tmp_path):
    written = write_manifests(_config(namespace="prod"), str(tmp_path))
    assert len(written) == 3
    assert (tmp_path / "10-deployment.yaml").is_file()
    assert (tmp_path / "00-namespace.yaml").is_file()


def test_write_helm_chart_arborescence(tmp_path):
    write_helm_chart(_config(), str(tmp_path / "mon-app"))
    assert (tmp_path / "mon-app" / "Chart.yaml").is_file()
    assert (tmp_path / "mon-app" / "templates" / "deployment.yaml").is_file()
    assert (tmp_path / "mon-app" / ".helmignore").is_file()
