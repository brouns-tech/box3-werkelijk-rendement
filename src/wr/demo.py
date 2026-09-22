from __future__ import annotations

import json
from pathlib import Path

from wr.config import PartnerSettings
from wr.db import connect, init_db
from wr.portfolio import rebuild_portfolio
from wr.recommend import rebuild_recommendations

DEMO_YEAR = 2024
PARTNERS = PartnerSettings(
    partner_a="Sophie de Vries",
    partner_b="Daan Jansen",
    partner_a_aliases=("S. de Vries",),
    partner_b_aliases=("D. Jansen",),
)

_FACTS = (
    {
        "issuer": "ing",
        "account_key": "NL11INGB0001234567",
        "account_label": "Oranje Spaarrekening",
        "holder_names": ["Sophie de Vries", "Daan Jansen"],
        "ownership": "joint",
        "start_balance": 45000.0,
        "end_balance": 47750.0,
        "deposits": 2000.0,
        "withdrawals": 0.0,
        "interest_received": 750.0,
        "gain_method": "interest_only",
    },
    {
        "issuer": "rabobank",
        "account_key": "NL22RABO0002345678",
        "account_label": "Rabo InternetSparen",
        "holder_names": ["Sophie de Vries"],
        "ownership": "individual",
        "start_balance": 18000.0,
        "end_balance": 18540.0,
        "deposits": 0.0,
        "withdrawals": 0.0,
        "interest_received": 540.0,
        "gain_method": "interest_only",
    },
    {
        "issuer": "raisin",
        "account_key": "RAISIN-DEMO-01",
        "account_label": "Nordic Savings Account",
        "holder_names": ["Daan Jansen"],
        "ownership": "individual",
        "start_balance": 27000.0,
        "end_balance": 27945.0,
        "deposits": 0.0,
        "withdrawals": 0.0,
        "interest_received": 945.0,
        "gain_method": "interest_only",
    },
    {
        "issuer": "degiro",
        "account_key": "DEGIRO-DEMO-01",
        "account_label": "Beleggingsrekening",
        "holder_names": ["Sophie de Vries"],
        "ownership": "individual",
        "start_balance": 65000.0,
        "end_balance": 71300.0,
        "deposits": 5000.0,
        "withdrawals": 1000.0,
        "dividends_gross": 1400.0,
        "withholding_tax": 210.0,
        "capital_gain": 2300.0,
        "gain_method": "explicit",
    },
    {
        "issuer": "flatex",
        "account_key": "FLATEX-DEMO-01",
        "account_label": "Effectendepot",
        "holder_names": ["Daan Jansen"],
        "ownership": "individual",
        "start_balance": 42000.0,
        "end_balance": 45000.0,
        "deposits": 2000.0,
        "withdrawals": 0.0,
        "capital_gain": 1000.0,
        "gain_method": "explicit",
    },
    {
        "issuer": "revolut",
        "account_key": "REVOLUT-DEMO-01",
        "account_label": "Flexible Cash Funds",
        "holder_names": ["Sophie de Vries", "Daan Jansen"],
        "ownership": "joint",
        "start_balance": 8000.0,
        "end_balance": 10080.0,
        "deposits": 2000.0,
        "withdrawals": 0.0,
        "capital_gain": 80.0,
        "gain_method": "earned_return",
    },
)


def create_demo_workspace(directory: str | Path) -> Path:
    workspace = Path(directory)
    workspace.mkdir(parents=True, exist_ok=True)
    db_path = workspace / "wr-demo.sqlite"
    db_path.unlink(missing_ok=True)

    conn = connect(db_path)
    init_db(conn)
    _insert_demo_data(conn)
    rebuild_portfolio(conn)
    rebuild_recommendations(conn, PARTNERS)
    conn.close()

    config_path = workspace / "config.toml"
    config_path.write_text(
        'db_path = "wr-demo.sqlite"\n\n'
        "[partners]\n"
        'partner_a = "Sophie de Vries"\n'
        'partner_b = "Daan Jansen"\n'
        'partner_a_aliases = ["S. de Vries"]\n'
        'partner_b_aliases = ["D. Jansen"]\n',
        encoding="utf-8",
    )
    return config_path


def _insert_demo_data(conn) -> None:
    for index, fact in enumerate(_FACTS, start=1):
        document_id = f"demo-{index:02d}"
        conn.execute(
            """
            INSERT INTO documents (
                content_sha256, byte_size, page_count, first_seen_path, imported_at,
                issuer, doc_type, tax_year, raw_text_excerpt, parse_status
            ) VALUES (?, ?, 1, ?, '2025-01-15T12:00:00+00:00', ?,
                      'annual_statement', ?, 'Synthetic demo statement', 'parsed')
            """,
            (
                document_id,
                1000 + index,
                f"demo/statements/{fact['issuer']}-2024.pdf",
                fact["issuer"],
                DEMO_YEAR,
            ),
        )
        conn.execute(
            """
            INSERT INTO account_year_facts (
                document_sha256, tax_year, issuer, account_key, account_label,
                holder_names, ownership, currency, start_balance, end_balance,
                deposits, withdrawals, interest_received, interest_paid,
                dividends_gross, withholding_tax, capital_gain, gain_method,
                is_canonical, extra
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'EUR', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                document_id,
                DEMO_YEAR,
                fact["issuer"],
                fact["account_key"],
                fact["account_label"],
                json.dumps(fact["holder_names"]),
                fact["ownership"],
                fact.get("start_balance"),
                fact.get("end_balance"),
                fact.get("deposits"),
                fact.get("withdrawals"),
                fact.get("interest_received"),
                fact.get("interest_paid"),
                fact.get("dividends_gross"),
                fact.get("withholding_tax"),
                fact.get("capital_gain"),
                fact["gain_method"],
                json.dumps({"synthetic": True}),
            ),
        )

    conn.execute(
        """
        INSERT INTO documents (
            content_sha256, byte_size, page_count, first_seen_path, imported_at,
            issuer, doc_type, tax_year, raw_text_excerpt, parse_status
        ) VALUES (
            'demo-tax-return', 2400, 12, 'demo/statements/aangifte-2024.pdf',
            '2025-03-01T12:00:00+00:00', 'belastingdienst', 'aangifte_ib', 2024,
            'Verzonden: Aangifte Inkomstenbelasting 2024 — synthetic demo', 'parsed'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO tax_returns (
            document_sha256, tax_year, filer_name, full_year_fiscal_partners,
            partner_a_name, partner_b_name, bezittingen_0101, bezittingen_3112,
            heffingsvrij_vermogen, grondslag, allocation_a, allocation_b,
            allocation_status, voordeel_a, voordeel_b, box3_tax_a, box3_tax_b
        ) VALUES (
            'demo-tax-return', 2024, 'Sophie de Vries', 1,
            'Sophie de Vries', 'Daan Jansen', 205000, 220615,
            114000, 106615, 0.55, 0.45, 'EXPLICIT', 6000, 4900, 2160, 1764
        )
        """
    )
    conn.commit()
