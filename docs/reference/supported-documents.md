# Supported documents

Werkelijk Rendement uses a positive allowlist. A PDF is imported only when its
extracted text matches a known template. Filenames and directory names do not
affect classification.

| Institution | Supported PDF statement | Use and limitations |
| --- | --- | --- |
| Belastingdienst | `Aangifte Inkomstenbelasting` copy containing `Eigen kopie, niet opsturen`, `Formulierenversie`, and `Burgerservicenummer`; supported final-assessment layout | Supplies aggregate Box 3 and filed tax figures, never the account inventory. |
| Brand New Day | `Kwartaaloverzicht` with `Overzicht Ne kwartaal YYYY` for a `Beleggingsrekening` | Retains quarterly balances, net cash flow, reported net return and bank costs. The shared processor aggregates periods into annual summaries; missing quarters remain partial. Pension products are excluded from this template. |
| DEGIRO | `Jaaropgave` / `Jaaroverzicht` containing opening and closing portfolio totals | Supplies portfolio balances, deposits, withdrawals, and return components. |
| flatex | `Lijst met financiële klanteninstrumenten en klantenfondsen` dated 31 December | Supplies the year-end securities-and-cash inventory. Adjacent years are needed to derive a full-year value change. |
| flatex | `Rekeninguittreksel` | Used only for external transfers involving the configured linked bank account. Cash sweeps are excluded. |
| flatex | `Steuerbescheinigung` | Accepted as supplementary legacy income data; it is not a complete portfolio inventory. |
| ING | `Jaaroverzicht` for ING payment, savings, and credit-card products | Supplies account balances and reported interest. |
| Rabobank | `Financieel Jaaroverzicht` | Supplies account balances and reported interest. |
| SNS | `Jaaroverzicht Betalen, Sparen & Lenen`, `Financieel overzicht`, and `Totaaloverzicht Rekeningen` | The total overview supplies balances; savings accounts without a reported interest figure remain incomplete. |
| Raisin | `Raisin Financieel Jaaroverzicht` | Supplies savings-product balances, interest, and withholding tax. |
| Revolut | `Annual Financial Summary` | Supplies annual account data. |
| Revolut | Annual `Flexible Cash Funds Statement` | Parses each fund overview separately, using portfolio number and fund currency for identity and retaining all underlying account numbers. Supports EUR-only and USD/GBP plus EUR columns, signed amounts, and four-decimal returns/fees. Complete, reconciled summaries supply gross return including EUR currency value changes; missing or inconsistent summaries remain incomplete. Service fees are retained separately and are not deducted. |
| Revolut | Personal current-account statement covering 1 January through 31 December | Parses Current Account and Deposit separately; interest credits are separated from transfers. Amounts retain their source currency. Reconciled USD cash transactions can be valued in EUR using lazily downloaded and locally cached ECB daily rates, including currency gains/losses. Missing transactions, unavailable rates and other unconverted currencies remain incomplete. Revolut Business statements are not supported. |

## General limitations

- PDFs must contain extractable text. Image-only scans are not OCRed.
- CSV files and transaction exports are not supported.
- Interim statements are unsupported except for the listed Brand New Day quarterly
  reports and flatex account statements.
- A changed institution template may require a parser update even when its
  statement name remains the same.

To add another institution or statement layout, follow the parser workflow in
[Contributing](../development/contributing.md) and include synthetic fixtures.

## Period reports and annual summaries

Adapters can emit dated `AccountPeriodFact` records instead of annual facts.
The shared processor supports arbitrary inclusive date ranges within one calendar
year, including daily, monthly and quarterly reports. Original periods are kept
separately from regenerated annual facts. Cross-year ranges must be split using
dated source evidence; amounts are never prorated.

Flows and returns are summed over selected periods. Annual opening and closing
balances are taken only from periods reaching 1 January and 31 December.
Unknown flows remain unknown; a reported net cash flow is retained separately
and does not establish gross deposits or withdrawals. Exact duplicate periods
count once. Overlapping periods are never added together and leave a warning;
gaps, missing returns and balance discontinuities also leave coverage partial.
Native annual evidence takes precedence for the same account and year.

A leading gap is treated as an account-opening assumption when the earliest
available report for that account starts with exactly EUR 0.00 and there is no
earlier period or annual evidence. The annual opening balance is then assumed
to be zero. This creates a typed `assumption` notification, displayed as an
informational message and included in audit exports; it does not reduce coverage.
Nonzero, unknown or foreign-currency opening balances, earlier account evidence,
interior gaps and missing year-end periods still produce coverage warnings.

Brand New Day return totals use the quarterly net return plus separately charged
bank costs, retaining both original amounts for audit. The indicative gross
return, which also reverses embedded fund costs, is not substituted for portfolio
value changes. Q4's annual costs page is not counted as another period. This is
consistent with the [expense treatment in the existing return calculation](https://www.belastingdienst.nl/wps/wcm/connect/nl/box-3/content/wat-is-mijn-werkelijk-rendement).
Audit bundles include `source_period_facts.csv` when dated evidence is present;
annual summaries reference every contributing source period and document.

## Flexible Cash Funds return calculation

The overview's earned return is gross; service fees, sold value, withdrawn
return, and reinvested return are signed negative amounts. Purchases include
reinvested returns. Each overview must reconcile in its fund currency:

`closing = opening + purchased + sold + earned + fees + withdrawn return + reinvested return`

Using the overview's EUR column, the taxable return is calculated as:

`closing - opening - purchased - sold - withdrawn return - reinvested return - fees`

This removes internal reinvestment from external contributions, includes
withdrawn income, and adds back separately charged service fees. The difference
between this result and the EUR gross earned return is retained as the currency
value change. Original summary amounts retain their precision; year totals are
rounded to cents. The generic `earned_return` method stores the complete return,
while `extra` retains gross income, fees, net income, currency value change, and
the original summary columns for audit.

The account table shows earned return, currency gain/loss, and effective return
separately. The overview header contains only coverage and source count. EUR holdings have zero
currency impact. Other investment value changes are shown separately from
earned income; unconverted foreign-currency results remain unknown in EUR.

This follows the Belastingdienst's [investment return calculation](https://www.belastingdienst.nl/wps/wcm/connect/nl/box-3/content/rekenvoorbeelden-berekening-werkelijk-rendement)
and [2025 rule excluding expense deductions](https://www.belastingdienst.nl/wps/wcm/connect/fisin/fisin2025/Box_3_Werkelijk_rendement).
The updated processing profile requires existing imports to be scanned again;
reprocessing replaces the obsolete combined account record.
