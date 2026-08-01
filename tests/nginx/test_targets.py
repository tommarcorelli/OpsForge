"""Tests des cibles Caddy et Traefik du module Nginx d'OpsForge."""

import pytest
import yaml

from modules.nginx.core import (
    SUPPORTED_TARGETS,
    TARGET_MODES,
    generate,
    generate_caddy,
    generate_haproxy,
    generate_traefik,
    get_preset,
    list_presets,
    validate_config,
)


def _static_cfg(**overrides):
    cfg = {
        "mode": "static",
        "server_name": "site.example.com",
        "root": "/var/www/site",
    }
    cfg.update(overrides)
    return cfg


def _proxy_cfg(**overrides):
    cfg = {
        "mode": "reverse_proxy",
        "server_name": "api.example.com",
        "backend_host": "127.0.0.1",
        "backend_port": 3000,
    }
    cfg.update(overrides)
    return cfg


def _lb_cfg(**overrides):
    cfg = {
        "mode": "load_balancer",
        "server_name": "app.example.com",
        "upstream_name": "app_pool",
        "backends": [
            {"host": "127.0.0.1", "port": 3001},
            {"host": "127.0.0.1", "port": 3002},
        ],
    }
    cfg.update(overrides)
    return cfg


# ---------------------------------------------------------------------------
# Dispatcher generate() / SUPPORTED_TARGETS
# ---------------------------------------------------------------------------
def test_supported_targets():
    assert set(SUPPORTED_TARGETS) == {"nginx", "caddy", "traefik", "haproxy"}


def test_generate_dispatch_par_defaut_nginx():
    assert "server {" in generate(_static_cfg())


def test_generate_cible_inconnue_leve_valueerror():
    with pytest.raises(ValueError):
        generate(_proxy_cfg(), target="varnish")


# ---------------------------------------------------------------------------
# Cible Caddy
# ---------------------------------------------------------------------------
def test_caddy_static_genere_root_et_file_server():
    conf = generate_caddy(_static_cfg())
    assert "site.example.com {" in conf
    assert "root * /var/www/site" in conf
    assert "file_server" in conf


def test_caddy_static_spa_try_files():
    conf = generate_caddy(_static_cfg(spa=True, index_file="index.html"))
    assert "try_files {path} /index.html" in conf


def test_caddy_reverse_proxy():
    conf = generate_caddy(_proxy_cfg())
    assert "reverse_proxy 127.0.0.1:3000" in conf


def test_caddy_load_balancer_avec_lb_policy():
    conf = generate_caddy(_lb_cfg(lb_algorithm="least_conn"))
    assert "reverse_proxy 127.0.0.1:3001 127.0.0.1:3002 {" in conf
    assert "lb_policy least_conn" in conf


def test_caddy_https_pas_de_prefixe_http():
    conf = generate_caddy(_proxy_cfg(https=True))
    assert "http://api.example.com {" not in conf
    assert "api.example.com {" in conf
    assert "HTTPS automatique" in conf


def test_caddy_sans_https_prefixe_http():
    conf = generate_caddy(_proxy_cfg(https=False))
    assert "http://api.example.com {" in conf


def test_caddy_gzip_et_security_headers():
    conf = generate_caddy(_proxy_cfg(gzip=True, security_headers=True))
    assert "encode gzip" in conf
    assert 'X-Frame-Options "SAMEORIGIN"' in conf


def test_caddy_taille_max_body_convertie():
    conf = generate_caddy(_proxy_cfg(client_max_body_size="10m"))
    assert "max_size 10MB" in conf


def test_caddy_size_format_invalide_retourne_none():
    from modules.nginx.core import _caddy_size
    assert _caddy_size("beaucoup") is None


def test_caddy_load_balancer_poids_ignore_avec_commentaire():
    cfg = _lb_cfg(backends=[
        {"host": "127.0.0.1", "port": 3001, "weight": 3},
        {"host": "127.0.0.1", "port": 3002},
    ])
    conf = generate_caddy(cfg)
    assert "Ponderation par backend ignoree" in conf


