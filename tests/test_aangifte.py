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


def test_parses_full_year_partnership_from_same_address_and_marriage():
    result = parse_aangifte(
        "Aangifte inkomstenbelasting 2025\n"
        "Persoonlijke gegevens van ALEX EXAMPLE\n"
        "Naam echtgenoot SAM EXAMPLE\n"
        "Had u in 2025 een echtgenoot? Ja\n"
        "Stond u heel 2025 ingeschreven op hetzelfde adres als SAM EXAMPLE? Ja"
    )

    assert result.tax_return is not None
    assert result.tax_return.full_year_fiscal_partners is True


def test_does_not_treat_co_resident_without_qualifying_relationship_as_fiscal_partner():
    result = parse_aangifte(
        "Aangifte inkomstenbelasting 2022\n"
        "Persoonlijke gegevens van ALEX EXAMPLE\n"
        "Had u in 2022 een echtgenoot? Nee\n"
        "Had u in 2022 een huisgenoot? Ja\n"
        "Stond u heel 2022 ingeschreven op hetzelfde adres als SAM EXAMPLE? Ja\n"
        "Had u een notarieel samenlevingscontract met SAM EXAMPLE? Nee\n"
        "Had u een kind samen met SAM EXAMPLE? Nee\n"
        "Was u met SAM EXAMPLE partners in een pensioenregeling? Nee\n"
        "Was SAM EXAMPLE in 2021 uw fiscale partner? Nee"
    )

    assert result.tax_return is not None
    assert result.tax_return.full_year_fiscal_partners is False


def test_parses_2025_fictitious_return_and_final_box3_tax_layout():
    result = parse_aangifte(
        "Aangifte inkomstenbelasting 2025\n"
        "Persoonlijke gegevens van ALEX EXAMPLE\n"
        "Naam echtgenoot SAM EXAMPLE\n"
        "Had u in 2025 een echtgenoot? Ja\n"
        "Stond u heel 2025 ingeschreven op hetzelfde adres als SAM EXAMPLE? Ja\n"
        "Uw gezamenlijk fictief rendement over 2025 € 8.000\n"
        "Voordeel sparen en beleggen (fictief) € 8.000\n"
        "Voordeel sparen en beleggen (fictief) € 0\n"
        "Inkomstenbelasting box 3\n€ 2.800"
    )

    assert result.tax_return is not None
    assert result.tax_return.voordeel_a == 8015.0
    assert result.tax_return.voordeel_b == 0.0
    assert result.tax_return.box3_tax_a == 2845.0


def test_parses_partner_box3_figures_from_separate_partner_block():
    result = parse_aangifte(
        "Aangifte inkomstenbelasting 2023\n"
        "Persoonlijke gegevens van ALEX EXAMPLE\n"
        "Naam echtgenoot SAM EXAMPLE\n"
        "ALEX EXAMPLE en partner zijn heel 2023 fiscale partners\n"
        "Voordeel uit sparen en beleggen € 3.000\n"
        "Inkomstenbelasting box 3\n€ 1.000\n"
        "Deel SAM EXAMPLE sparen en beleggen € 40.000\n"
        "Voordeel sparen en beleggen € 159\n"
        "Inkomstenbelasting box 3\n€ 50"
    )

    assert result.tax_return is not None
    assert result.tax_return.voordeel_b == 159.0
    assert result.tax_return.box3_tax_b == 50.0


def test_parses_official_box3_asset_aggregate_at_1_january_only():
    result = parse_aangifte(
        "Aangifte inkomstenbelasting 2023\n"
        "Bankrekeningen in box 3 € 200.000\n"
        "Beleggingen in box 3 € 60.000\n"
    )

    assert result.tax_return is not None
    assert result.tax_return.bezittingen_0101 == 260000.0
    assert result.tax_return.bezittingen_3112 is None
