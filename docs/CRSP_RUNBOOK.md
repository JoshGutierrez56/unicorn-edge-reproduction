# Reproduce the licensed-data follow-up

This is a retrospective diagnostic, **not** the author's exact extract and not a historical-membership reconstruction. [Read the frozen plan and amendments first](CRSP_FOLLOWUP_PLAN.md). A CRSP/WRDS subscription does not establish which vendor the author used.

## Acquire privately

Install Python 3.11+ and uv, then `uv sync --frozen --extra dev --extra wrds`. Configure your authorized WRDS username and a local libpq passfile; the script never embeds a password or prints credentials. Database sessions are read-only. The acquisition records bounded SQL, code/version hashes and yearly checksums. Interrupted downloads resume only when the specification and existing checksums match.

```sh
uv run --frozen --extra wrds python scripts/download_crsp.py --cache ../private-crsp
uv run --frozen python scripts/prepare_identity_review.py --cache ../private-crsp
```

Keep the cache and review **outside the repository**. Review every candidate in `../private-crsp/identity-review.json` against the frozen public company's issuer and share class. Replace each `PENDING` with `approved` or `excluded`, and document the evidence/reason and reviewer. Do not approve merely because a ticker string matches. Unknown identities remain excluded; do not select on realized returns. The runner refuses incomplete decisions, changed source hashes, duplicate IDs and silently substituted IDs.

The recorded extract yielded 495 provisional ticker matches, eight unmatched/ambiguous symbols, and three subsequently rejected issuer collisions. After review, 492 candidates remained; 490 had prices during 2003–2024. These counts describe this vintage, not a guarantee for future extracts. Review templates contain licensed identity metadata and must stay private.

The actual membership query was denied despite catalog visibility. The script records the denial; it does not bypass account permissions or fabricate intervals. A separate authorized membership source is required for a true historical-universe comparison.

## Freeze, evaluate, reconcile

Commit the reviewed implementation before evaluation. The runner refuses a dirty working tree and a nonempty output directory. It writes its case specification before loading market outcomes.

```sh
uv run --frozen pytest -q
uv run --frozen python scripts/run_crsp_followup.py --crsp ../private-crsp --yahoo ../private-prices --output ../crsp-study-reviewed
```

The Yahoo cache is acquired using the original repository workflow. Both providers use the same reviewed current-name intersection and signal-date observation mask. Their return lookbacks retain their own observed data. Quote-freeze cases share CRSP's quote availability. This controls several differences, but does not make the datasets identical or remove survivorship bias.

Strict cases report missing held returns. Separate stale-mark cases carry valuation across only verified `MP` intervals closed by `P1`/`P2` returns, freeze trading in unavailable securities, retain missing signal observations and absorb the full cumulative return on resumption. See the plan for the limitations of this convention. No true closing quote or daily return is fabricated.

Only aggregate coverage, portfolio returns, specifications, derived metrics and hashes are eligible for public release. Keep raw source rows, identifier mappings, review files and security-level outcomes private. A successful test suite verifies the implementation contracts; it does not establish an attractive investment strategy or author-result equivalence.
