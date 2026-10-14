import json
import sqlite3

import pytest

from wr.config import ChildSettings, PartnerSettings, load_settings, save_settings
from wr.db import init_db
from wr.identities import effective_partners, identity_slot, similarity, suggest_identities
from wr.recommend import rebuild_recommendations


INITIAL_VARIANTS = (
    "A B C Example", "A.B.C. Example", "A.B.C. EXAMPLE", "ABC Example",
    "ABC EXAMPLE", "a. b. c. example", "  A  B  C   Example  ",
)


@pytest.mark.parametrize("left", INITIAL_VARIANTS)
@pytest.mark.parametrize("right", INITIAL_VARIANTS)
def test_initial_formatting_variants_are_exact_matches(left, right):
    assert similarity(left, right) == 1.0


@pytest.mark.parametrize("variant", INITIAL_VARIANTS)
def test_initial_variants_match_configured_aliases_for_parents_and_children(variant):
    parent = PartnerSettings(partner_a="Alex Example", partner_a_aliases=("ABC Example",))
    child = PartnerSettings(partner_a="Robin Example", children=(ChildSettings("Alex Example", ("ABC Example",)),))
    assert identity_slot(variant, parent) == "a"
    assert identity_slot(variant, child) == "child_0"


def test_formatting_variants_form_one_suggestion_group():
    conn = identity_db(INITIAL_VARIANTS)
    suggestions = suggest_identities(conn)
    assert suggestions.partners.partner_b is None
    assert not suggestions.unresolved
    assert {identity_slot(name, suggestions.partners) for name in INITIAL_VARIANTS} == {"a"}


def test_case_variants_prefer_exact_identity_over_similar_first_name():
    configured = PartnerSettings(partner_a="Alex Example", partner_b="Alexa Example")
    assert identity_slot("ALEX EXAMPLE", configured) == "a"
    assert identity_slot("ALEXA EXAMPLE", configured) == "b"
    assert identity_slot("A. Example", configured) is None
    suggestions = suggest_identities(identity_db(["Alex Example", "ALEX EXAMPLE", "Alexa Example"]))
    assert not suggestions.unresolved


def test_unassigned_initial_variants_remain_unassigned_after_import():
    configured = PartnerSettings(partner_a="Robin Example", unassigned_names=("ABC Example",))
    assert identity_slot("A.B.C. Example", configured) is None
    effective = effective_partners(identity_db(["A.B.C. Example"], ["Robin Example"]), configured)
    assert effective == configured


def test_initial_variants_cannot_be_assigned_to_different_people(tmp_path):
    configured = PartnerSettings(partner_a="ABC Example", children=(ChildSettings("A.B.C. Example"),))
    with pytest.raises(ValueError, match="multiple people"):
        save_settings(load_settings(tmp_path), configured)
    assert identity_slot("A B C Example", configured) is None


def test_name_boundaries_and_distinct_initials_are_preserved():
    assert similarity("ABC Example", "ABD Example") == 0.0
    assert similarity("Ann Abel Example", "Anna Bel Example") == 0.0
    assert similarity("Example", "A.B.C. Example") == 0.0


def test_initial_alias_variants_flow_into_recommendations():
    conn = identity_db(INITIAL_VARIANTS, ["Alex Example"])
    configured = PartnerSettings(partner_a="Alex Example", partner_a_aliases=("ABC Example",))
    rebuild_recommendations(conn, configured)
    row = conn.execute("SELECT * FROM partner_tax_results").fetchone()
    assert row["allocated_actual_return"] == 50 * len(INITIAL_VARIANTS)
    assert row["coverage_status"] == "COMPLETE"
    assert conn.execute("SELECT holder_names FROM account_year_facts WHERE account_key = '1'").fetchone()[0] == json.dumps([INITIAL_VARIANTS[1]])


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
    cfg = load_settings()
    partners = PartnerSettings(partner_a="Sophie de Vries", partner_a_aliases=("Fie",), unassigned_names=("S. de Vries",))
    save_settings(cfg, partners, "documents")
    assert load_settings().partners == partners
    assert str(load_settings().import_root) == "documents"
    cfg.resolved_db_path.parent.mkdir()
    cfg.resolved_db_path.touch()
    cfg.resolved_db_path.unlink()
    assert load_settings().partners == partners


