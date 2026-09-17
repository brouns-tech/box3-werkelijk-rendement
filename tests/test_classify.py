from wr.classify import classify


def test_accepts_official_belastingdienst_aangifte_template():
    classification = classify(
        "Eigen kopie, niet opsturen\n"
        "Aangifte Inkomstenbelasting 2024\n"
        "Formulierenversie IB 650E\n"
        "Burgerservicenummer 123456789"
    )

    assert classification is not None
    assert (classification.issuer, classification.doc_type) == (
        "belastingdienst",
        "aangifte_ib",
    )


def test_requires_official_aangifte_template_markers():
    assert classify(
        "Aangifte inkomstenbelasting 2024\n"
        "Burgerservicenummer 123456789"
    ) is None


def test_requires_full_year_revolut_account_statement():
    assert classify(
        "Revolut Account statement\n"
        "Transactions from January 1, 2024 to January 31, 2024"
    ) is None


def test_accepts_degiro_jaaroverzicht_with_portfolio_totals():
    classification = classify(
        "flatexDEGIRO Bank Dutch Branch\n"
        "Hierbij ontvangt u het jaaroverzicht 2023 van uw beleggingsrekening\n"
        "Portefeuilleoverzicht per 1-1-2023\n"
        "Totale portefeuille waarde per 1-1-2023 1.000,00 EUR"
    )

    assert classification is not None
    assert (classification.issuer, classification.doc_type) == ("degiro", "jaaroverzicht")
