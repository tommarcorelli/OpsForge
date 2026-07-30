"""Tests du coeur du module Backup d'OpsForge (restic / Borg)."""

import os
import shutil
import subprocess

import pytest

from modules.backup.core import (
    PRESETS,
    generate_backup_script,
    generate_cron_entry,
    generate_env_template,
    generate_files,
    generate_restore_script,
    generate_systemd_units,
    get_preset,
    list_backends,
    list_presets,
    list_schedulers,
    list_tools,
    validate_config,
    write_files,
)

BASH_AVAILABLE = shutil.which("bash") is not None


def _base_config(**overrides):
    config = {
        "tool": "restic",
        "app_name": "test-app",
        "repo_backend": "local",
        "repo_path": "/tmp/repo",
        "source_paths": ["/data"],
        "exclude_patterns": [],
        "passphrase_env_var": "BACKUP_PASSPHRASE",
        "retention": {"keep_daily": 7, "keep_weekly": 4, "keep_monthly": 6, "keep_yearly": 0},
        "scheduler": "systemd",
        "schedule_oncalendar": "*-*-* 03:00:00",
    }
    config.update(overrides)
    return config


def _assert_bash_valid(script_text):
    if not BASH_AVAILABLE:
        pytest.skip("bash n'est pas disponible dans cet environnement")
    result = subprocess.run(
        ["bash", "-n", "-"], input=script_text, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"bash -n a echoue :\n{result.stderr}\n---\n{script_text}"


# --------------------------------------------------------------------------
# validate_config
# --------------------------------------------------------------------------
def test_config_valide_ne_retourne_aucune_erreur():
    assert validate_config(_base_config()) == []


def test_config_non_dict_est_une_erreur():
    assert validate_config("pas un dict") != []
    assert validate_config(None) != []


def test_tool_inconnu_est_une_erreur():
    errors = validate_config(_base_config(tool="tarsnap"))
    assert any("tool inconnu" in e for e in errors)


def test_app_name_invalide_est_une_erreur():
    errors = validate_config(_base_config(app_name="avec espaces !"))
    assert any("app_name invalide" in e for e in errors)


def test_repo_backend_inconnu_est_une_erreur():
    errors = validate_config(_base_config(repo_backend="ftp"))
    assert any("repo_backend inconnu" in e for e in errors)


def test_borg_avec_backend_s3_est_une_erreur():
    errors = validate_config(_base_config(tool="borg", repo_backend="s3", s3_bucket="x"))
    assert any("S3" in e for e in errors)


def test_repo_path_manquant_est_une_erreur():
    config = _base_config()
    del config["repo_path"]
    errors = validate_config(config)
    assert any("repo_path" in e for e in errors)


def test_source_paths_vide_est_une_erreur():
    errors = validate_config(_base_config(source_paths=[]))
    assert any("source_paths" in e for e in errors)


def test_source_paths_manquant_est_une_erreur():
    config = _base_config()
    del config["source_paths"]
    errors = validate_config(config)
    assert any("source_paths" in e for e in errors)


def test_sftp_sans_host_est_une_erreur():
    errors = validate_config(_base_config(repo_backend="sftp", sftp_user="backup"))
    assert any("sftp_host" in e for e in errors)


def test_sftp_sans_user_est_une_erreur():
    errors = validate_config(_base_config(repo_backend="sftp", sftp_host="host.example.com"))
    assert any("sftp_user" in e for e in errors)


def test_sftp_complet_est_valide():
    errors = validate_config(_base_config(repo_backend="sftp", sftp_host="h", sftp_user="u"))
    assert errors == []


def test_s3_sans_bucket_est_une_erreur():
    errors = validate_config(_base_config(repo_backend="s3"))
    assert any("s3_bucket" in e for e in errors)


def test_scheduler_inconnu_est_une_erreur():
    errors = validate_config(_base_config(scheduler="airflow"))
    assert any("scheduler inconnu" in e for e in errors)


def test_retention_negative_est_une_erreur():
    errors = validate_config(_base_config(retention={"keep_daily": -1}))
    assert any("retention.keep_daily" in e for e in errors)


def test_retention_cle_inconnue_est_une_erreur():
    errors = validate_config(_base_config(retention={"keep_hourly": 3}))
    assert any("Cle de retention inconnue" in e for e in errors)


def test_retention_non_dict_est_une_erreur():
    errors = validate_config(_base_config(retention="beaucoup"))
    assert any("retention" in e for e in errors)


# --------------------------------------------------------------------------
# generate_backup_script — restic
# --------------------------------------------------------------------------
def test_restic_backup_script_syntaxe_bash_valide():
    _assert_bash_valid(generate_backup_script(_base_config()))


def test_restic_backup_script_contenu():
    script = generate_backup_script(_base_config())
    assert "restic init" in script
    assert 'export RESTIC_REPOSITORY="/tmp/repo"' in script
    assert "restic backup" in script
    assert '"/data"' in script
    assert "--keep-daily 7" in script
    assert "--keep-weekly 4" in script
    assert "--keep-monthly 6" in script
    assert "--keep-yearly" not in script  # 0 => flag omis


def test_restic_backup_script_sftp_repo_url():
    config = _base_config(repo_backend="sftp", sftp_host="backup.example.com", sftp_user="backupuser")
    script = generate_backup_script(config)
    assert "sftp:backupuser@backup.example.com:/tmp/repo" in script


def test_restic_backup_script_s3_repo_url():
    config = _base_config(repo_backend="s3", s3_bucket="mybucket", repo_path="prefix/path")
    script = generate_backup_script(config)
    assert "s3:s3.amazonaws.com/mybucket/prefix/path" in script


def test_restic_backup_script_exclude_patterns():
    script = generate_backup_script(_base_config(exclude_patterns=["*.log", "*/tmp/*"]))
    assert "--exclude '*.log'" in script
    assert "--exclude '*/tmp/*'" in script


def test_restic_backup_script_webhook_notification():
    script = generate_backup_script(_base_config(notify_webhook_url="https://hc-ping.com/xyz"))
    assert "trap notify_echec ERR" in script
    assert "NOTIFY_WEBHOOK_URL" in script
    _assert_bash_valid(script)


def test_restic_backup_script_sans_webhook_pas_de_trap():
    script = generate_backup_script(_base_config())
    assert "trap notify_echec" not in script


def test_backup_script_invalide_leve_value_error():
    with pytest.raises(ValueError):
        generate_backup_script({"tool": "restic"})


# --------------------------------------------------------------------------
# generate_backup_script — borg
# --------------------------------------------------------------------------
def test_borg_backup_script_syntaxe_bash_valide():
    _assert_bash_valid(generate_backup_script(_base_config(tool="borg")))


def test_borg_backup_script_contenu():
    script = generate_backup_script(_base_config(tool="borg"))
    assert "borg init --encryption=repokey" in script
    assert 'export BORG_REPO="/tmp/repo"' in script
    assert "borg create --stats --compression lz4" in script
    assert "test-app-{now:%Y-%m-%d_%H%M%S}" in script
    assert "borg prune" in script


def test_borg_backup_script_un_seul_source_path_sans_exclude():
    script = generate_backup_script(_base_config(tool="borg", source_paths=["/data"], exclude_patterns=[]))
    _assert_bash_valid(script)
    assert '"/data"' in script


def test_borg_backup_script_un_seul_source_path_avec_exclude():
    script = generate_backup_script(
        _base_config(tool="borg", source_paths=["/data"], exclude_patterns=["*.tmp"])
    )
    _assert_bash_valid(script)
    assert "--exclude '*.tmp'" in script


def test_borg_backup_script_plusieurs_sources_et_excludes():
    script = generate_backup_script(
        _base_config(tool="borg", source_paths=["/data", "/etc/app", "/var/lib/app"],
                     exclude_patterns=["*.log", "*.tmp", "*/cache/*"])
    )
    _assert_bash_valid(script)
    for path in ("/data", "/etc/app", "/var/lib/app"):
        assert f'"{path}"' in script
    for pattern in ("*.log", "*.tmp", "*/cache/*"):
        assert f"--exclude '{pattern}'" in script


def test_borg_backup_script_sftp_repo_url():
    config = _base_config(tool="borg", repo_backend="sftp", sftp_host="h.example.com", sftp_user="u")
    script = generate_backup_script(config)
    assert "u@h.example.com:/tmp/repo" in script


# --------------------------------------------------------------------------
# generate_restore_script
# --------------------------------------------------------------------------
def test_restic_restore_script_syntaxe_bash_valide():
    _assert_bash_valid(generate_restore_script(_base_config()))


def test_restic_restore_script_contenu():
    script = generate_restore_script(_base_config())
    assert "restic restore" in script
    assert 'SNAPSHOT="${1:-latest}"' in script
    assert "restic snapshots" in script


def test_borg_restore_script_syntaxe_bash_valide():
    _assert_bash_valid(generate_restore_script(_base_config(tool="borg")))


def test_borg_restore_script_contenu():
    script = generate_restore_script(_base_config(tool="borg"))
    assert "borg extract" in script
    assert "borg list" in script


def test_restore_script_invalide_leve_value_error():
    with pytest.raises(ValueError):
        generate_restore_script({"tool": "restic"})


# --------------------------------------------------------------------------
# generate_systemd_units / generate_cron_entry
# --------------------------------------------------------------------------
def test_systemd_units_noms_de_fichiers():
    units = generate_systemd_units(_base_config(app_name="myapp"))
    assert set(units.keys()) == {"myapp-backup.service", "myapp-backup.timer"}


def test_systemd_service_contenu():
    units = generate_systemd_units(_base_config(app_name="myapp"))
    service = units["myapp-backup.service"]
    assert "[Service]" in service
    assert "Type=oneshot" in service
    assert "ExecStart=/opt/myapp/backup.sh" in service


def test_systemd_timer_contenu():
    units = generate_systemd_units(_base_config(app_name="myapp", schedule_oncalendar="*-*-* 04:00:00"))
    timer = units["myapp-backup.timer"]
    assert "OnCalendar=*-*-* 04:00:00" in timer
    assert "Persistent=true" in timer


def test_cron_entry_contenu():
    entry = generate_cron_entry(_base_config(app_name="myapp", schedule_cron="0 4 * * *"))
    assert "0 4 * * * /opt/myapp/backup.sh" in entry


# --------------------------------------------------------------------------
# generate_env_template
# --------------------------------------------------------------------------
def test_env_template_contient_la_variable_passphrase():
    template = generate_env_template(_base_config(passphrase_env_var="MY_PASSPHRASE"))
    assert "MY_PASSPHRASE=" in template


def test_env_template_s3_contient_les_cles_aws():
    template = generate_env_template(_base_config(repo_backend="s3"))
    assert "AWS_ACCESS_KEY_ID" in template
    assert "AWS_SECRET_ACCESS_KEY" in template


def test_env_template_sftp_mentionne_la_cle_ssh():
    template = generate_env_template(_base_config(repo_backend="sftp"))
    assert "SSH" in template


def test_env_template_local_ne_mentionne_ni_aws_ni_ssh():
    template = generate_env_template(_base_config(repo_backend="local"))
    assert "AWS_ACCESS_KEY_ID" not in template


# --------------------------------------------------------------------------
# generate_files (dispatch complet)
# --------------------------------------------------------------------------
def test_generate_files_systemd_contient_les_units():
    fichiers = generate_files(_base_config(scheduler="systemd", app_name="myapp"))
    assert "myapp-backup.service" in fichiers
    assert "myapp-backup.timer" in fichiers
    assert "crontab-entry.txt" not in fichiers


def test_generate_files_cron_contient_la_crontab():
    fichiers = generate_files(_base_config(scheduler="cron"))
    assert "crontab-entry.txt" in fichiers
    assert "backup.service" not in "".join(fichiers.keys())


def test_generate_files_contient_toujours_backup_restore_env():
    fichiers = generate_files(_base_config())
    assert "backup.sh" in fichiers
    assert "restore.sh" in fichiers
    assert "backup.env.example" in fichiers


def test_generate_files_invalide_leve_value_error():
    with pytest.raises(ValueError):
        generate_files({"tool": "restic"})


# --------------------------------------------------------------------------
# write_files
# --------------------------------------------------------------------------
def test_write_files_ecrit_sur_disque(tmp_path):
    paths = write_files(_base_config(), str(tmp_path))
    assert len(paths) == 5  # backup.sh, restore.sh, env, service, timer
    for p in paths:
        assert os.path.isfile(p)


def test_write_files_scripts_sont_executables(tmp_path):
    paths = write_files(_base_config(), str(tmp_path))
    for p in paths:
        if p.endswith(".sh"):
            mode = os.stat(p).st_mode
            assert mode & 0o100  # bit executable owner


def test_write_files_cree_les_dossiers_manquants(tmp_path):
    output_dir = str(tmp_path / "sous" / "dossier")
    paths = write_files(_base_config(), output_dir)
    assert all(os.path.isfile(p) for p in paths)


# --------------------------------------------------------------------------
# Listing helpers
# --------------------------------------------------------------------------
def test_list_tools():
    assert set(list_tools()) == {"restic", "borg"}


def test_list_backends():
    assert set(list_backends()) == {"local", "sftp", "s3"}


def test_list_schedulers():
    assert set(list_schedulers()) == {"systemd", "cron"}


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------
def test_list_presets_correspond_au_dict_presets():
    assert set(list_presets()) == set(PRESETS.keys())


def test_get_preset_inconnu_leve_value_error():
    with pytest.raises(ValueError):
        get_preset("ce-preset-n-existe-pas")


def test_get_preset_retourne_une_copie():
    p1 = get_preset("restic-local-systemd")
    p1["app_name"] = "modifie"
    p2 = get_preset("restic-local-systemd")
    assert p2["app_name"] != "modifie"


@pytest.mark.parametrize("nom_preset", list(PRESETS.keys()))
def test_tous_les_presets_sont_valides(nom_preset):
    config = get_preset(nom_preset)
    assert validate_config(config) == []


@pytest.mark.parametrize("nom_preset", list(PRESETS.keys()))
def test_tous_les_presets_generent_des_scripts_bash_valides(nom_preset):
    config = get_preset(nom_preset)
    fichiers = generate_files(config)
    assert "backup.sh" in fichiers
    assert "restore.sh" in fichiers
    _assert_bash_valid(fichiers["backup.sh"])
    _assert_bash_valid(fichiers["restore.sh"])