def test_caddy_invalide_leve_valueerror():
    with pytest.raises(ValueError):
        generate_caddy({"mode": "static", "server_name": "", "root": ""})


# ---------------------------------------------------------------------------
# Cible Traefik
# ---------------------------------------------------------------------------
def test_traefik_static_non_supporte():
    errors = validate_config(_static_cfg(), target="traefik")
    assert any("static" in e for e in errors)
    with pytest.raises(ValueError):
        generate_traefik(_static_cfg())


def test_traefik_reverse_proxy_yaml_valide():
    conf = generate_traefik(_proxy_cfg())
    # Le contenu apres l'en-tete de commentaires doit etre du YAML valide.
    yaml_part = "\n".join(line for line in conf.split("\n") if not line.startswith("#"))
    doc = yaml.safe_load(yaml_part)
    assert "http" in doc
    router = next(iter(doc["http"]["routers"].values()))
    assert router["rule"] == "Host(`api.example.com`)"
    service = next(iter(doc["http"]["services"].values()))
    assert service["loadBalancer"]["servers"] == [{"url": "http://127.0.0.1:3000"}]


def test_traefik_load_balancer_plusieurs_serveurs():
    conf = generate_traefik(_lb_cfg())
    yaml_part = "\n".join(line for line in conf.split("\n") if not line.startswith("#"))
    doc = yaml.safe_load(yaml_part)
    service = next(iter(doc["http"]["services"].values()))
    urls = [s["url"] for s in service["loadBalancer"]["servers"]]
    assert urls == ["http://127.0.0.1:3001", "http://127.0.0.1:3002"]


def test_traefik_ip_hash_devient_sticky_cookie():
    conf = generate_traefik(_lb_cfg(lb_algorithm="ip_hash"))
    yaml_part = "\n".join(line for line in conf.split("\n") if not line.startswith("#"))
    doc = yaml.safe_load(yaml_part)
    service = next(iter(doc["http"]["services"].values()))
    assert "sticky" in service["loadBalancer"]
    assert service["loadBalancer"]["sticky"]["cookie"]["name"]


def test_traefik_least_conn_note_dans_len_tete():
    conf = generate_traefik(_lb_cfg(lb_algorithm="least_conn"))
    assert "least_conn" in conf
    assert "pas d'equivalent direct" in conf


def test_traefik_https_entrypoint_et_tls():
    conf = generate_traefik(_proxy_cfg(https=True))
    yaml_part = "\n".join(line for line in conf.split("\n") if not line.startswith("#"))
    doc = yaml.safe_load(yaml_part)
    router = next(iter(doc["http"]["routers"].values()))
    assert router["entryPoints"] == ["websecure"]
    assert router["tls"]["certResolver"] == "letsencrypt"


def test_traefik_sans_https_entrypoint_web():
    conf = generate_traefik(_proxy_cfg(https=False))
    yaml_part = "\n".join(line for line in conf.split("\n") if not line.startswith("#"))
    doc = yaml.safe_load(yaml_part)
    router = next(iter(doc["http"]["routers"].values()))
    assert router["entryPoints"] == ["web"]
    assert "tls" not in router


def test_traefik_invalide_leve_valueerror():
    with pytest.raises(ValueError):
        generate_traefik(_proxy_cfg(backend_host=""))


# ---------------------------------------------------------------------------
# Cible HAProxy
# ---------------------------------------------------------------------------
def test_haproxy_static_non_supporte():
    errors = validate_config(_static_cfg(), target="haproxy")
    assert any("static" in e for e in errors)
    with pytest.raises(ValueError):
        generate_haproxy(_static_cfg())


def test_haproxy_reverse_proxy_frontend_et_backend():
    conf = generate_haproxy(_proxy_cfg())
    assert "frontend fe_api_example_com" in conf
    assert "bind *:80" in conf
    assert "default_backend be_api_example_com" in conf
    assert "backend be_api_example_com" in conf
    assert "server srv1 127.0.0.1:3000 check" in conf