def test_duplicate_alias_rejected_without_overwriting_preferences(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_settings()
    save_settings(cfg, PartnerSettings(partner_a="Sophie de Vries"), "")
    with pytest.raises(ValueError, match="both taxpayers"):
        save_settings(cfg, PartnerSettings(partner_a="Sophie de Vries", partner_b="Simon de Vries", partner_a_aliases=("S. de Vries",), partner_b_aliases=("S de Vries",)), "")
    assert load_settings().partners.partner_a == "Sophie de Vries"


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
    assert row["allocated_actual_return"] == 100
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


def test_tax_return_partner_is_primary_and_remaining_holders_are_children():
    conn = identity_db(["Alex Example", "Blair Example", "Charlie Example", "C. Example", "Robin Example"], ["Alex Example"])
    conn.execute("UPDATE tax_returns SET partner_b_name = 'Blair Example'")
    suggestions = suggest_identities(conn)
    assert {name for _, name in suggestions.partners.configured()} == {"Alex Example", "Blair Example"}
    assert {child.canonical_name for child in suggestions.partners.children} == {"Charlie Example", "Robin Example"}
    assert identity_slot("C. Example", suggestions.partners) == identity_slot("Charlie Example", suggestions.partners)


def test_ambiguous_parent_child_initials_remain_unassigned():
    conn = identity_db(["Alex Example", "Alice Example", "A. Example"], ["Alex Example"])
    suggestions = suggest_identities(conn)
    assert suggestions.partners.partner_b is None
    assert suggestions.partners.children == (ChildSettings("Alice Example"),)
    assert suggestions.unresolved == ("A. Example",)
    assert identity_slot("A. Example", suggestions.partners) is None


def test_children_persist_and_conflicting_aliases_are_rejected(tmp_path):
    cfg = load_settings(tmp_path)
    partners = PartnerSettings(partner_a="Alex Example", children=(ChildSettings("Charlie Example", ("Charlie",)),))
    save_settings(cfg, partners)
    assert load_settings(tmp_path).partners == partners
    with pytest.raises(ValueError, match="multiple people"):
        save_settings(cfg, PartnerSettings(partner_a="Alex Example", children=(ChildSettings("Charlie Example", ("Alex Example",)),)))
    assert load_settings(tmp_path).partners == partners


def test_children_can_be_configured_before_importing_parent_documents():
    configured = PartnerSettings(children=(ChildSettings("Charlie Example"),))
    assert effective_partners(identity_db([]), configured) == configured
    effective = effective_partners(identity_db(["Charlie Example"], ["Alex Example"]), configured)
    assert effective.partner_a == "Alex Example"
    assert effective.children == configured.children


@pytest.mark.parametrize("two_parents, expected", [(False, 100), (True, 75)])
def test_child_return_is_attributed_to_parents_without_child_tax_results(two_parents, expected):
    conn = identity_db(["Alex Example", "Charlie Example"], ["Alex Example"])
    cfg = PartnerSettings(partner_a="Alex Example", partner_b="Blair Example" if two_parents else None,
                          children=(ChildSettings("Charlie Example"),))
    rebuild_recommendations(conn, cfg)
    rows = conn.execute("SELECT * FROM partner_tax_results").fetchall()
    assert rows[0]["allocated_actual_return"] == expected
    assert rows[0]["coverage_status"] == "COMPLETE"
    assert all(row["partner"] in {"a", "b"} for row in rows)


def test_new_children_detected_with_existing_profiles_but_unassigned_preserved():
    conn = identity_db(["Alex Example", "Charlie Example", "Robin Example"], ["Alex Example"])
    cfg = PartnerSettings(partner_a="Alex Example", unassigned_names=("Robin Example",))
    effective = effective_partners(conn, cfg)
    assert effective.children == (ChildSettings("Charlie Example"),)
    assert identity_slot("Robin Example", effective) is None


def test_parent_child_joint_account_belongs_fully_to_sole_parent():
    conn = identity_db(["Alex Example"], ["Alex Example"])
    conn.execute("UPDATE account_year_facts SET holder_names = ?, ownership = 'joint'", (json.dumps(["Alex Example", "Charlie Example"]),))
    cfg = PartnerSettings(partner_a="Alex Example", children=(ChildSettings("Charlie Example"),))
    rebuild_recommendations(conn, cfg)
    row = conn.execute("SELECT * FROM partner_tax_results").fetchone()
    assert row["allocated_actual_return"] == 50
    assert row["coverage_status"] == "COMPLETE"


def test_child_assets_follow_filed_split_for_full_year_partners():
    conn = identity_db(["Charlie Example"], ["Alex Example"])
    conn.execute("UPDATE tax_returns SET full_year_fiscal_partners = 1, partner_a_name = 'Alex Example', partner_b_name = 'Blair Example', grondslag = 1000, allocation_a = 0.8, allocation_b = 0.2")
    from wr.portfolio import rebuild_portfolio

    rebuild_portfolio(conn)
    rebuild_recommendations(conn)
    rows = conn.execute("SELECT * FROM partner_tax_results ORDER BY partner").fetchall()
    assert [row["allocated_actual_return"] for row in rows] == [40, 10]
    assert [row["partner_name"] for row in rows] == ["Alex Example", "Blair Example"]
