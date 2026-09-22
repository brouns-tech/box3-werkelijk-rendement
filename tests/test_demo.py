import json
import sqlite3

from wr.config import load_config, resolve_db_path
from wr.demo import create_demo_workspace


def test_demo_workspace_contains_complete_synthetic_analysis(tmp_path):
    config_path = create_demo_workspace(tmp_path)
    settings = load_config(config_path)

    assert settings.partners.partner_a == "Sophie de Vries"
    assert settings.partners.partner_b == "Daan Jansen"

    conn = sqlite3.connect(resolve_db_path(settings))
    conn.row_factory = sqlite3.Row
    portfolio = conn.execute("SELECT * FROM yearly_portfolio").fetchone()
    results = conn.execute(
        "SELECT * FROM partner_tax_results ORDER BY partner"
    ).fetchall()
    facts = conn.execute(
        "SELECT holder_names, extra FROM account_year_facts ORDER BY id"
    ).fetchall()

    assert portfolio["tax_year"] == 2024
    assert portfolio["coverage_status"] == "COMPLETE"
    assert portfolio["source_fact_count"] == 6
    assert [row["partner_name"] for row in results] == [
        "Sophie de Vries",
        "Daan Jansen",
    ]
    assert {row["recommendation"] for row in results} == {"ACTUAL_BETTER"}
    assert all(json.loads(row["extra"])["synthetic"] for row in facts)
    assert {name for row in facts for name in json.loads(row["holder_names"])} == {
        "Sophie de Vries",
        "Daan Jansen",
    }
