"""Tests du coeur du module Monitoring d'OpsForge."""

import pytest
import yaml

from modules.monitoring.core import (
    generate_files,
    generate_combined,
    validate_config,
    list_presets,
    get_preset,
    list_rules,
    SUPPORTED_MODES,
    RULES_CATALOG,
    PRESETS,
)


def _yaml_body(text):
    """Parse le YAML en ignorant les lignes de commentaire d'entete."""
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    return yaml.safe_load(body)


def _prom_cfg(**overrides):
    cfg = {
        "mode": "prometheus",
        "jobs": [{"job_name": "node", "targets": ["localhost:9100"]}],
    }
    cfg.update(overrides)
    return cfg


def _alerts_cfg(**overrides):
    cfg = {
        "mode": "alerts",
        "rules": ["instance_down", "high_cpu"],
    }
    cfg.update(overrides)
    return cfg


def _grafana_cfg(**overrides):
    cfg = {
        "mode": "grafana",
        "datasources": [{"name": "Prometheus", "type": "prometheus", "url": "http://localhost:9090"}],
    }
    cfg.update(overrides)
    return cfg


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def test_mode_invalide_rejete():
    errors = validate_config({"mode": "zabbix"})
    assert any("Mode non supporte" in e for e in errors)


def test_prometheus_sans_job_rejete():
    errors = validate_config(_prom_cfg(jobs=[]))
    assert any("job de scrape" in e for e in errors)


def test_prometheus_job_sans_target_rejete():
    errors = validate_config(_prom_cfg(jobs=[{"job_name": "node", "targets": []}]))
    assert any("cible" in e for e in errors)


def test_prometheus_target_invalide_rejete():
    errors = validate_config(_prom_cfg(jobs=[{"job_name": "node", "targets": ["pas-de-port"]}]))
    assert any("invalide" in e for e in errors)


def test_prometheus_interval_invalide_rejete():
    errors = validate_config(_prom_cfg(scrape_interval="15secondes"))
    assert any("Duree invalide" in e for e in errors)


def test_alerts_sans_regle_rejete():
    errors = validate_config(_alerts_cfg(rules=[]))
    assert any("au moins une regle" in e.lower() for e in errors)


def test_alerts_regle_inconnue_rejete():
    errors = validate_config(_alerts_cfg(rules=["explose_tout"]))
    assert any("inconnue" in e for e in errors)


def test_alerts_seuil_hors_bornes_rejete():
    errors = validate_config(_alerts_cfg(cpu_threshold=150))
    assert any("Seuil invalide" in e for e in errors)


def test_grafana_sans_datasource_rejete():
    errors = validate_config(_grafana_cfg(datasources=[]))
    assert any("datasource" in e for e in errors)


def test_grafana_datasource_sans_url_rejete():
    errors = validate_config(_grafana_cfg(datasources=[{"name": "P", "type": "prometheus", "url": ""}]))
    assert any("URL" in e for e in errors)


def test_grafana_type_inconnu_rejete():
    errors = validate_config(
        _grafana_cfg(datasources=[{"name": "X", "type": "mysql-bidon", "url": "http://x"}])
    )
    assert any("non reconnu" in e for e in errors)


def test_configs_valides_ne_levent_aucune_erreur():
    assert validate_config(_prom_cfg()) == []
    assert validate_config(_alerts_cfg()) == []
    assert validate_config(_grafana_cfg()) == []


# --------------------------------------------------------------------------
# Generation : Prometheus
# --------------------------------------------------------------------------

def test_prometheus_produit_prometheus_yml():
    files = generate_files(_prom_cfg())
    assert list(files.keys()) == ["prometheus.yml"]


def test_prometheus_yaml_valide_et_structure():
    text = generate_files(_prom_cfg())["prometheus.yml"]
    data = _yaml_body(text)
    assert data["global"]["scrape_interval"] == "15s"
    assert data["scrape_configs"][0]["job_name"] == "node"
    assert data["scrape_configs"][0]["static_configs"][0]["targets"] == ["localhost:9100"]


def test_prometheus_alertmanager_et_rule_files():
    text = generate_files(_prom_cfg(alertmanager=True, rule_files=True))["prometheus.yml"]
    data = _yaml_body(text)
    assert "alerting" in data
    assert data["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"] == ["localhost:9093"]
    assert data["rule_files"] == ["alert.rules.yml"]


def test_prometheus_sans_options_omet_alerting():
    data = _yaml_body(generate_files(_prom_cfg())["prometheus.yml"])
    assert "alerting" not in data
    assert "rule_files" not in data


