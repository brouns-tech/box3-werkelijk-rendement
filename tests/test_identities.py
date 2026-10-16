import json
import sqlite3

import pytest


from wr.reconciliation.service import reconcile_facts
from wr.models.identities import ChildIdentity, HouseholdSettings, TaxpayerIdentity, TaxpayerPosition
from wr.workspace.settings import load_settings, save_settings
from wr.storage.migrations import init_db
from wr.identities.service import effective_household, suggest_identities
from wr.identities.matching import (
    EXACT_MATCH,
    FIRST_NAME_MATCH,
    FUZZY_NAME_MATCH,
    INITIALS_MATCH,
    NO_MATCH,
    resolve_identity,
    similarity,
)
from wr.calculations.service import rebuild_recommendations


INITIAL_VARIANTS = (
    "A B C Example", "A.B.C. Example", "A.B.C. EXAMPLE", "ABC Example",
    "ABC EXAMPLE", "a. b. c. example", "  A  B  C   Example  ",
)


@pytest.mark.parametrize("left,right,expected", [
    ("", "Alex Example", NO_MATCH),
    ("Alex Example", "Blair Example", NO_MATCH),
    ("Alex Example", "ALEX EXAMPLE", EXACT_MATCH),
    ("Alex", "Alex Example", FIRST_NAME_MATCH),
    ("A. Example", "Alex Example", INITIALS_MATCH),
    ("A. B. Example", "Alex Blair Example", INITIALS_MATCH),
    ("Sophi Example", "Sophie Example", FUZZY_NAME_MATCH),
    ("Alex Examples", "Alex Example", FUZZY_NAME_MATCH),
])
def test_named_similarity_scores(left, right, expected):
    assert similarity(left, right) == expected
    assert similarity(right, left) == expected


@pytest.mark.parametrize("name,expected", [
    (None, None),
    ("", None),
    ("Unknown Person", None),
    ("Alex Example", TaxpayerPosition.PRIMARY),
    ("Blair Example", TaxpayerPosition.SECONDARY),
    ("Charlie Example", "child"),
    ("A. Example", None),
])
def test_resolve_identity_return_values(name, expected):
    partners = HouseholdSettings(identities=(TaxpayerIdentity(name="Alex Example", position=TaxpayerPosition.PRIMARY), TaxpayerIdentity(name="Blair Example", position=TaxpayerPosition.SECONDARY),) + (ChildIdentity(name="Charlie Example"), ChildIdentity(name="Alice Example")))
    identity = resolve_identity(name, partners)
    if expected is None:
        assert identity is None
    elif expected == "child":
        assert identity is partners.children[0]
    else:
        assert identity is partners.taxpayer(expected)


@pytest.mark.parametrize("left", INITIAL_VARIANTS)
@pytest.mark.parametrize("right", INITIAL_VARIANTS)
def test_initial_formatting_variants_are_exact_matches(left, right):
    assert similarity(left, right) == 1.0


@pytest.mark.parametrize("variant", INITIAL_VARIANTS)
def test_initial_variants_match_configured_aliases_for_parents_and_children(variant):
    parent = HouseholdSettings(identities=(TaxpayerIdentity(name="Alex Example", position=TaxpayerPosition.PRIMARY, aliases=("ABC Example",)),))
    child = HouseholdSettings(identities=(TaxpayerIdentity(name="Robin Example", position=TaxpayerPosition.PRIMARY),) + (ChildIdentity(name="Alex Example", aliases=("ABC Example",)),))
    assert resolve_identity(variant, parent) is parent.primary
    assert resolve_identity(variant, child) is child.children[0]


def test_formatting_variants_form_one_suggestion_group():
    conn = identity_db(INITIAL_VARIANTS)
    suggestions = suggest_identities(conn)
    assert suggestions.household.secondary is None
    assert not suggestions.unresolved
    assert {resolve_identity(name, suggestions.household) for name in INITIAL_VARIANTS} == {suggestions.household.primary}


def test_case_variants_prefer_exact_identity_over_similar_first_name():
    configured = HouseholdSettings(identities=(TaxpayerIdentity(name="Alex Example", position=TaxpayerPosition.PRIMARY), TaxpayerIdentity(name="Alexa Example", position=TaxpayerPosition.SECONDARY),))
    assert resolve_identity("ALEX EXAMPLE", configured) is configured.primary
    assert resolve_identity("ALEXA EXAMPLE", configured) is configured.secondary
    assert resolve_identity("A. Example", configured) is None
    suggestions = suggest_identities(identity_db(["Alex Example", "ALEX EXAMPLE", "Alexa Example"]))
    assert not suggestions.unresolved


