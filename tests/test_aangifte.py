from wr.parsers.aangifte import parse_aangifte


def test_tax_return_contains_aggregates_but_no_account_inventory():
    result = parse_aangifte(
        "Aangifte inkomstenbelasting 2024\n"
        "Eigen kopie, niet opsturen\n"
        "Formulierenversie IB 650E\n"
        "Persoonlijke gegevens van ALEX EXAMPLE\n"
        "Burgerservicenummer 123456789\n"
        "Waarde van bezittingen 100.000 120.000"
    )

    assert result.tax_return is not None
    assert result.tax_return.bezittingen_0101 == 100000.0
    assert result.tax_return.bezittingen_3112 == 120000.0
    assert not hasattr(result.tax_return, "assets")


def test_parses_partner_split_from_official_printout():
    result = parse_aangifte(
        "Aangifte inkomstenbelasting 2023\n"
        "Persoonlijke gegevens van ALEX EXAMPLE\n"
        "Naam echtgenoot SAM EXAMPLE\n"
        "ALEX EXAMPLE en partner zijn heel 2023 fiscale partners\n"
        "Grondslag sparen en beleggen € 160.000\n"
        "Uw deel € 120.000\n"
        "Deel SAM EXAMPLE € 40.000"
    )

    assert result.tax_return is not None
    assert result.tax_return.full_year_fiscal_partners is True
    assert result.tax_return.filer_name == "ALEX EXAMPLE"
    assert result.tax_return.partner_b_name == "SAM EXAMPLE"
    assert result.tax_return.grondslag == 161891.0
    assert result.tax_return.grondslag_a == 154361.0
    assert result.tax_return.grondslag_b == 7530.0


def test_parses_official_box3_asset_aggregate_at_1_january_only():
    result = parse_aangifte(
        "Aangifte inkomstenbelasting 2023\n"
        "Bankrekeningen in box 3 € 200.000\n"
        "Beleggingen in box 3 € 60.000\n"
    )

    assert result.tax_return is not None
    assert result.tax_return.bezittingen_0101 == 260000.0
    assert result.tax_return.bezittingen_3112 is None
