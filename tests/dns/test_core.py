import json
import re

from modules.dns.core import (
    generate_bind_zone,
    generate_dns,
    generate_route53_json,
    get_preset,
    list_presets,
    validate_config,
)


def test_list_presets_contains_expected():
    presets = list_presets()
    assert "site-statique" in presets
    assert "domaine-mail" in presets
    assert "sous-domaines-services" in presets
    assert "verification-domaine" in presets
    assert "custom" in presets


def test_all_presets_are_valid_except_custom():
    for name in list_presets():
        if name == "custom":
            continue
        assert validate_config(get_preset(name)) == [], name


def test_custom_preset_has_no_records_and_is_invalid():
    config = get_preset("custom")
    assert config["records"] == []
    assert validate_config(config) != []


def test_get_preset_returns_deep_copy():
    p1 = get_preset("site-statique")
    p1["records"].append({"type": "A", "name": "x", "value": "1.2.3.4"})
    p2 = get_preset("site-statique")
    assert len(p2["records"]) == 2


def test_get_preset_defaults_to_bind_engine():
    assert get_preset("site-statique")["engine"] == "bind"


def test_get_preset_accepts_engine_override():
    assert get_preset("site-statique", engine="route53")["engine"] == "route53"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_validate_rejects_unknown_engine():
    config = get_preset("site-statique")
    config["engine"] = "powerdns-api"
    errors = validate_config(config)
    assert any("Moteur non supporte" in e for e in errors)


def test_validate_rejects_invalid_domain():
    config = get_preset("site-statique")
    config["domain"] = "pas un domaine"
    errors = validate_config(config)
    assert any("Domaine invalide" in e for e in errors)


def test_validate_rejects_missing_soa_fields():
    config = get_preset("site-statique")
    config["soa"] = {}
    errors = validate_config(config)
    assert any("primary_ns" in e for e in errors)
    assert any("admin_email" in e for e in errors)


def test_validate_rejects_no_nameservers():
    config = get_preset("site-statique")
    config["nameservers"] = []
    errors = validate_config(config)
    assert any("Aucun serveur de noms" in e for e in errors)


def test_validate_rejects_no_records():
    config = get_preset("site-statique")
    config["records"] = []
    errors = validate_config(config)
    assert any("Aucun enregistrement" in e for e in errors)


def test_validate_rejects_unknown_record_type():
    config = get_preset("site-statique")
    config["records"] = [{"type": "PTR", "name": "@", "value": "x"}]
    errors = validate_config(config)
    assert any("non supporte" in e for e in errors)


def test_validate_rejects_invalid_ipv4():
    config = get_preset("site-statique")
    config["records"] = [{"type": "A", "name": "@", "value": "999.999.999.999"}]
    errors = validate_config(config)
    assert any("IPv4" in e for e in errors)


def test_validate_rejects_invalid_ipv6():
    config = get_preset("site-statique")
    config["records"] = [{"type": "AAAA", "name": "@", "value": "pas-une-ipv6"}]
    errors = validate_config(config)
    assert any("IPv6" in e for e in errors)


def test_validate_accepts_valid_ipv6():
    config = get_preset("site-statique")
    config["records"] = [{"type": "AAAA", "name": "@", "value": "2001:db8::1"}]
    assert validate_config(config) == []


def test_validate_rejects_cname_without_trailing_dot():
    config = get_preset("site-statique")
    config["records"] = [{"type": "CNAME", "name": "www", "value": "exemple.com"}]
    errors = validate_config(config)
    assert any("point" in e for e in errors)


def test_validate_rejects_mx_without_priority():
    config = get_preset("site-statique")
    config["records"] = [{"type": "MX", "name": "@", "value": "mail.exemple.com."}]
    errors = validate_config(config)
    assert any("priorite manquante" in e.lower() for e in errors)


def test_validate_rejects_srv_missing_fields():
    config = get_preset("site-statique")
    config["records"] = [{"type": "SRV", "name": "_sip._tcp", "value": "sip.exemple.com.", "priority": 10}]
    errors = validate_config(config)
    assert any("weight" in e for e in errors)
    assert any("port" in e for e in errors)


def test_validate_rejects_caa_invalid_tag():
    config = get_preset("site-statique")
    config["records"] = [{"type": "CAA", "name": "@", "value": "letsencrypt.org", "tag": "invalidtag", "flag": 0}]
    errors = validate_config(config)
    assert any("tag invalide" in e for e in errors)


def test_validate_rejects_cname_at_apex():
    config = get_preset("site-statique")
    config["records"] = [{"type": "CNAME", "name": "@", "value": "exemple.com."}]
    errors = validate_config(config)
    assert any("racine du domaine" in e for e in errors)


