# Understand the overview

The header shows coverage status and the number of statement sources. Financial
figures appear in the tables, alongside their account or taxpayer context.

Coverage uses both color and a text label:

- **Green — Ready to review:** all imported Box 3 accounts have usable return
  data in EUR.
- **Yellow — Needs attention:** return data or currency conversion is missing.
- **Gray — No data yet:** no eligible Box 3 account evidence is available.

These statuses concern imported accounts only. They do not establish that every
account or asset has been supplied. No current coverage status represents a hard
failure; red is reserved for actual errors.

Select **Tax year** in **Overview**, then work through these sections:

1. **Coverage** and warnings: establish which evidence is present and which
   accounts or figures are missing or partial. An actual-return amount can be a
   known subtotal while the overall result remains indeterminate.
   **Ready to review** means the imported Box 3 statements have usable return
   fields; it does not establish that all your assets or tax-return evidence are present.
2. **Decision overview**: inspect the actual-return and fictitious-return
   comparison, taxpayer allocation, and result status. A missing-data or
   manual-review status is not a definitive recommendation.
3. **Account overview**: check account holders, individual/joint allocation,
   Box 3 inclusion, opening and closing values, interest, dividends, and
   calculated return against the original statements.
   Blue and green identify the two primary taxpayers; purple identifies joint
   and child accounts. Non-Box-3 records use half the color intensity and remain
   visible for checking, but are excluded from Box 3 totals.
4. **Import diagnostics**: review counts of parsed, skipped, and failed documents
   by institution and document type. Return to **Documents** for document details.

Policies are implemented for 2017–2025. Later years require manual review rather
than a guessed future policy. Unsupported assets or incomplete partner coverage
may also prevent a meaningful tax comparison. Importing every PDF in your folder
cannot establish completeness of your entire financial situation.
Both fiscal partners remain visible when their taxable base or allocation is
missing. A missing figure requires review; it is not treated as a zero taxable base.

Choose **Download audit export** to save a ZIP for the selected year. It includes
yearly totals, asset calculations, source facts, and tax results. Use it alongside
the original PDFs to inspect the inputs and calculation assumptions.

## Currency conversion

Original cash-account amounts retain their source currency. For supported Revolut
USD Current Account and Deposit statements, the app can derive EUR values from
dated transactions and historical ECB daily reference rates. It first reconciles
every transaction balance and the product's annual totals. Missing or inconsistent
transactions remain incomplete; annual totals alone are insufficient for conversion.
Other unsupported foreign-currency layouts remain incomplete too.

When rates are needed, import or recalculation downloads the USD series for that
completed tax year, including preceding dates needed for the opening balance.
The rates are cached locally; accounts already expressed in EUR do not trigger a
download. For weekends and holidays the app uses the latest preceding published
rate, at most seven days old. It never uses a future observation. ECB rates are
USD per EUR, so dollar amounts are divided by the rate.

Opening and closing balances are valued on 1 January and 31 December. Each cash
movement and interest credit is valued on its date. Credited interest is excluded
from external deposits, so it is counted once in effective return:

`effective EUR return = closing EUR balance - opening EUR balance - EUR deposits + EUR withdrawals`

`currency gain/loss = effective EUR return - EUR interest`

Same-date transfers between Current Account and Deposit cancel in their combined
return. Calculations use decimal arithmetic, with totals rounded to cents after
conversion. This does not reconstruct missing earlier fund statements or certify
that all assets are present. The EUR comparison remains incomplete if a needed
rate cannot be obtained. Rescan or recalculate to retry after a network failure.

The audit ZIP includes `fx_conversions.csv` with transaction and rate dates,
original USD amounts, rates, unrounded EUR values, source URL, retrieval time,
and response checksum. Source facts retain USD amounts; `eur_*` columns supply
their EUR valuations, and `return_used` is in EUR.

Reference rates are valuations, not a claim about the bank's executed exchange
price. See the [ECB reference rates](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html)
and [historical API examples](https://data.ecb.europa.eu/help/api/data-examples).