def test_haproxy_load_balancer_plusieurs_serveurs_et_poids():
    conf = generate_haproxy(_lb_cfg(backends=[
        {"host": "127.0.0.1", "port": 3001, "weight": 3},
        {"host": "127.0.0.1", "port": 3002},
    ]))
    assert "server srv1 127.0.0.1:3001 check weight=3" in conf
    assert "server srv2 127.0.0.1:3002 check" in conf
    assert "server srv2 127.0.0.1:3002 check weight" not in conf


@pytest.mark.parametrize("algo,expected", [
    ("round_robin", "balance roundrobin"),
    ("least_conn", "balance leastconn"),
    ("ip_hash", "balance source"),
])
def test_haproxy_algorithmes_de_repartition(algo, expected):
    conf = generate_haproxy(_lb_cfg(lb_algorithm=algo))
    assert expected in conf


def test_haproxy_ip_hash_note_dans_len_tete():
    conf = generate_haproxy(_lb_cfg(lb_algorithm="ip_hash"))
    assert "balance source" in conf
    assert "equivalent HAProxy le plus proche" in conf


def test_haproxy_reverse_proxy_pas_de_directive_balance():
    # Un seul serveur en reverse_proxy : pas de round-robin a annoncer.
    conf = generate_haproxy(_proxy_cfg())
    assert "balance" not in conf


def test_haproxy_https_deux_frontends_et_redirection():
    conf = generate_haproxy(_proxy_cfg(https=True))
    assert "frontend fe_api_example_com_http" in conf
    assert "redirect scheme https code 301 if !{ ssl_fc }" in conf
    assert "bind *:443 ssl crt /etc/haproxy/certs/api.example.com.pem" in conf


def test_haproxy_sans_https_un_seul_frontend():
    conf = generate_haproxy(_proxy_cfg(https=False))
    assert "frontend fe_api_example_com_http" not in conf
    assert "bind *:80" in conf


def test_haproxy_gzip_et_security_headers():
    conf = generate_haproxy(_proxy_cfg(gzip=True, security_headers=True))
    assert "compression algo gzip" in conf
    assert 'X-Frame-Options "SAMEORIGIN"' in conf


def test_haproxy_websocket_timeout_tunnel():
    conf = generate_haproxy(_proxy_cfg(websocket=True))
    assert "timeout tunnel 1h" in conf


def test_haproxy_note_client_max_body_size_toujours_presente():
    conf = generate_haproxy(_proxy_cfg())
    assert "pas d'equivalent direct a client_max_body_size" in conf


def test_haproxy_slug_caracteres_non_alphanumeriques():
    conf = generate_haproxy(_proxy_cfg(server_name="my-app_01.example.com"))
    assert "fe_my_app_01_example_com" in conf
    assert "be_my_app_01_example_com" in conf


def test_haproxy_invalide_leve_valueerror():
    with pytest.raises(ValueError):
        generate_haproxy(_proxy_cfg(backend_host=""))


# ---------------------------------------------------------------------------
# Coherence des presets existants avec chaque cible compatible
# ---------------------------------------------------------------------------
def test_tous_les_presets_compatibles_generent_pour_caddy():
    for name in list_presets():
        cfg = get_preset(name)
        if cfg["mode"] in TARGET_MODES["caddy"]:
            conf = generate(cfg, target="caddy")
            assert cfg["server_name"] in conf or "http://" + cfg["server_name"] in conf


def test_tous_les_presets_compatibles_generent_pour_traefik():
    for name in list_presets():
        cfg = get_preset(name)
        if cfg["mode"] in TARGET_MODES["traefik"]:
            conf = generate(cfg, target="traefik")
            assert "http:" in conf


def test_tous_les_presets_compatibles_generent_pour_haproxy():
    for name in list_presets():
        cfg = get_preset(name)
        if cfg["mode"] in TARGET_MODES["haproxy"]:
            conf = generate(cfg, target="haproxy")
            assert "frontend fe_" in conf and "backend be_" in conf
