"""Tests du coeur du module systemd d'OpsForge."""

import pytest

from modules.systemd.core import (
    generate_units,
    generate_combined,
    validate_config,
    list_presets,
    get_preset,
    SUPPORTED_MODES,
    PRESETS,
)


def _service_cfg(**overrides):
    cfg = {
        "mode": "service",
        "name": "myapp",
        "exec_start": "/opt/myapp/bin/run",
    }
    cfg.update(overrides)
    return cfg


def _timer_cfg(**overrides):
    cfg = {
        "mode": "timer",
        "name": "backup",
        "exec_start": "/usr/local/bin/backup.sh",
        "on_calendar": "*-*-* 02:00:00",
    }
    cfg.update(overrides)
    return cfg


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def test_mode_invalide_rejete():
    errors = validate_config({"mode": "cronjob"})
    assert any("Mode non supporte" in e for e in errors)


def test_name_manquant_rejete():
    errors = validate_config(_service_cfg(name=""))
    assert any("nom de l'unite" in e.lower() or "name" in e for e in errors)


def test_name_avec_espace_rejete():
    errors = validate_config(_service_cfg(name="mon app"))
    assert any("invalide" in e for e in errors)


def test_exec_start_manquant_rejete():
    errors = validate_config(_service_cfg(exec_start=""))
    assert any("ExecStart" in e or "exec_start" in e for e in errors)


def test_service_type_invalide_rejete():
    errors = validate_config(_service_cfg(service_type="magic"))
    assert any("Type de service invalide" in e for e in errors)


def test_restart_invalide_rejete():
    errors = validate_config(_service_cfg(restart="parfois"))
    assert any("redemarrage invalide" in e for e in errors)


def test_restart_sec_negatif_rejete():
    errors = validate_config(_service_cfg(restart_sec=-2))
    assert any("RestartSec invalide" in e for e in errors)


def test_timer_sans_planification_rejete():
    cfg = _timer_cfg()
    cfg.pop("on_calendar")
    errors = validate_config(cfg)
    assert any("planification" in e for e in errors)


def test_config_valide_ne_leve_aucune_erreur():
    assert validate_config(_service_cfg()) == []
    assert validate_config(_timer_cfg()) == []


# --------------------------------------------------------------------------
# Generation : mode service
# --------------------------------------------------------------------------

def test_service_genere_un_seul_fichier():
    units = generate_units(_service_cfg())
    assert list(units.keys()) == ["myapp.service"]


def test_service_contient_sections_attendues():
    conf = generate_units(_service_cfg())["myapp.service"]
    assert "[Unit]" in conf
    assert "[Service]" in conf
    assert "[Install]" in conf
    assert "ExecStart=/opt/myapp/bin/run" in conf
    assert "WantedBy=multi-user.target" in conf


def test_service_type_par_defaut_simple():
    conf = generate_units(_service_cfg())["myapp.service"]
    assert "Type=simple" in conf


def test_service_user_group_workdir():
    conf = generate_units(
        _service_cfg(user="myapp", group="www", working_directory="/opt/myapp")
    )["myapp.service"]
    assert "User=myapp" in conf
    assert "Group=www" in conf
    assert "WorkingDirectory=/opt/myapp" in conf


def test_service_description_par_defaut_est_le_nom():
    conf = generate_units(_service_cfg())["myapp.service"]
    assert "Description=myapp" in conf


def test_service_after_par_defaut_network_target():
    conf = generate_units(_service_cfg())["myapp.service"]
    assert "After=network.target" in conf


def test_environment_variables_quotees():
    conf = generate_units(
        _service_cfg(environment=[{"key": "PORT", "value": "8000"}])
    )["myapp.service"]
    assert 'Environment="PORT=8000"' in conf


def test_environment_accepte_les_chaines():
    conf = generate_units(
        _service_cfg(environment=["LANG=fr_FR.UTF-8"])
    )["myapp.service"]
    assert 'Environment="LANG=fr_FR.UTF-8"' in conf


def test_environment_file_present():
    conf = generate_units(_service_cfg(environment_file="/etc/myapp/env"))["myapp.service"]
    assert "EnvironmentFile=/etc/myapp/env" in conf


