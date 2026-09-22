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
| Revolut | Annual Flexible Cash Funds savings statement | Supplies earned return for the savings product. |
| Revolut | Personal current-account statement covering 1 January through 31 December | Supplies balances and flows. Revolut Business statements are not supported. |

## General limitations

- PDFs must contain extractable text. Image-only scans are not OCRed.
- CSV files and transaction exports are not supported.
- Interim statements are unsupported except for the listed flatex account
  statements.
- A changed institution template may require a parser update even when its
  statement name remains the same.

To add another institution or statement layout, follow the parser workflow in
[CONTRIBUTING.md](../CONTRIBUTING.md) and include synthetic, anonymized fixtures.
