# Real market data is not the same as the author's exact dataset

The reconstruction uses real Yahoo market histories, not synthetic prices. However, the author's code, exact extract, constituent snapshot date and adjustment conventions were not obtained. Section 2.1 of the [paper](https://arxiv.org/html/2511.12490v1) describes daily prices for current S&P 500 constituents over 2004–2024 without identifying a vendor. The precise reason for the headline mismatch is therefore unresolved. Documented implementation and data differences are possible contributors, not an identified causal explanation.

## Obtain these before calling a follow-up an exact replication

1. Dated constituent/security-ID list, ticker mappings and the inclusion rule for incomplete histories.
2. Vendor/product, download date, fields, adjustment settings, currency and calendar.
3. Contemporaneous nominal prices for inverse-price ranking; explicit split/dividend treatment for both signal returns and P&L.
4. Exact daily weights, signal timestamps, execution timestamps and evaluation endpoints.
5. Code/version and daily return records for training scale, costs, shorts, cash, stops and final liquidation.
6. Definitions that reconcile the annual-return, volatility, Sharpe and wealth tables.

An independent investability study is a different task: it should additionally use historical constituent membership and delisted histories, executable fills, borrow availability, financing and realistic costs. These improvements need not increase returns or reproduce the paper's deliberately current-constituent sample.

## Access and cost, checked October 14, 2026 (Eastern)

- **Original extract:** unknown vendor and licensing; no defensible price quote is possible from the paper alone.
- **This Yahoo reconstruction:** no paid data subscription; provider availability, current-vintage adjustments and usage terms still apply. Raw provider histories are not redistributed.
- **Norgate US Stocks Platinum:** the [official package page](https://norgatedata.com/stockmarketpackages.php#usstocks) lists **USD 346.50 for six months / USD 630 for twelve months**, history back to 1990, delisted securities and historical index constituents. This is a possible independent data source, not the author's identified vendor. Package suitability, adjustment fields, licensing and current pricing must be checked before purchase.
- **Institutional CRSP/WRDS:** an existing authorized subscription may cover the required equity/history products without an additional individual purchase. Access is institution/product specific; no current entitlement or personal price has been assumed here.

The paper's Table 14 estimate of $5,000–10,000/month concerns a live level-one data operation, **not** the necessary cost of this historical daily-data test. Buying a dataset would not by itself resolve the paper's internal wealth-table arithmetic or unspecified execution logic. No paid data was purchased for this reproduction.
