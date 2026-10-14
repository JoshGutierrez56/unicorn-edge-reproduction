# Run ledger

The method and comparison set were committed before the first strategy run (`9d8baf9`, engine `b067b0e`). The paper's results were already known; this is not a preregistered or untouched holdout study.

- **Smoke primary:** completed using `b067b0e`. Three-window Sharpe 0.5904. This result was observed before running the full comparison set. No strategy parameters were changed in response.
- **Full study v1:** stopped when the strict 78% up-day threshold had no training variation. Completed prior case outputs are preserved privately. The original routine correctly refused to invent a leverage scale but stopped the entire batch.
- **Infrastructure amendment:** record each uncalibratable training window and omit that case's aggregate instead of stopping unrelated comparisons. Preserve partial-window outputs with `PARTIAL` in the filename. Do not substitute a scale, loosen a threshold, report a Sharpe for a constant series, or omit the failed case from the accounting. This changes batch failure reporting, not any signal, return, cost, stop, window, or calibrated result.
- **Full study v2:** uses the original 47 specified cases, with the explicit failure-reporting amendment. All results, including negative outcomes and the invalid same-day diagnostic, are retained. The latter is never a valid strategy estimate.
