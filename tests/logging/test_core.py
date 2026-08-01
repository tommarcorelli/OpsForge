import toml

from modules.logging.core import (
    generate_fluentbit,
    generate_logging,
    generate_vector,
    get_preset,
    list_presets,
    validate_config,
)


def test_list_presets_contains_expected():
    presets = list_presets()
    assert "docker-loki" in presets
    assert "nginx-loki" in presets
    assert "syslog-elasticsearch" in presets
    assert "app-json-loki" in presets
    assert "custom" in presets


def test_validate_config_rejects_unknown_backend():
    errors = validate_config({"preset": "docker-loki", "backend": "bogus"})
    assert any("Backend non supporte" in e for e in errors)


def test_validate_config_rejects_custom_without_sources():
    errors = validate_config({"preset": "custom", "backend": "fluent-bit"})
    assert any("aucune source" in e for e in errors)


def test_validate_config_rejects_tail_without_path():
    config = {
        "preset": "custom",
        "backend": "fluent-bit",
        "sources": [{"type": "tail", "tag": "x"}],
        "destination": {"type": "stdout"},
    }
    errors = validate_config(config)
    assert any("path" in e for e in errors)


def test_validate_config_rejects_syslog_with_bad_port():
    config = {
        "preset": "custom",
        "backend": "fluent-bit",
        "sources": [{"type": "syslog", "port": 99999, "tag": "sys"}],
        "destination": {"type": "stdout"},
    }
    errors = validate_config(config)
    assert any("port invalide" in e for e in errors)


def test_validate_config_rejects_missing_destination_for_custom():
    config = {
        "preset": "custom",
        "backend": "fluent-bit",
        "sources": [{"type": "tail", "path": "/var/log/x.log", "tag": "x"}],
    }
    errors = validate_config(config)
    assert any("destination" in e for e in errors)


def test_validate_config_rejects_elasticsearch_without_index():
    config = {
        "preset": "custom",
        "backend": "fluent-bit",
        "sources": [{"type": "tail", "path": "/var/log/x.log", "tag": "x"}],
        "destination": {"type": "elasticsearch", "host": "es", "port": 9200},
    }
    errors = validate_config(config)
    assert any("index" in e for e in errors)


def test_generate_fluentbit_docker_loki_preset():
    conf = generate_fluentbit(get_preset("docker-loki"))
    assert "[INPUT]" in conf
    assert "/var/lib/docker/containers/*/*.log" in conf
    assert "[OUTPUT]" in conf
    assert "Name   loki" in conf
    assert "Labels job=docker" in conf


def test_generate_fluentbit_syslog_input():
    conf = generate_fluentbit(get_preset("syslog-elasticsearch"))
    assert "Name   syslog" in conf
    assert "Port   5140" in conf
    assert "Name   es" in conf
    assert "Index  syslog" in conf


def test_generate_vector_produces_valid_toml_for_all_presets():
    for preset in list_presets():
        if preset == "custom":
            continue
        config = get_preset(preset)
        config["backend"] = "vector"
        content = generate_vector(config)
        parsed = toml.loads(content)  # doit etre du TOML syntaxiquement valide
        assert "sources" in parsed
        assert "sinks" in parsed


def test_generate_vector_loki_sink_has_correct_endpoint():
    config = get_preset("nginx-loki")
    content = generate_vector(config)
    assert 'endpoint = "http://localhost:3100"' in content


def test_generate_logging_fluentbit_backend_filename():
    files = generate_logging({"preset": "docker-loki", "backend": "fluent-bit"})
    assert set(files.keys()) == {"fluent-bit.conf"}


def test_generate_logging_vector_backend_filename():
    files = generate_logging({"preset": "docker-loki", "backend": "vector"})
    assert set(files.keys()) == {"vector.toml"}


def test_generate_logging_invalid_config_raises():
    try:
        generate_logging({"preset": "unknown-preset"})
        assert False, "aurait du lever ValueError"
    except ValueError:
        pass


def test_get_preset_returns_deep_copy():
    p1 = get_preset("docker-loki")
    p1["sources"].append({"type": "tail", "path": "/tmp/x.log", "tag": "x"})
    p2 = get_preset("docker-loki")
    assert len(p2["sources"]) == 1  # inchange


def test_custom_config_with_json_parser():
    config = {
        "preset": "custom",
        "backend": "fluent-bit",
        "sources": [{"type": "tail", "path": "/var/log/app/*.json", "tag": "app", "parser": "json"}],
        "destination": {"type": "stdout"},
    }
    assert validate_config(config) == []
    conf = generate_fluentbit(config)
    assert "Parser json" in conf
