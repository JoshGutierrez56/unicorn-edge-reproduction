# Claims audit — arXiv:2511.12490v1

Source: Mainak Singha, *Discovery of a 13-Sharpe OOS Factor: Drift Regimes Unlock Hidden Cross-Sectional Predictability*, [version 1](https://arxiv.org/html/2511.12490v1). These findings concern the stated method and reported numbers, not the author's intent.

| Claim or design | Finding | Assessment |
|---|---|---|
| Table 2 combined Sharpe 13.19 | Explicit reconstruction: 0.5904 across the same half-open interpretation of three test years. | Not reproduced; unavailable author code/data prevent declaring an exact replication failure. |
| Table 1 final-window return 62%; Table 3 wealth $9.415M → $110.376M | The wealth step implies +1,072.34%. Even interpreting 62% as an arithmetic annual mean cannot produce an 11.72× one-year wealth multiple. | Numerically incompatible under the stated one-year definition. |
| Table 1 returns treated as geometric | `(1+2.067)(1+2.072)(1+.62) = 15.2634×`, not 110.376×. | This is an alternate interpretation check, not an assertion that arithmetic annual means compound directly. |
| Abstract: Sharpe above seven under ±30% parameter perturbations | Table 6 threshold perturbations include 3.2 and 4.1. | Internal claim/table mismatch. |
| About 35% active stock-days; Table 5 approximately 187 longs and 189 shorts | On a roughly 500-stock universe, 35% is roughly 175 stocks, not 376. Definitions/denominators may differ but are not reconciled. Our primary gate averages 9.60% of eligible names over selected test years. | Requires clarification; not a proof of an implementation error. |
| 100% gross and 50% per side imply market neutrality | They constrain dollars, not beta/sector exposures. A later training multiplier can raise gross above 100%. | Dollar-neutral is the supported description. No sector constraint appears in the stated implementation. |
| Historical 12% volatility / 15% drawdown scaling | Primary test volatility 17.35%; concatenated drawdown 24.41%. | Historical calibration is not a future risk guarantee. |
| Inverse share price as value | A split or a unit change can change cross-sectional rank with unchanged economic value. | A nominal-price signal, not a fundamental valuation measure. |
| Broad 2004–2024 evidence | Headline evaluation concatenates three one-year tests; other calendar years are not included in that headline. | Do not describe this as a continuous 21-year OOS strategy record. |
| Current constituents used backward | Missing former constituents and unavailable delisting histories create selection bias. | Neither this reconstruction nor the stated universe establishes investability. |

## Wealth-table arithmetic

Let daily simple returns be `r_t > -1`. Then `log(1+r_t) <= r_t`. For 253 daily observations and a 62% annualized arithmetic mean using 252 sessions/year:

```text
sum(r_t) = 0.62 × 253 / 252
wealth multiple <= exp(sum(r_t)) = 1.8635
Table 3 final-window multiple = 110.376 / 9.415 = 11.7234
```

This upper bound rules out the suggested arithmetic-versus-geometric reconciliation for that final one-year step. Other unreported definitions or corrections would require author clarification. Computed values are preserved in [paper-arithmetic.json](../results/2026-10-14/paper-arithmetic.json).

## What this audit does not establish

It does not establish misconduct, prove that every possible interpretation loses money, or identify the exact source of the original headline. It does establish that the reported arithmetic needs correction/clarification and that one documented implementation with meaningful tests does not produce the advertised result. An investment decision would require a point-in-time universe, contemporaneous prices, executable timing, financing/borrow treatment, and independent reproduction before relying on the strategy.
