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


def test_excludes_revolut_business_account_statement():
    assert classify(
        "Revolut Business Account statement\n"
        "Balance summary\n"
        "Transactions from January 1, 2025 to December 31, 2025"
    ) is None


def test_requires_personal_revolut_current_account_summary():
    classification = classify(
        "Revolut EUR Statement\n"
        "Account (Current Account)\n"
        "Transactions from January 1, 2025 to December 31, 2025"
    )
    assert classification is not None
    assert (classification.issuer, classification.doc_type) == (
        "revolut",
        "account_statement",
    )


def test_accepts_degiro_jaaroverzicht_with_portfolio_totals():
    classification = classify(
        "flatexDEGIRO Bank Dutch Branch\n"
        "Hierbij ontvangt u het jaaroverzicht 2023 van uw beleggingsrekening\n"
        "Portefeuilleoverzicht per 1-1-2023\n"
        "Totale portefeuille waarde per 1-1-2023 1.000,00 EUR"
    )

    assert classification is not None
    assert (classification.issuer, classification.doc_type) == ("degiro", "jaaroverzicht")


def test_requires_rabobank_annual_overview_layout():
    assert classify(
        "Rabobank Financieel Jaaroverzicht\n"
        "Saldo 01-01-2024\nSaldo 31-12-2024"
    ) is None

    classification = classify(
        "Rabobank\nOnderwerp Financieel Jaaroverzicht 2024\n"
        "Saldo 01-01-2024\nSaldo 31-12-2024"
    )
    assert classification is not None
    assert (classification.issuer, classification.doc_type) == ("rabobank", "jaaroverzicht")


def test_requires_raisin_product_table_layout():
    assert classify("Raisin Financieel Jaaroverzicht 2024") is None

    classification = classify(
        "Raisin Financieel Jaaroverzicht 2024\n"
        "Raisin spaarproduct(en)\nKENMERK:\nOMSCHRIJVING:\nBronbelasting"
    )
    assert classification is not None
    assert (classification.issuer, classification.doc_type) == ("raisin", "jaaroverzicht")
