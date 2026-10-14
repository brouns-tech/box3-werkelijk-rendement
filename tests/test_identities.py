import json
import sqlite3

import pytest

from wr.config import PartnerSettings, load_config, save_settings
from wr.db import init_db
from wr.identities import effective_partners, identity_slot, similarity, suggest_identities
from wr.recommend import rebuild_recommendations


def identity_db(names, filers=()):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO documents (content_sha256, byte_size, imported_at, parse_status) VALUES ('doc', 1, 'now', 'parsed')")
    for index, name in enumerate(names):
        conn.execute("INSERT INTO account_year_facts (document_sha256, tax_year, issuer, account_key, holder_names, capital_gain, gain_method, is_canonical) VALUES ('doc', 2023, 'bank', ?, ?, 50, 'explicit', 1)", (str(index), json.dumps([name])))
    for name in filers:
        conn.execute("INSERT OR IGNORE INTO tax_returns (document_sha256, tax_year, filer_name, voordeel_a, box3_tax_a) VALUES ('doc', 2023, ?, 100, 32)", (name,))
    conn.commit()
    return conn


def test_groups_initials_first_names_accents_and_small_spelling_differences():
    conn = identity_db(["Sophie de Vries", "S. de Vries", "Sophie", "Sophi de Vries", "Daan Jansen", "D. Jansen"])
    partners = suggest_identities(conn).partners
    assert identity_slot("S. de Vries", partners) == identity_slot("Sophie de Vries", partners)
    assert identity_slot("Sophie", partners) == identity_slot("Sophie de Vries", partners)
    assert identity_slot("Sophi de Vries", partners) == identity_slot("Sophie de Vries", partners)
    assert identity_slot("D. Jansen", partners) != identity_slot("S. de Vries", partners)
    assert similarity("Dhr. José van Dijk", "Jose van Dijk") == 1
    assert similarity("S. M. de Vries", "Sophie Maria de Vries") >= 0.8


def test_shared_surname_and_initials_do_not_bridge_two_people():
    conn = identity_db(["Sophie de Vries", "Simon de Vries", "S. de Vries", "de Vries"])
    suggestions = suggest_identities(conn)
    assert {suggestions.partners.partner_a, suggestions.partners.partner_b} == {"Sophie de Vries", "Simon de Vries"}
    assert set(suggestions.unresolved) == {"S. de Vries", "de Vries"}
    assert identity_slot("S. de Vries", suggestions.partners) is None
    assert identity_slot("de Vries", suggestions.partners) is None


def test_configured_nickname_aliases_override_inference():
    conn = identity_db(["Sophie de Vries", "Fie", "Simon de Vries"])
    configured = PartnerSettings(partner_a="Sophie de Vries", partner_a_aliases=("Fie",), unassigned_names=("S. de Vries",))
    assert effective_partners(conn, configured) == configured
    assert identity_slot("Fie", configured) == "a"
    assert identity_slot("S. de Vries", configured) is None


def test_ui_settings_override_toml_and_survive_database_removal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text('[partners]\npartner_a = "Legacy Person"\n')
    cfg = load_config()
    partners = PartnerSettings(partner_a="Sophie de Vries", partner_a_aliases=("Fie",), unassigned_names=("S. de Vries",))
    save_settings(cfg, partners, "documents")
    assert load_config().partners == partners
    assert str(load_config().import_root) == "documents"
    cfg.resolved_db_path.parent.mkdir()
    cfg.resolved_db_path.touch()
    cfg.resolved_db_path.unlink()
    assert load_config().partners == partners


def test_duplicate_alias_rejected_without_overwriting_preferences(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    save_settings(cfg, PartnerSettings(partner_a="Sophie de Vries"), "")
    with pytest.raises(ValueError, match="both taxpayers"):
        save_settings(cfg, PartnerSettings(partner_a="Sophie de Vries", partner_b="Simon de Vries", partner_a_aliases=("S. de Vries",), partner_b_aliases=("S de Vries",)), "")
    assert load_config().partners.partner_a == "Sophie de Vries"


def test_inferred_initials_flow_into_recommendations():
    conn = identity_db(["S. de Vries"], ["Sophie de Vries"])
    rebuild_recommendations(conn)
    row = conn.execute("SELECT * FROM partner_tax_results").fetchone()
    assert row["partner_name"] == "Sophie de Vries"
    assert row["allocated_actual_return"] == 50
    assert row["recommendation"] == "ACTUAL_BETTER"


def test_ambiguous_holders_keep_individual_coverage_incomplete():
    conn = identity_db(["Sophie de Vries", "S. de Vries", "Simon de Vries"], ["Sophie de Vries"])
    rebuild_recommendations(conn)
    row = conn.execute("SELECT * FROM partner_tax_results WHERE partner_name = 'Sophie de Vries'").fetchone()
    assert row["allocated_actual_return"] == 50
    assert row["coverage_status"] == "PARTIAL"
    assert "holder needs review" in row["notes"]


def test_reordering_full_year_partners_keeps_filed_figures_together():
    conn = identity_db([], ["Sophie de Vries"])
    conn.execute("UPDATE tax_returns SET full_year_fiscal_partners = 1, partner_a_name = 'Sophie de Vries', partner_b_name = 'Daan Jansen', grondslag = 1000, allocation_a = 0.8, allocation_b = 0.2, voordeel_a = 100, voordeel_b = 20, box3_tax_a = 32, box3_tax_b = 6.4")
    rebuild_recommendations(conn, PartnerSettings(partner_a="Daan Jansen", partner_b="Sophie de Vries"))
    row = conn.execute("SELECT * FROM partner_tax_results WHERE partner = 'a'").fetchone()
    assert row["partner_name"] == "Daan Jansen"
    assert row["allocation_ratio"] == 0.2
    assert row["fictitious_return"] == 20
    assert row["estimated_box3_tax_fictitious"] == 6.4
