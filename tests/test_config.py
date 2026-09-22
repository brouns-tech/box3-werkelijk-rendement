from pathlib import Path

import pytest

from wr.cli import main
from wr.config import load_config, resolve_db_path
from wr.import_pipeline import ImportReport, run_import
from wr.parsers import parse_document


def test_configuration_is_optional(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.config_path is None
    assert resolve_db_path(config) == tmp_path / "data" / "wr.sqlite"


def test_explicit_missing_configuration_is_an_error(tmp_path):
    missing = tmp_path / "missing.toml"

    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config(missing)


def test_typed_configuration_preserves_generic_institution_options(tmp_path):
    config_path = tmp_path / "custom.toml"
    config_path.write_text(
        'import_root = "statements"\n'
        'db_path = "state/results.sqlite"\n'
        '[partners]\npartner_a = "Alex Example"\n'
        'partner_a_aliases = ["A. Example"]\n'
        '[institutions.broker]\nlinked_account = "NL00 TEST 0000 0000 00"\n',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.import_root == Path("statements")
    assert config.resolved_db_path == tmp_path / "state" / "results.sqlite"
    assert config.partners.partner_a_aliases == ("A. Example",)
    assert config.institution_options == {
        "broker": {"linked_account": "NL00 TEST 0000 0000 00"}
    }


def test_import_with_root_does_not_require_configuration(monkeypatch, tmp_path):
    statements = tmp_path / "statements"
    statements.mkdir()
    monkeypatch.chdir(tmp_path)

    exit_code = main(["import", "--root", str(statements)])

    assert exit_code == 0
    assert (tmp_path / "data" / "wr.sqlite").is_file()


def test_import_returns_a_structured_report(tmp_path):
    statements = tmp_path / "statements"
    statements.mkdir()

    report = run_import(statements, tmp_path / "result.sqlite")

    assert isinstance(report, ImportReport)
    assert report.seen == 0
    assert report.outcomes == []


def test_parser_receives_institution_options():
    text = (
        "flatex Bank AG\n"
        "Rekeninguittreksel nr: 001/2020\n"
        "Rekeningnummer: 1000000000\n"
        "Oud saldo van 05.02.2020 in EUR 0,00+\n"
        "06.02. 06.02. Überweisung 5.000,00+\n"
        "NL00 TEST 0000 0000 00\n"
        "Nieuw saldo 31.12.2020 Nr. 001/2020 valuta EUR 5.000,00+\n"
    )

    result = parse_document(
        "flatex",
        "account_statement",
        text,
        2020,
        institution_options={
            "flatex": {"linked_account": "NL00 TEST 0000 0000 00"}
        },
    )

    assert result.facts[0].deposits == 5000.0
