"""Tests du coeur du module Nginx d'OpsForge."""

import pytest

from modules.nginx.core import (
    generate_config,
    validate_config,
    list_presets,
    get_preset,
    SUPPORTED_MODES,
    LB_ALGORITHMS,
    PRESETS,
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
        "backends": [
            {"host": "127.0.0.1", "port": 3001},
            {"host": "127.0.0.1", "port": 3002},
        ],
    }
    cfg.update(overrides)
    return cfg


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def test_mode_invalide_rejete():
    errors = validate_config({"mode": "wordpress"})
    assert any("Mode non supporte" in e for e in errors)


def test_server_name_manquant_rejete():
    cfg = _static_cfg(server_name="")
    errors = validate_config(cfg)
    assert any("server_name" in e or "domaine" in e for e in errors)


def test_static_sans_root_rejete():
    cfg = _static_cfg(root="")
    errors = validate_config(cfg)
    assert any("root" in e for e in errors)


def test_reverse_proxy_sans_backend_host_rejete():
    cfg = _proxy_cfg(backend_host="")
    errors = validate_config(cfg)
    assert any("backend_host" in e for e in errors)


def test_reverse_proxy_port_invalide_rejete():
    cfg = _proxy_cfg(backend_port=99999)
    errors = validate_config(cfg)
    assert any("Port de backend invalide" in e for e in errors)


def test_load_balancer_moins_de_deux_backends_rejete():
    cfg = _lb_cfg(backends=[{"host": "127.0.0.1", "port": 3001}])
    errors = validate_config(cfg)
    assert any("Au moins 2 backends" in e for e in errors)


def test_load_balancer_algorithme_invalide_rejete():
    cfg = _lb_cfg(lb_algorithm="magic")
    errors = validate_config(cfg)
    assert any("Algorithme de repartition invalide" in e for e in errors)


def test_listen_port_invalide_rejete():
    cfg = _static_cfg(listen_port=70000)
    errors = validate_config(cfg)
    assert any("Port d'ecoute invalide" in e for e in errors)


def test_client_max_body_size_invalide_rejete():
    cfg = _static_cfg(client_max_body_size="beaucoup")
    errors = validate_config(cfg)
    assert any("client_max_body_size invalide" in e for e in errors)


def test_config_valide_ne_leve_aucune_erreur():
    assert validate_config(_static_cfg()) == []
    assert validate_config(_proxy_cfg()) == []
    assert validate_config(_lb_cfg()) == []


# --------------------------------------------------------------------------
# Generation : mode static
# --------------------------------------------------------------------------

def test_static_genere_root_et_index():
    conf = generate_config(_static_cfg())
    assert "root /var/www/site;" in conf
    assert "index index.html;" in conf
    assert "server_name site.example.com;" in conf


def test_static_spa_utilise_fallback_index():
    conf = generate_config(_static_cfg(spa=True))
    assert "try_files $uri $uri/ /index.html;" in conf


def test_static_non_spa_repond_404():
    conf = generate_config(_static_cfg(spa=False))
    assert "try_files $uri $uri/ =404;" in conf


# --------------------------------------------------------------------------
# Generation : mode reverse_proxy
# --------------------------------------------------------------------------

def test_reverse_proxy_genere_proxy_pass():
    conf = generate_config(_proxy_cfg())
    assert "proxy_pass http://127.0.0.1:3000;" in conf
    assert "proxy_set_header Host $host;" in conf


def test_reverse_proxy_websocket_ajoute_upgrade_headers():
    conf = generate_config(_proxy_cfg(websocket=True))
    assert "proxy_set_header Upgrade $http_upgrade;" in conf
    assert 'proxy_set_header Connection "upgrade";' in conf


def test_reverse_proxy_sans_websocket_omet_upgrade_headers():
    conf = generate_config(_proxy_cfg(websocket=False))
    assert "Upgrade $http_upgrade" not in conf


# --------------------------------------------------------------------------
# Generation : mode load_balancer
# --------------------------------------------------------------------------

def test_load_balancer_genere_upstream_avec_tous_les_backends():
    conf = generate_config(_lb_cfg())
    assert "upstream backend_pool {" in conf
    assert "server 127.0.0.1:3001;" in conf
    assert "server 127.0.0.1:3002;" in conf
    assert "proxy_pass http://backend_pool;" in conf


def test_load_balancer_nom_upstream_personnalise():
    conf = generate_config(_lb_cfg(upstream_name="mon_pool"))
    assert "upstream mon_pool {" in conf
    assert "proxy_pass http://mon_pool;" in conf


@pytest.mark.parametrize("algo", LB_ALGORITHMS)
def test_load_balancer_algorithmes(algo):
    conf = generate_config(_lb_cfg(lb_algorithm=algo))
    if algo == "round_robin":
        # Round robin est le defaut nginx : aucune directive dediee.
        assert "least_conn;" not in conf
        assert "ip_hash;" not in conf
    else:
        assert f"{algo};" in conf


def test_load_balancer_poids_optionnel():
    cfg = _lb_cfg(backends=[
        {"host": "127.0.0.1", "port": 3001, "weight": 3},
        {"host": "127.0.0.1", "port": 3002},
    ])
    conf = generate_config(cfg)
    assert "server 127.0.0.1:3001 weight=3;" in conf
    assert "server 127.0.0.1:3002;" in conf


# --------------------------------------------------------------------------
# Options transverses
# --------------------------------------------------------------------------

def test_https_genere_redirection_et_bloc_ssl():
    conf = generate_config(_proxy_cfg(https=True))
    assert "return 301 https://$host$request_uri;" in conf
    assert "listen 443 ssl http2;" in conf
    assert "ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;" in conf
    assert "certbot certonly --nginx -d api.example.com" in conf


def test_sans_https_pas_de_bloc_ssl():
    conf = generate_config(_proxy_cfg(https=False))
    assert "ssl_certificate" not in conf
    assert "listen 443" not in conf


def test_gzip_active_ajoute_directives():
    conf = generate_config(_static_cfg(gzip=True))
    assert "gzip on;" in conf


def test_gzip_desactive_par_defaut():
    conf = generate_config(_static_cfg())
    assert "gzip on;" not in conf


def test_security_headers_actifs():
    conf = generate_config(_static_cfg(security_headers=True))
    assert 'add_header X-Frame-Options "SAMEORIGIN" always;' in conf


def test_client_max_body_size_personnalise():
    conf = generate_config(_proxy_cfg(client_max_body_size="20m"))
    assert "client_max_body_size 20m;" in conf


def test_commentaire_activation_present():
    conf = generate_config(_static_cfg())
    assert "ln -s /etc/nginx/sites-available/site.example.com" in conf


# --------------------------------------------------------------------------
# Config invalide -> exception
# --------------------------------------------------------------------------

def test_generate_config_leve_valueerror_si_invalide():
    with pytest.raises(ValueError):
        generate_config({"mode": "static", "server_name": "", "root": ""})


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
    preset_a = get_preset("load-balanced-app")
    preset_a["backends"].append({"host": "1.2.3.4", "port": 9999})
    preset_b = get_preset("load-balanced-app")
    assert len(preset_b["backends"]) == 2  # la mutation de preset_a n'a pas fuite dans PRESETS


def test_list_presets_couvre_les_trois_modes():
    modes_couverts = {PRESETS[name]["mode"] for name in list_presets()}
    assert modes_couverts == set(SUPPORTED_MODES)
