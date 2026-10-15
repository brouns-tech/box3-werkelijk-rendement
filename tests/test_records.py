import json
import sqlite3

import pytest
from pydantic import ValidationError

from wr.config import load_settings, save_settings
from wr.db import init_db, insert_facts, update_document, upsert_document
from wr.models import AccountYearFact
from wr.parsers.flatex import FlatexMetadata, ReturnEvidence, SecurityPosition
from wr.portfolio import is_box3_fact
from wr.records import FactRecord


def test_nested_metadata_survives_database_round_trip():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    upsert_document(conn, content_sha256="synthetic", byte_size=1, imported_at="2026-01-01", parse_status="parsed")
    fact = AccountYearFact(
        2024, "flatex", "example-account", "Synthetic portfolio",
        holder_names=["Alex Example"],
        extra=FlatexMetadata(
            positions=[SecurityPosition(isin="XX0000000001", market_value=125)],
            return_derived_from=ReturnEvidence(opening_balance="prior_31_december_inventory", external_flow_documents=2),
        ),
    )
    insert_facts(conn, "synthetic", [fact])
    row = conn.execute("SELECT * FROM account_year_facts").fetchone()
    restored = FactRecord.from_row(row)
    assert isinstance(restored.extra, FlatexMetadata)
    assert restored.extra.positions[0].market_value == 125
    assert restored.extra.return_derived_from.external_flow_documents == 2
    assert restored.holder_names == ["Alex Example"]
    assert json.loads(row["extra"]) == {
        "positions": [{"isin": "XX0000000001", "market_value": 125.0}],
        "return_derived_from": {"opening_balance": "prior_31_december_inventory", "external_flow_documents": 2},
    }


@pytest.mark.parametrize("metadata", ['{"box3": "false"}', '{"box_3": false}', '[]', '{invalid', [], False])
def test_invalid_exclusion_metadata_fails_closed(metadata):
    with pytest.raises(ValidationError):
        is_box3_fact({"extra": metadata})


def test_fact_fields_are_validated_before_database_write():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    with pytest.raises(ValidationError, match="tax_year"):
        insert_facts(conn, "synthetic", [{"issuer": "bank", "account_key": "example"}])
    with pytest.raises(ValidationError, match="finite"):
        insert_facts(conn, "synthetic", [{"tax_year": 2024, "issuer": "bank", "account_key": "example", "end_balance": float("nan")}])
    assert conn.execute("SELECT COUNT(*) FROM account_year_facts").fetchone()[0] == 0


def test_document_update_distinguishes_omitted_fields_from_explicit_null():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    upsert_document(conn, content_sha256="synthetic", byte_size=1, imported_at="2026-01-01", parse_status="parsed", tax_year=2024)
    update_document(conn, "synthetic", issuer="bank")
    assert conn.execute("SELECT tax_year FROM documents").fetchone()[0] == 2024
    update_document(conn, "synthetic", tax_year=None)
    assert conn.execute("SELECT tax_year FROM documents").fetchone()[0] is None
    with pytest.raises(ValidationError):
        update_document(conn, "synthetic", unknown_column="invalid")


def test_settings_validate_known_options_and_preserve_extension_namespaces(tmp_path):
    path = tmp_path / ".wr-settings.json"
    path.write_text(json.dumps({"version": 2, "institutions": {"flatex": {"linked_account": " example "}, "future-bank": {"enabled": True, "codes": [1, 2]}}}))
    settings = load_settings(tmp_path)
    assert settings.institution_options["flatex"].linked_account == "example"
    save_settings(settings)
    assert json.loads(path.read_text())["institutions"]["future-bank"] == {"enabled": True, "codes": [1, 2]}
    path.write_text(json.dumps({"version": 2, "institutions": {"flatex": {"linked_account": 123}}}))
    with pytest.raises(ValidationError, match="linked_account"):
        load_settings(tmp_path)


@pytest.mark.parametrize("holders", ['{"name": "Alex Example"}', '[123]', '"Alex Example"'])
def test_holder_json_must_be_a_list_of_strings(holders):
    with pytest.raises(ValidationError):
        FactRecord.from_row({"holder_names": holders})