def test_prometheus_multi_jobs():
    cfg = _prom_cfg(jobs=[
        {"job_name": "prometheus", "targets": ["localhost:9090"]},
        {"job_name": "node", "targets": ["localhost:9100", "10.0.0.5:9100"]},
    ])
    data = _yaml_body(generate_files(cfg)["prometheus.yml"])
    assert len(data["scrape_configs"]) == 2
    assert data["scrape_configs"][1]["static_configs"][0]["targets"] == ["localhost:9100", "10.0.0.5:9100"]


# --------------------------------------------------------------------------
# Generation : Alertes
# --------------------------------------------------------------------------

def test_alerts_produit_alert_rules_yml():
    files = generate_files(_alerts_cfg())
    assert list(files.keys()) == ["alert.rules.yml"]


def test_alerts_yaml_valide_et_regles_selectionnees():
    data = _yaml_body(generate_files(_alerts_cfg(rules=["instance_down"]))["alert.rules.yml"])
    rules = data["groups"][0]["rules"]
    assert len(rules) == 1
    assert rules[0]["alert"] == "InstanceDown"
    assert rules[0]["expr"] == "up == 0"
    assert rules[0]["labels"]["severity"] == "critical"


def test_alerts_seuils_injectes_dans_expr():
    text = generate_files(_alerts_cfg(rules=["high_cpu"], cpu_threshold=70))["alert.rules.yml"]
    assert "> 70" in text
    assert "<<cpu>>" not in text  # la sentinelle a bien ete remplacee


def test_alerts_expr_promql_preserve_les_accolades():
    # Regression : str.format() aurait casse sur {mode="idle"}.
    data = _yaml_body(generate_files(_alerts_cfg(rules=["high_cpu"]))["alert.rules.yml"])
    assert 'node_cpu_seconds_total{mode="idle"}' in data["groups"][0]["rules"][0]["expr"]


def test_alerts_nom_de_groupe_personnalise():
    data = _yaml_body(generate_files(_alerts_cfg(group_name="prod"))["alert.rules.yml"])
    assert data["groups"][0]["name"] == "prod"


# --------------------------------------------------------------------------
# Generation : Grafana
# --------------------------------------------------------------------------

def test_grafana_produit_datasource_yml():
    files = generate_files(_grafana_cfg())
    assert list(files.keys()) == ["datasource.yml"]


def test_grafana_yaml_valide_et_apiversion():
    data = _yaml_body(generate_files(_grafana_cfg())["datasource.yml"])
    assert data["apiVersion"] == 1
    assert data["datasources"][0]["name"] == "Prometheus"
    assert data["datasources"][0]["access"] == "proxy"


def test_grafana_is_default_present_seulement_si_demande():
    cfg = _grafana_cfg(datasources=[
        {"name": "Prometheus", "type": "prometheus", "url": "http://localhost:9090", "is_default": True},
        {"name": "Loki", "type": "loki", "url": "http://localhost:3100"},
    ])
    data = _yaml_body(generate_files(cfg)["datasource.yml"])
    assert data["datasources"][0].get("isDefault") is True
    assert "isDefault" not in data["datasources"][1]


# --------------------------------------------------------------------------
# Combine + config invalide
# --------------------------------------------------------------------------

def test_combined_retourne_le_contenu():
    combined = generate_combined(_prom_cfg())
    assert "scrape_configs" in combined


def test_generate_files_leve_valueerror_si_invalide():
    with pytest.raises(ValueError):
        generate_files({"mode": "prometheus", "jobs": []})


# --------------------------------------------------------------------------
# Catalogue + presets
# --------------------------------------------------------------------------

def test_list_rules_retourne_le_catalogue():
    keys = {r["key"] for r in list_rules()}
    assert keys == set(RULES_CATALOG.keys())


def test_tous_les_presets_sont_valides():
    for name in list_presets():
        cfg = get_preset(name)
        assert validate_config(cfg) == []


def test_get_preset_inconnu_leve_valueerror():
    with pytest.raises(ValueError):
        get_preset("preset-qui-n-existe-pas")


def test_get_preset_retourne_une_copie_independante():
    preset_a = get_preset("prometheus-node")
    preset_a["jobs"].append({"job_name": "x", "targets": ["y:1"]})
    preset_b = get_preset("prometheus-node")
    assert len(preset_b["jobs"]) == 2


def test_presets_couvrent_les_trois_modes():
    modes_couverts = {PRESETS[name]["mode"] for name in list_presets()}
    assert modes_couverts == set(SUPPORTED_MODES)
