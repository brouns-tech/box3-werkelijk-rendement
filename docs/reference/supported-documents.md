# Supported documents

Werkelijk Rendement uses a positive allowlist. A PDF is imported only when its
extracted text matches a known template. Filenames and directory names do not
affect classification.

| Institution | Supported PDF statement | Use and limitations |
| --- | --- | --- |
| Belastingdienst | `Aangifte Inkomstenbelasting` copy containing `Eigen kopie, niet opsturen`, `Formulierenversie`, and `Burgerservicenummer`; supported final-assessment layout | Supplies aggregate Box 3 and filed tax figures, never the account inventory. |
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
| Revolut | Personal current-account statement covering 1 January through 31 December | Parses Current Account and Deposit separately; interest credits are separated from transfers. Amounts retain their source currency. Foreign-currency accounts require EUR conversion (including currency gains/losses) and remain incomplete for tax comparison. Revolut Business statements are not supported. |

## General limitations

- PDFs must contain extractable text. Image-only scans are not OCRed.
- CSV files and transaction exports are not supported.
- Interim statements are unsupported except for the listed flatex account
  statements.
- A changed institution template may require a parser update even when its
  statement name remains the same.

To add another institution or statement layout, follow the parser workflow in
[Contributing](../development/contributing.md) and include synthetic fixtures.

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

This follows the Belastingdienst's [investment return calculation](https://www.belastingdienst.nl/wps/wcm/connect/nl/box-3/content/rekenvoorbeelden-berekening-werkelijk-rendement)
and [2025 rule excluding expense deductions](https://www.belastingdienst.nl/wps/wcm/connect/fisin/fisin2025/Box_3_Werkelijk_rendement).
The updated processing profile requires existing imports to be scanned again;
reprocessing replaces the obsolete combined account record.