def test_validate_rejects_cname_sharing_name_with_other_record():
    config = get_preset("site-statique")
    config["records"] = [
        {"type": "CNAME", "name": "www", "value": "exemple.com."},
        {"type": "A", "name": "www", "value": "203.0.113.10"},
    ]
    errors = validate_config(config)
    assert any("ne peut avoir que" in e for e in errors)


def test_validate_accepts_multiple_a_records_same_name_round_robin():
    config = get_preset("site-statique")
    config["records"] = [
        {"type": "A", "name": "@", "value": "203.0.113.10"},
        {"type": "A", "name": "@", "value": "203.0.113.11"},
    ]
    assert validate_config(config) == []


# ---------------------------------------------------------------------------
# Generation BIND
# ---------------------------------------------------------------------------
def test_bind_zone_contains_origin_and_soa():
    zone = generate_bind_zone(get_preset("site-statique"))
    assert "$ORIGIN exemple.com." in zone
    assert "SOA" in zone
    assert "ns1.exemple.com. admin.exemple.com." in zone


def test_bind_zone_serial_matches_date_format():
    zone = generate_bind_zone(get_preset("site-statique"))
    match = re.search(r"(\d{10})\t; serial", zone)
    assert match, zone
    assert re.match(r"^\d{8}00$", match.group(1))


def test_bind_zone_lists_all_nameservers():
    zone = generate_bind_zone(get_preset("site-statique"))
    assert zone.count("IN\tNS\t") == 2


def test_bind_zone_mx_includes_priority():
    zone = generate_bind_zone(get_preset("domaine-mail"))
    assert "@\tIN\tMX\t10\tmail.exemple.com." in zone


def test_bind_zone_txt_is_quoted():
    zone = generate_bind_zone(get_preset("domaine-mail"))
    assert '"v=spf1 mx ~all"' in zone


def test_bind_zone_srv_and_caa_format():
    config = get_preset("site-statique")
    config["records"] = [
        {"type": "A", "name": "@", "value": "203.0.113.10"},
        {"type": "SRV", "name": "_sip._tcp", "value": "sip.exemple.com.", "priority": 10, "weight": 5, "port": 5060},
        {"type": "CAA", "name": "@", "value": "letsencrypt.org", "tag": "issue", "flag": 0},
    ]
    zone = generate_bind_zone(config)
    assert "_sip._tcp\tIN\tSRV\t10 5 5060 sip.exemple.com." in zone
    assert '@\tIN\tCAA\t0 issue "letsencrypt.org"' in zone


# ---------------------------------------------------------------------------
# Generation Route53
# ---------------------------------------------------------------------------
def test_route53_output_is_valid_json():
    content = generate_route53_json(get_preset("site-statique"))
    parsed = json.loads(content)
    assert "Changes" in parsed
    assert len(parsed["Changes"]) == 2


def test_route53_names_are_fully_qualified():
    parsed = json.loads(generate_route53_json(get_preset("site-statique")))
    names = [c["ResourceRecordSet"]["Name"] for c in parsed["Changes"]]
    assert "exemple.com." in names
    assert "www.exemple.com." in names


def test_route53_mx_combines_priority_and_value():
    parsed = json.loads(generate_route53_json(get_preset("domaine-mail")))
    mx = next(c for c in parsed["Changes"] if c["ResourceRecordSet"]["Type"] == "MX")
    assert mx["ResourceRecordSet"]["ResourceRecords"][0]["Value"] == "10 mail.exemple.com."


def test_route53_txt_value_is_quoted_and_escaped():
    parsed = json.loads(generate_route53_json(get_preset("domaine-mail")))
    txt = next(c for c in parsed["Changes"] if c["ResourceRecordSet"]["Type"] == "TXT" and c["ResourceRecordSet"]["Name"] == "exemple.com.")
    assert txt["ResourceRecordSet"]["ResourceRecords"][0]["Value"] == '"v=spf1 mx ~all"'


def test_route53_action_is_upsert():
    parsed = json.loads(generate_route53_json(get_preset("site-statique")))
    assert all(c["Action"] == "UPSERT" for c in parsed["Changes"])


# ---------------------------------------------------------------------------
# Point d'entree
# ---------------------------------------------------------------------------
def test_generate_dns_bind_filename():
    files = generate_dns(get_preset("site-statique"))
    assert set(files) == {"exemple.com.zone"}


def test_generate_dns_route53_filename():
    files = generate_dns(get_preset("site-statique", engine="route53"))
    assert set(files) == {"exemple.com.route53.json"}


def test_generate_dns_invalid_config_raises():
    try:
        generate_dns(get_preset("custom"))
        assert False, "aurait du lever ValueError"
    except ValueError:
        pass
