"""Cache provider observations outside the public repository; never invent missing data."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--universe", type=Path, default=Path("docs/universe.csv"))
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    symbols = pd.read_csv(args.universe)["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
    symbols = list(dict.fromkeys(symbols + ["SPY"]))
    receipt_path = args.cache / "receipt.json"
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {
        "provider": "Yahoo Finance through yfinance", "yfinance_version": yf.__version__,
        "start": "2003-01-01", "end_exclusive": "2025-01-01",
        "universe_sha256": hashlib.sha256(args.universe.read_bytes()).hexdigest(), "symbols": {},
    }
    for i, symbol in enumerate(symbols, 1):
        destination = args.cache / f"{symbol}.csv"
        previous = receipt["symbols"].get(symbol, {})
        if destination.exists() and previous.get("sha256") == hashlib.sha256(destination.read_bytes()).hexdigest():
            continue
        error = None
        for attempt in range(2):
            try:
                frame = yf.download(symbol, start=receipt["start"], end=receipt["end_exclusive"],
                                    auto_adjust=False, progress=False, threads=False)
                if isinstance(frame.columns, pd.MultiIndex):
                    frame.columns = frame.columns.get_level_values(0)
                if frame.empty or not {"Close", "Adj Close"}.issubset(frame.columns):
                    raise ValueError("Provider returned no complete price schema")
                if frame.index.duplicated().any() or not frame.index.is_monotonic_increasing:
                    raise ValueError("Duplicate or unsorted provider dates")
                frame.to_csv(destination, index_label="Date", lineterminator="\n")
                receipt["symbols"][symbol] = {
                    "status": "downloaded", "rows": len(frame),
                    "first": str(frame.index.min().date()), "last": str(frame.index.max().date()),
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                    "missing_close": int(frame["Close"].isna().sum()),
                    "missing_adj_close": int(frame["Adj Close"].isna().sum()),
                }
                error = None
                break
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                if attempt == 0:
                    time.sleep(2)
        if error:
            receipt["symbols"][symbol] = {"status": "failed", "error": error}
        temporary = receipt_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        temporary.replace(receipt_path)
        print(f"{i}/{len(symbols)} {symbol}: {receipt['symbols'][symbol]['status']}", flush=True)
        time.sleep(0.2)
    failed = [s for s, v in receipt["symbols"].items() if v["status"] == "failed"]
    print(json.dumps({"symbols": len(symbols), "failed": failed}), flush=True)


if __name__ == "__main__":
    main()
