import sqlite3

from wr.dedupe import canonicalize_facts
from wr.db import init_db
from wr.parsers.flatex import parse_flatex


def test_parses_flatex_financial_instruments_inventory():
    result = parse_flatex(
        "flatexDEGIRO Bank AG\n"
        "Lijst met financiële klanteninstrumenten en klantenfondsen\n"
        "Ingesloten vindt u de lijst voor 31.12.2021.\n"
        "Rekeningnummer : 1000000000\n"
        "Rekeningstand : 100,00 EUR\n"
        "Effectenrekeningnummer : 1000000001\n"
        "Effectenrekeningposities\n"
        "XX0000000001** 1.000,00 EUR\n"
        "XX0000000002** 2.000,00 EUR\n",
        tax_year=2022,
        doc_type="financial_instruments_statement",
    )

    fact = result.facts[0]
    assert result.tax_year == 2021
    assert fact.end_balance == 6569.01
    assert fact.extra["cash_balance"] == 27.55
    assert fact.extra["securities_market_value"] == 6541.46
    assert fact.extra["asset_class"] == "securities_portfolio"
    assert "securities portfolio" in fact.account_label
    assert fact.extra["position_count"] == 2


def test_keeps_degiro_and_flatex_as_separate_canonical_sources():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    for sha, issuer in (("degiro-doc", "degiro"), ("flatex-doc", "flatex")):
        conn.execute(
            """
            INSERT INTO documents (content_sha256, byte_size, imported_at, parse_status, doc_type)
            VALUES (?, 1, '2026-01-01T00:00:00+00:00', 'parsed', 'jaaroverzicht')
            """,
            (sha,),
        )
        conn.execute(
            """
            INSERT INTO account_year_facts (
                document_sha256, tax_year, issuer, account_key, account_label
            ) VALUES (?, 2021, ?, 'account-1', ?)
            """,
            (sha, issuer, issuer),
        )

    canonicalize_facts(conn)

    facts = conn.execute(
        "SELECT issuer FROM account_year_facts WHERE is_canonical = 1 ORDER BY issuer"
    ).fetchall()
    assert [fact["issuer"] for fact in facts] == ["degiro", "flatex"]


def test_parses_linked_ing_transfers_from_flatex_account_statement():
    result = parse_flatex(
        "flatex Bank AG\n"
        "Rekeninguittreksel nr: 001/2020\n"
        "Rekeningnummer: 1000000000\n"
        "Oud saldo van 05.02.2020 in EUR 0,00+\n"
        "06.02. 06.02. Überweisung 5.000,00+\n"
        "NL00TEST0000000000\n"
        "07.02. 07.02. Überweisung 50,00-\n"
        "page footer\n"
        "\fRekeninguittreksel nr: 001/2020\n"
        "NL00TEST0000000000\n"
        "08.02. 08.02. Dividendbetaling US0000000001 1,00+\n"
        "Nieuw saldo 31.03.2020\n",
        tax_year=2020,
        doc_type="account_statement",
        linked_account="NL00TEST0000000000",
    )

    fact = result.facts[0]
    assert fact.start_balance == 0.0
    assert fact.deposits == 5000.0
    assert fact.withdrawals == 50.0
    assert fact.extra["opening_statement"] is True


def test_keeps_cash_sweeps_out_of_external_flows():
    result = parse_flatex(
        "flatexDEGIRO Bank AG\n"
        "Rekeninguittreksel nr: 004/2021\n"
        "Rekeningnummer: 1000000002\n"
        "Oud saldo van 30.09.2021 in EUR 10,00+\n"
        "04.10. 01.10. Cash Sweep 100,00+\n"
        "05.10. 04.10. Cash Sweep 20,00-\n"
        "Nieuw saldo 31.12.2021 Nr. 004/2021 valuta EUR 90,00+\n",
        tax_year=2021,
        doc_type="account_statement",
    )

    fact = result.facts[0]
    assert fact.end_balance == 90.0
    assert fact.deposits == 0.0
    assert fact.withdrawals == 0.0
    assert fact.extra["cash_sweep_deposits"] == 100.0
    assert fact.extra["cash_sweep_withdrawals"] == 20.0
    assert fact.capital_gain == 0.0
    assert fact.gain_method == "explicit"
    assert fact.extra["return_assumption"] == "zero_by_product"
    assert fact.extra["statement_number"] == 4


def test_derives_return_from_adjacent_inventories_and_linked_flows():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    for sha, year, end_balance, doc_type in (
        ("inventory-2020", 2020, 100.0, "financial_instruments_statement"),
        ("inventory-2021", 2021, 120.0, "financial_instruments_statement"),
        ("flows-2021", 2021, None, "account_statement"),
    ):
        conn.execute(
            """
            INSERT INTO documents (content_sha256, byte_size, imported_at, parse_status, doc_type)
            VALUES (?, 1, '2026-01-01T00:00:00+00:00', 'parsed', ?)
            """,
            (sha, doc_type),
        )
        conn.execute(
            """
            INSERT INTO account_year_facts (
                document_sha256, tax_year, issuer, account_key, account_label,
                end_balance, deposits, withdrawals, extra
            ) VALUES (?, ?, 'flatex', '1000000000', 'flatex', ?, ?, ?, ?)
            """,
            (
                sha,
                year,
                end_balance,
                10.0 if sha == "flows-2021" else None,
                5.0 if sha == "flows-2021" else None,
                '{"opening_statement": false}' if sha == "flows-2021" else "{}",
            ),
        )

    canonicalize_facts(conn)

    fact = conn.execute(
        """
        SELECT start_balance, end_balance, deposits, withdrawals, capital_gain, gain_method, extra
        FROM account_year_facts
        WHERE document_sha256 = 'inventory-2021'
        """
    ).fetchone()
    result = dict(fact)
    assert {key: value for key, value in result.items() if key != "extra"} == {
        "start_balance": 100.0,
        "end_balance": 120.0,
        "deposits": 10.0,
        "withdrawals": 5.0,
        "capital_gain": 15.0,
        "gain_method": "balance_flow",
    }


def test_legacy_cash_only_balance_flow_is_cleared():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        """
        INSERT INTO documents (content_sha256, byte_size, imported_at, parse_status, doc_type)
        VALUES ('cash-only', 1, '2026-01-01T00:00:00+00:00', 'parsed', 'account_statement')
        """
    )
    conn.execute(
        """
        INSERT INTO account_year_facts (
            document_sha256, tax_year, issuer, account_key, account_label,
            start_balance, end_balance, deposits, withdrawals, capital_gain, gain_method
        ) VALUES ('cash-only', 2021, 'flatex', 'cash-account', 'flatex cash account',
                  100, 50, 0, 500, 450, 'balance_flow')
        """
    )

    canonicalize_facts(conn)

    fact = conn.execute(
        """
        SELECT capital_gain, gain_method FROM account_year_facts
        WHERE document_sha256 = 'cash-only'
        """
    ).fetchone()
    assert dict(fact) == {"capital_gain": None, "gain_method": "unknown"}