# --------------------------------------------------------------------------
# Politique de redemarrage
# --------------------------------------------------------------------------

@pytest.mark.parametrize("policy", ["on-failure", "on-abnormal", "always"])
def test_restart_policy_presente(policy):
    conf = generate_units(_service_cfg(restart=policy, restart_sec=7))["myapp.service"]
    assert f"Restart={policy}" in conf
    assert "RestartSec=7" in conf


def test_restart_no_omet_la_directive():
    conf = generate_units(_service_cfg(restart="no"))["myapp.service"]
    assert "Restart=" not in conf


def test_oneshot_omet_restart():
    # Un oneshot n'est pas long-running : Restart n'a pas de sens.
    conf = generate_units(_service_cfg(service_type="oneshot", restart="always"))["myapp.service"]
    assert "Restart=" not in conf


# --------------------------------------------------------------------------
# Durcissement (sandboxing)
# --------------------------------------------------------------------------

def test_hardening_directives_actives():
    conf = generate_units(_service_cfg(
        no_new_privileges=True,
        private_tmp=True,
        protect_system=True,
        protect_home=True,
    ))["myapp.service"]
    assert "NoNewPrivileges=true" in conf
    assert "PrivateTmp=true" in conf
    assert "ProtectSystem=strict" in conf
    assert "ProtectHome=true" in conf


def test_hardening_absent_par_defaut():
    conf = generate_units(_service_cfg())["myapp.service"]
    assert "NoNewPrivileges" not in conf
    assert "PrivateTmp" not in conf


# --------------------------------------------------------------------------
# Generation : mode timer
# --------------------------------------------------------------------------

def test_timer_genere_deux_fichiers():
    units = generate_units(_timer_cfg())
    assert set(units.keys()) == {"backup.service", "backup.timer"}


def test_timer_service_est_oneshot_par_defaut():
    units = generate_units(_timer_cfg())
    assert "Type=oneshot" in units["backup.service"]


def test_timer_service_na_pas_de_install():
    # C'est le .timer qui active le service, pas l'inverse.
    units = generate_units(_timer_cfg())
    assert "[Install]" not in units["backup.service"]


def test_timer_contient_on_calendar_et_target():
    units = generate_units(_timer_cfg())
    timer = units["backup.timer"]
    assert "[Timer]" in timer
    assert "OnCalendar=*-*-* 02:00:00" in timer
    assert "WantedBy=timers.target" in timer
    assert "Unit=backup.service" in timer


def test_timer_persistent_optionnel():
    units = generate_units(_timer_cfg(persistent=True))
    assert "Persistent=true" in units["backup.timer"]
    units2 = generate_units(_timer_cfg())
    assert "Persistent=true" not in units2["backup.timer"]


# --------------------------------------------------------------------------
# Combine + commentaires d'installation
# --------------------------------------------------------------------------

def test_combined_concatene_les_unites():
    combined = generate_combined(_timer_cfg())
    assert "backup.service" in combined
    assert "backup.timer" in combined


def test_commentaire_installation_present():
    conf = generate_units(_service_cfg())["myapp.service"]
    assert "/etc/systemd/system/" in conf
    assert "daemon-reload" in conf


# --------------------------------------------------------------------------
# Config invalide -> exception
# --------------------------------------------------------------------------

def test_generate_units_leve_valueerror_si_invalide():
    with pytest.raises(ValueError):
        generate_units({"mode": "service", "name": "", "exec_start": ""})


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------

def test_tous_les_presets_sont_valides():
    for name in list_presets():
        cfg = get_preset(name)
        assert validate_config(cfg) == []


def test_get_preset_inconnu_leve_valueerror():
    with pytest.raises(ValueError):
        get_preset("preset-qui-n-existe-pas")


def test_get_preset_retourne_une_copie_independante():
    preset_a = get_preset("web-app")
    preset_a["name"] = "muté"
    preset_b = get_preset("web-app")
    assert preset_b["name"] == "myapp"


def test_presets_couvrent_les_deux_modes():
    modes_couverts = {PRESETS[name]["mode"] for name in list_presets()}
    assert modes_couverts == set(SUPPORTED_MODES)
