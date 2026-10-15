# CRSP follow-up: separate data conventions from universe selection

Recorded before fetching or evaluating the follow-up market panel. The Yahoo results and paper were already observed. This is a diagnostic retrospective, not an untouched holdout or an exact replication. Read-only WRDS authentication and table/field availability were checked; no CRSP strategy outcomes were examined before this plan.

## Fixed questions

1. Does the reported result persist when the frozen strategy uses CRSP CIZ total returns and documented prices?
2. How much is attributable to nominal versus split-adjusted inverse-price ranking?
3. What changes when historical S&P 500 membership replaces a current-member sample?

## Data and pairing

- Retrieve January 2003–December 2024 daily observations from `crsp.dsf_v2`, security identities from `crsp.stksecurityinfohist`, membership intervals from `crsp.dsp500list` and the CRSP exchange calendar. Use permanent security identifiers, with explicit share-class checks. Record ambiguous and unmatched ticker mappings rather than silently substitute another security.
- Keep raw licensed rows, mappings and security-level results outside the public repository. Publish queries, acquisition metadata/hashes, coverage and derived aggregate strategy outcomes only.
- Use CIZ `dlyret` as the total return, including its distribution/delisting treatment; never add legacy `dlret` again. Inspect return-missing/duration/trading-status flags. Do not forward-fill missing held returns or turn special missing codes into zeros. A missing held return that cannot be resolved stops that case and is reported.
- Use absolute nominal `dlyprc` for one price variant, and `abs(dlyprc) / dlycumfacpr` for a separately labelled split-adjusted variant after checking the field convention and positive factors. Current-vintage adjustments do not recreate the author's extract.
- **Common-universe comparison:** resolve the original public membership snapshot to CRSP, intersect with available Yahoo securities, and rerun Yahoo on that same set. Report exclusions and date coverage. If providers have unequal histories, report a common-observation eligibility comparison rather than calling differing panels a pure source substitution.
- **Historical-membership comparison:** keep the same CRSP source/price convention and use dated membership eligibility for cross-sectional ranks, gating and weights. Permit trailing pre-membership observations for signal lookback when they exist. Respect the existing signal-to-execution lag for exits as well as entries. This changes universe selection and must not be described as reproducing the paper's current-constituent design.

## Frozen strategy comparisons

Retain the existing 63-session / greater-than-60% gate, ten-session reversal, 70/30 blend, proportional long/short weights, five-year training scale, trading-cost accounting and stop rules. Primary evaluation years remain 2010, 2015 and 2020, with additional retrospective annual checks 2010–2024 reported separately. No tuning to seek Sharpe 13.

For both the common current-member and historical-member experiments, report nominal and split-adjusted price variants; same-close optimistic execution and one extra execution day; primary blend, gated reversal and ungated blend; base 0.6 bp and 10 bp cost checks. Distinguish any uncalibratable or unresolved-data case from a completed run. Preserve the original Yahoo release unchanged.

## Verification and interpretation

Test historical-membership boundary dates, ticker/share-class ambiguity, direct CIZ returns versus reconstructed cumulative indices, split-factor treatment, lagged exits, and rejection of unresolved held returns. Reconcile aggregate returns against the independent share/cash challenger where applicable. Compare eligible counts and source coverage before attributing performance differences to the strategy.

Higher-quality data can strengthen the test without improving results. CRSP is not identified as the author's original vendor; even a matching headline would require the author's code and daily records to establish an exact replication.

## Access amendment before market-panel retrieval

The catalog exposed the `dsp500list` view, but the first actual membership query returned `permission denied for schema crsp_a_indexes`. Table visibility is not proof of licensed access. Record this refusal and continue only the separately specified current-constituent comparison when daily stock-data access succeeds. Historical-membership cases remain blocked unless an authorized source is obtained; an empty membership table is never treated as successful point-in-time reconstruction. No alternative membership history is invented or inferred from current constituents.

## Identity and missing-quote amendment, before the corrected comparison

The initial private diagnostic at code `10ec28a` exposed missing held returns and was **not accepted as a valid CRSP comparison**. An issuer-name review of all 495 ticker candidates found three different issuers behind the strings `BNY`, `ECHO` and `P`. Exclude these candidates from **both** providers rather than guess renamed-security IDs. The other 492 candidates have a reviewed issuer/share-class correspondence; two have no observations in the study interval, leaving 490 observed common names. The eight originally unmatched/ambiguous candidates remain excluded. An explicit, source-hashed private review is now mandatory. Original Yahoo results are unchanged; its P/ECHO histories were separately checked against the intended current companies, so the CRSP ticker collision is not evidence that those Yahoo histories were wrong.

Strict CRSP cases still fail on unresolved held returns. For a separate, explicitly modeled sensitivity, carry the last valuation across an `MP` missing-price interval **only** when the source documents a closing `P1` (two trading days) or `P2` (three trading days) cumulative return. Check consecutive calendar rows and missing-price/return flags. Apply that complete return upon resumption; do not claim observed daily zero returns. All other missing observations remain unresolved. CRSP's authorized `metaflaginfo` definitions were consulted; no cause such as a trading halt is inferred merely from `MP`.

During missing quotes, freeze actual holdings: no entries, exits, rebalancing or stop-liquidation trades in the unavailable security. Other securities can trade; do not renormalize locked exposure away. Apply fees only to executed notional. A stop remains pending on locked holdings and absorbs the eventual price move. Final liquidation fails if a required quote is still missing. Eligibility and signal lookbacks always use the original observed returns, never the modeled valuation zeros. Stale marks can understate intra-interval volatility; this sensitivity is not an executable-price reconstruction.

Run the same five declared strategy/cost/timing cases for six panels: Yahoo Close, strict CRSP nominal, strict CRSP split-adjusted, Yahoo with the same CRSP quote freeze, CRSP nominal with stale valuation/freeze, and CRSP split-adjusted with stale valuation/freeze. Also retain the separately labeled 2010–2024 annual restart analysis for all six. Publish blocked strict cases, not only completed variants. Freeze the amended code before observing these corrected outcomes. Do not optimize parameters or choose the price convention that produces a preferred Sharpe.
