# Implementation plan frozen before the first strategy run

Recorded 2026-10-14. This is an independently implemented methodological reproduction of Mainak Singha, *Discovery of a 13-Sharpe OOS Factor*, [arXiv:2511.12490v1](https://arxiv.org/abs/2511.12490), not an exact replication or a newly discovered untouched holdout. The paper and its results were already read. No author code, exact vendor extract, universe freeze date, or complete portfolio return series was available when this plan was written.

## Base interpretation

- Current S&P 500 snapshot: datasets/s-and-p-500-companies commit `36472b57910842f4025e8ca8303b93a692d2bbae` (2026-10-09). This deliberately biased reconstruction follows the paper's current-constituent design but cannot match its unspecified list. Report missing and prelisting observations; do not call this point-in-time membership.
- Download Yahoo daily observations 2003-01-01 through 2024-12-31, retaining source hashes and timestamps privately. Publish only derived aggregate results and the allowed membership snapshot, not provider price histories.
- Primary price signal uses Yahoo Close (split-adjusted by the provider); total-return P&L uses Adj Close. Primary reversal and up-day count use total returns. Compare using Adj Close for inverse-price ranking and using Close returns for signals. Neither is raw contemporaneous nominal price, and backward adjustments remain a limitation.
- Value: daily percentile rank of inverse price. Reversal: negative ten-session compounded return, cross-sectionally standardized. Base score: 0.7 value + 0.3 reversal.
- Regime: more than 60% positive returns in the 63 observations strictly before the signal date, matching equation 2's t-k indexing. Require a complete window; missing data never count as negative returns.
- Standardize nonzero gated base scores over eligible names. Allocate proportional to positive/negative standardized scores, each side totaling 0.5 absolute weight. No position if either side is absent. Equal-side weights are a specified sensitivity, not a replacement chosen after seeing performance.
- Signals at close t earn returns only after close t. Primary reproduction assumes same-close signal execution (optimistic execution convention, not a claimed achievable fill). A full extra trading-day lag is the principal execution sensitivity. Diagnostic same-day return alignment is intentionally invalid and must be labeled leakage, never included as a valid strategy.
- Rebalance daily. Compute pretrade drifted weights using previous holdings and realized returns; trading costs are 0.6 basis point per dollar bought or sold, including entries, exits and liquidation. Solve self-financing costs against post-cost NAV. No turnover from merely relabeling weights. Cash earns zero in the base case; shorts, financing and borrow fees are additional limitations and sensitivities.
- Training scale min(0.12 / annualized volatility, 0.15 / absolute maximum drawdown), fit only on each training period's unscaled net returns. Allow leverage above 1 as the paper does; additionally report a scale capped at 1. Do not refit the scale within the test year.
- Primary windows use half-open calendar dates: 2005-01-01 to 2010-01-01 train / 2010 calendar year test; 2010 to 2015 train / 2015 test; 2015 to 2020 train / 2020 test. Also run test years 2011, 2016 and 2021 to expose the endpoint ambiguity. Concatenating three separated years does not form a continuous 21-year track record.
- Stop the strategy after a 30% drawdown or a trailing 63-session loss of 10%; trigger after observing the breach, liquidate with costs, and remain in cash for that evaluation period. The paper's additional volatility/correlation switch details are insufficiently specified and are not silently invented.

## Comparisons and robustness specified in advance

Ungated blend; gated inverse-price only; gated reversal only; matched daily-count random gates across fixed seeds; equal-weight available universe and SPY total-return benchmark. Compare one-day delayed execution, equal side weighting, signal adjustment conventions, two-times cost, 10bp cost, 100bp annual short borrow, leverage capped at 1, gate threshold/window changes, and alternative endpoint years. Report all specified runs, not only winners. Do not tune parameters to recover the headline Sharpe.

## Verification and interpretation

Hand-derived holdings/cost fixtures; independent daily NAV reconciliation; future-data perturbation; signal/gate timing; missing-observation failures; exposure and cash conservation; metric and wealth-table arithmetic. Report arithmetic annual mean, geometric cumulative return/CAGR, annual volatility, arithmetic-mean Sharpe, maximum drawdown including initial NAV, turnover, exposure, active count, and stop events. Benchmark claims should reconcile to their own daily return series.

Reproduction success means the described method is faithfully implemented under explicit assumptions, not that the reported results are guaranteed to match. A failed reproduction is evidence against relying on the headline, not proof of misconduct or a proof that no alternative author implementation could work. Current membership, unavailable delisted histories, public-data adjustments and execution assumptions prevent a fully unbiased investability assessment.
