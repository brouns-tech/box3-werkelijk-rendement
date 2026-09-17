from wr.parsers.degiro import parse_degiro


def test_parses_portfolio_totals_with_spaced_waarde_label():
    result = parse_degiro(
        "DEGIRO Jaaroverzicht 2023\n"
        "Account: ****mpl\n"
        "Dhr. EXAMPLE USER\n"
        "Portefeuilleoverzicht per 1-1-2023\n"
        "Totale portefeuille waarde per 1-1-2023 10.000,00\n"
        "Portefeuilleoverzicht per 31-12-2023\n"
        "Totale portefeuille waarde per 31-12-2023 12.000,00"
    )

    fact = result.facts[0]
    assert fact.account_key == "masked-mpl"
    assert fact.start_balance == 10000.0
    assert fact.end_balance == 12000.0


def test_marks_pension_account_outside_box3():
    result = parse_degiro(
        "DEGIRO Jaaropgave Pensioen 2023\n"
        "Account: ****mpl\n"
        "Dhr. EXAMPLE USER\n"
        "Pensioenrekening\n"
        "Portefeuilleoverzicht per 1-1-2023\n"
        "Totale portefeuille waarde per 1-1-2023 10.000,00\n"
        "Portefeuilleoverzicht per 31-12-2023\n"
        "Totale portefeuille waarde per 31-12-2023 12.000,00"
    )

    fact = result.facts[0]
    assert fact.account_key == "masked-mpl-pensioen"
    assert fact.extra == {"box3": False}
    assert fact.logical_group is None
