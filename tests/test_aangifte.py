from wr.parsers.aangifte import parse_aangifte


def test_report_totals_do_not_match_table_of_contents_page_numbers():
    text = """
3.2.1 Waarde van bezittingen                                      8
3.2.2 Waarde van schulden                                         9
Totaal waarde bezittingen                                   318.895 325.723
Waarde van bezittingen                                      318.895 325.723
"""

    tax_return = parse_aangifte(text, 2024).tax_return

    assert tax_return is not None
    assert tax_return.bezittingen_0101 == 318895.0
    assert tax_return.bezittingen_3112 == 325723.0


def test_portal_return_parses_partners_allocation_and_nonbusiness_assets():
    text = """
Aangifte inkomstenbelasting 2025
Persoonlijke gegevens van T S N EXAMPLE
Had u in 2025 een echtgenoot?                                  Ja
Naam echtgenoot                                             E J M EXAMPLE
Stond u heel 2025 ingeschreven op hetzelfde adres als E J M EXAMPLE?   Ja

Bankrekening: SNS Sparen NL90 SNSB 0000 0000 00: € 10.000
  Naam bankrekening                                         SNS Sparen
  IBAN (rekeningnummer)                                     NL90 SNSB 0000 0000 00
  Saldo op 1 januari 2025                                   € 10.000
  Was het een zakelijke rekening?                           Nee

Bankrekening: Knab Zakelijk NL94 KNAB 0000 0000 00: € 20.000
  Naam bankrekening                                         Knab Zakelijk
  IBAN (rekeningnummer)                                     NL94 KNAB 0000 0000 00
  Saldo op 1 januari 2025                                   € 20.000
  Was het een zakelijke rekening?                           Ja

Belegging: DEGIRO Beleggingsrekening example: € 30.000
  Omschrijving                                              DEGIRO Beleggingsrekening
  Nummer                                                    example
  Was het een zakelijke belegging?                          Nee

Uw gezamenlijk fictief rendement over 2025                  € 8.000
Grondslag voordeel uit sparen en beleggen    € 200.000 € 150.000 € 50.000
"""

    tax_return = parse_aangifte(text, 2025).tax_return

    assert tax_return is not None
    assert tax_return.filer_name == "T S N EXAMPLE"
    assert tax_return.partner_b_name == "E J M EXAMPLE"
    assert tax_return.full_year_fiscal_partners is True
    assert tax_return.grondslag == 200000.0
    assert tax_return.allocation_a == 0.75
    assert tax_return.allocation_b == 0.25
    assert tax_return.voordeel_a == 6000.0
    assert tax_return.voordeel_b == 2000.0
    assert tax_return.bezittingen_0101 == 40000.0
    assert [asset.account_id for asset in tax_return.assets] == [
        "NL90SNSB0000000000",
        "example",
    ]


def test_older_portal_return_parses_single_filer_box3_values():
    text = """
Aangifte inkomstenbelasting 2022
Persoonlijke gegevens van T S N EXAMPLE
Had u in 2022 een echtgenoot?                                  Nee
Stond u heel 2022 ingeschreven op hetzelfde adres als iemand?  Ja
Grondslag sparen en beleggen
                                                               € 28.671
Voordeel uit sparen en beleggen                                € 521
Inkomstenbelasting box 3: 31% van € 521                        € 161
"""

    tax_return = parse_aangifte(text, 2022).tax_return

    assert tax_return is not None
    assert tax_return.full_year_fiscal_partners is False
    assert tax_return.grondslag == 28671.0
    assert tax_return.voordeel_a == 521.0
    assert tax_return.box3_tax_a == 161.0


def test_older_joint_portal_return_parses_both_partner_values():
    text = """
Aangifte inkomstenbelasting 2023
Persoonlijke gegevens van T S N EXAMPLE
Had u in 2023 een echtgenoot?                                  Ja
Naam echtgenoot                                                E J M EXAMPLE
Stond u heel 2023 ingeschreven op hetzelfde adres?             Ja
Grondslag voordeel uit sparen en beleggen      € 160.000 € 120.000 € 40.000
Voordeel uit sparen en beleggen                                € 3.000
Inkomstenbelasting box 3: 32% van € 3.000                      € 1.050
Voordeel uit sparen en beleggen                                € 159
Inkomstenbelasting box 3: 32% van € 159                        € 50
"""

    tax_return = parse_aangifte(text, 2023).tax_return

    assert tax_return is not None
    assert tax_return.full_year_fiscal_partners is True
    assert tax_return.voordeel_a == 3283.0
    assert tax_return.voordeel_b == 159.0
    assert tax_return.box3_tax_a == 1050.0
    assert tax_return.box3_tax_b == 50.0