def test_unassigned_initial_variants_remain_unassigned_after_import():
    configured = HouseholdSettings(identities=(TaxpayerIdentity(name="Robin Example", position=TaxpayerPosition.PRIMARY),), unassigned_names=("ABC Example",))
    assert resolve_identity("A.B.C. Example", configured) is None
    effective = effective_household(identity_db(["A.B.C. Example"], ["Robin Example"]), configured)
    assert effective == configured


def test_initial_variants_cannot_be_assigned_to_different_people(tmp_path):
    configured = HouseholdSettings(identities=(TaxpayerIdentity(name="ABC Example", position=TaxpayerPosition.PRIMARY),) + (ChildIdentity(name="A.B.C. Example"),))
    with pytest.raises(ValueError, match="multiple people"):
        save_settings(load_settings(tmp_path), configured)
    assert resolve_identity("A B C Example", configured) is None


def test_name_boundaries_and_distinct_initials_are_preserved():
    assert similarity("ABC Example", "ABD Example") == 0.0
    assert similarity("Ann Abel Example", "Anna Bel Example") == 0.0
    assert similarity("Example", "A.B.C. Example") == 0.0


def test_initial_alias_variants_flow_into_recommendations():
    conn = identity_db(INITIAL_VARIANTS, ["Alex Example"])
    configured = HouseholdSettings(identities=(TaxpayerIdentity(name="Alex Example", position=TaxpayerPosition.PRIMARY, aliases=("ABC Example",)),))
    rebuild_recommendations(conn, configured)
    row = conn.execute("SELECT * FROM taxpayer_tax_results").fetchone()
    assert row["allocated_actual_return"] == 50 * len(INITIAL_VARIANTS)
    assert row["coverage_status"] == "COMPLETE"
    assert conn.execute("SELECT holder_names FROM account_year_facts WHERE account_key = '1'").fetchone()[0] == json.dumps([INITIAL_VARIANTS[1]])


def identity_db(names, filers=()):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO documents (content_sha256, byte_size, imported_at, parse_status) VALUES ('doc', 1, 'now', 'parsed')")
    for index, name in enumerate(names):
        conn.execute("INSERT INTO account_year_facts (document_sha256, tax_year, issuer, account_key, holder_names, capital_gain, gain_method) VALUES ('doc', 2023, 'bank', ?, ?, 50, 'explicit')", (str(index), json.dumps([name])))
    for name in filers:
        conn.execute("INSERT OR IGNORE INTO tax_returns (document_sha256, tax_year, filer_name, voordeel_a, box3_tax_a) VALUES ('doc', 2023, ?, 100, 32)", (name,))
    conn.commit()
    reconcile_facts(conn)
    return conn


def test_groups_initials_first_names_accents_and_small_spelling_differences():
    conn = identity_db(["Sophie de Vries", "S. de Vries", "Sophie", "Sophi de Vries", "Daan Jansen", "D. Jansen"])
    partners = suggest_identities(conn).household
    assert resolve_identity("S. de Vries", partners) == resolve_identity("Sophie de Vries", partners)
    assert resolve_identity("Sophie", partners) == resolve_identity("Sophie de Vries", partners)
    assert resolve_identity("Sophi de Vries", partners) == resolve_identity("Sophie de Vries", partners)
    assert resolve_identity("D. Jansen", partners) != resolve_identity("S. de Vries", partners)
    assert similarity("Dhr. José van Dijk", "Jose van Dijk") == 1
    assert similarity("S. M. de Vries", "Sophie Maria de Vries") >= 0.8


def test_shared_surname_and_initials_do_not_bridge_two_people():
    conn = identity_db(["Sophie de Vries", "Simon de Vries", "S. de Vries", "de Vries"])
    suggestions = suggest_identities(conn)
    assert {suggestions.household.primary.name, suggestions.household.secondary.name} == {"Sophie de Vries", "Simon de Vries"}
    assert set(suggestions.unresolved) == {"S. de Vries", "de Vries"}
    assert resolve_identity("S. de Vries", suggestions.household) is None
    assert resolve_identity("de Vries", suggestions.household) is None


def test_configured_nickname_aliases_override_inference():
    conn = identity_db(["Sophie de Vries", "Fie", "Simon de Vries"])
    configured = HouseholdSettings(identities=(TaxpayerIdentity(name="Sophie de Vries", position=TaxpayerPosition.PRIMARY, aliases=("Fie",)),), unassigned_names=("S. de Vries",))
    assert effective_household(conn, configured) == configured
    assert resolve_identity("Fie", configured) is configured.primary
    assert resolve_identity("S. de Vries", configured) is None


def test_ui_settings_replace_earlier_json_profiles_and_survive_database_removal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".wr-settings.json").write_text(json.dumps({"partners": {"partner_a": "Legacy Person"}}))
    cfg = load_settings()
    partners = HouseholdSettings(identities=(TaxpayerIdentity(name="Sophie de Vries", position=TaxpayerPosition.PRIMARY, aliases=("Fie",)),), unassigned_names=("S. de Vries",))
    save_settings(cfg, partners, "documents")
    assert load_settings().household == partners
    assert str(load_settings().import_root) == "documents"
    cfg.resolved_db_path.parent.mkdir()
    cfg.resolved_db_path.touch()
    cfg.resolved_db_path.unlink()
    assert load_settings().household == partners


def test_duplicate_alias_rejected_without_overwriting_preferences(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_settings()
    save_settings(cfg, HouseholdSettings(identities=(TaxpayerIdentity(name="Sophie de Vries", position=TaxpayerPosition.PRIMARY),)), "")
    with pytest.raises(ValueError, match="multiple people"):
        save_settings(cfg, HouseholdSettings(identities=(TaxpayerIdentity(name="Sophie de Vries", position=TaxpayerPosition.PRIMARY, aliases=("S. de Vries",)), TaxpayerIdentity(name="Simon de Vries", position=TaxpayerPosition.SECONDARY, aliases=("S de Vries",)),)), "")
    assert load_settings().household.primary.name == "Sophie de Vries"


def test_inferred_initials_flow_into_recommendations():
    conn = identity_db(["S. de Vries"], ["Sophie de Vries"])
    rebuild_recommendations(conn)
    row = conn.execute("SELECT * FROM taxpayer_tax_results").fetchone()
    assert row["taxpayer_name"] == "Sophie de Vries"
    assert row["allocated_actual_return"] == 50
    assert row["recommendation"] == "ACTUAL_BETTER"


def test_ambiguous_holders_keep_individual_coverage_incomplete():
    conn = identity_db(["Sophie de Vries", "S. de Vries", "Simon de Vries"], ["Sophie de Vries"])
    rebuild_recommendations(conn)
    row = conn.execute("SELECT * FROM taxpayer_tax_results WHERE taxpayer_name = 'Sophie de Vries'").fetchone()
    assert row["allocated_actual_return"] == 100
    assert row["coverage_status"] == "PARTIAL"
    assert "holder needs review" in row["notes"]


def test_reordering_full_year_partners_keeps_filed_figures_together():
    conn = identity_db([], ["Sophie de Vries"])
    conn.execute("UPDATE tax_returns SET full_year_fiscal_partners = 1, partner_a_name = 'Sophie de Vries', partner_b_name = 'Daan Jansen', grondslag = 1000, allocation_a = 0.8, allocation_b = 0.2, voordeel_a = 100, voordeel_b = 20, box3_tax_a = 32, box3_tax_b = 6.4")
    rebuild_recommendations(conn, HouseholdSettings(identities=(TaxpayerIdentity(name="Daan Jansen", position=TaxpayerPosition.PRIMARY), TaxpayerIdentity(name="Sophie de Vries", position=TaxpayerPosition.SECONDARY),)))
    row = conn.execute("SELECT * FROM taxpayer_tax_results WHERE taxpayer_position = 'primary'").fetchone()
    assert row["taxpayer_name"] == "Daan Jansen"
    assert row["allocation_ratio"] == 0.2
    assert row["fictitious_return"] == 20
    assert row["estimated_box3_tax_fictitious"] == 6.4


def test_tax_return_partner_is_primary_and_remaining_holders_are_children():
    conn = identity_db(["Alex Example", "Blair Example", "Charlie Example", "C. Example", "Robin Example"], ["Alex Example"])
    conn.execute("UPDATE tax_returns SET partner_b_name = 'Blair Example'")
    suggestions = suggest_identities(conn)
    assert {identity.name for identity in suggestions.household.taxpayers} == {"Alex Example", "Blair Example"}
    assert {child.name for child in suggestions.household.children} == {"Charlie Example", "Robin Example"}
    assert resolve_identity("C. Example", suggestions.household) == resolve_identity("Charlie Example", suggestions.household)


def test_ambiguous_parent_child_initials_remain_unassigned():
    conn = identity_db(["Alex Example", "Alice Example", "A. Example"], ["Alex Example"])
    suggestions = suggest_identities(conn)
    assert suggestions.household.secondary is None
    assert [child.name for child in suggestions.household.children] == ["Alice Example"]
    assert suggestions.unresolved == ("A. Example",)
    assert resolve_identity("A. Example", suggestions.household) is None


def test_children_persist_and_conflicting_aliases_are_rejected(tmp_path):
    cfg = load_settings(tmp_path)
    partners = HouseholdSettings(identities=(TaxpayerIdentity(name="Alex Example", position=TaxpayerPosition.PRIMARY),) + (ChildIdentity(name="Charlie Example", aliases=("Charlie",)),))
    save_settings(cfg, partners)
    assert load_settings(tmp_path).household == partners
    with pytest.raises(ValueError, match="multiple people"):
        save_settings(cfg, HouseholdSettings(identities=(TaxpayerIdentity(name="Alex Example", position=TaxpayerPosition.PRIMARY),) + (ChildIdentity(name="Charlie Example", aliases=("Alex Example",)),)))
    assert load_settings(tmp_path).household == partners


def test_children_can_be_configured_before_importing_parent_documents():
    configured = HouseholdSettings(identities=() + (ChildIdentity(name="Charlie Example"),))
    assert effective_household(identity_db([]), configured) == configured
    effective = effective_household(identity_db(["Charlie Example"], ["Alex Example"]), configured)
    assert effective.primary.name == "Alex Example"
    assert effective.children == configured.children


@pytest.mark.parametrize("two_parents, expected", [(False, 100), (True, 75)])
def test_child_return_is_attributed_to_parents_without_child_tax_results(two_parents, expected):
    conn = identity_db(["Alex Example", "Charlie Example"], ["Alex Example"])
    cfg = HouseholdSettings(identities=(TaxpayerIdentity(name="Alex Example", position=TaxpayerPosition.PRIMARY), *((TaxpayerIdentity(name="Blair Example" if two_parents else None, position=TaxpayerPosition.SECONDARY),) if ("Blair Example" if two_parents else None) else ()),) + (ChildIdentity(name="Charlie Example"),))
    rebuild_recommendations(conn, cfg)
    rows = conn.execute("SELECT * FROM taxpayer_tax_results").fetchall()
    assert rows[0]["allocated_actual_return"] == expected
    assert rows[0]["coverage_status"] == "COMPLETE"
    assert all(row["taxpayer_position"] in {"primary", "secondary"} for row in rows)


def test_new_children_detected_with_existing_profiles_but_unassigned_preserved():
    conn = identity_db(["Alex Example", "Charlie Example", "Robin Example"], ["Alex Example"])
    cfg = HouseholdSettings(identities=(TaxpayerIdentity(name="Alex Example", position=TaxpayerPosition.PRIMARY),), unassigned_names=("Robin Example",))
    effective = effective_household(conn, cfg)
    assert [child.name for child in effective.children] == ["Charlie Example"]
    assert resolve_identity("Robin Example", effective) is None


def test_parent_child_joint_account_belongs_fully_to_sole_parent():
    conn = identity_db(["Alex Example"], ["Alex Example"])
    conn.execute("UPDATE account_year_facts SET holder_names = ?, ownership = 'joint'", (json.dumps(["Alex Example", "Charlie Example"]),))
    cfg = HouseholdSettings(identities=(TaxpayerIdentity(name="Alex Example", position=TaxpayerPosition.PRIMARY),) + (ChildIdentity(name="Charlie Example"),))
    rebuild_recommendations(conn, cfg)
    row = conn.execute("SELECT * FROM taxpayer_tax_results").fetchone()
    assert row["allocated_actual_return"] == 50
    assert row["coverage_status"] == "COMPLETE"


def test_child_assets_follow_filed_split_for_full_year_partners():
    conn = identity_db(["Charlie Example"], ["Alex Example"])
    conn.execute("UPDATE tax_returns SET full_year_fiscal_partners = 1, partner_a_name = 'Alex Example', partner_b_name = 'Blair Example', grondslag = 1000, allocation_a = 0.8, allocation_b = 0.2")
    from wr.calculations.service import rebuild_portfolio

    rebuild_portfolio(conn)
    rebuild_recommendations(conn)
    rows = conn.execute("SELECT * FROM taxpayer_tax_results ORDER BY taxpayer_position").fetchall()
    assert [row["allocated_actual_return"] for row in rows] == [40, 10]
    assert [row["taxpayer_name"] for row in rows] == ["Alex Example", "Blair Example"]
