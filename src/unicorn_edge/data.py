import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def load_cache(cache: Path, universe: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, dict]:
    receipt = json.loads((cache / "receipt.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(universe.read_bytes()).hexdigest()
    if digest != receipt["universe_sha256"]:
        raise ValueError("Membership snapshot differs from downloaded data receipt")
    frames = {}
    for symbol, entry in receipt["symbols"].items():
        if entry["status"] != "downloaded":
            continue
        path = cache / f"{symbol}.csv"
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Cache checksum mismatch: {symbol}")
        frame = pd.read_csv(path, index_col="Date", parse_dates=True)
        if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
            raise ValueError(f"Invalid provider dates: {symbol}")
        if ((frame[["Close","Adj Close"]] <= 0) | np.isinf(frame[["Close","Adj Close"]])).any().any():
            raise ValueError(f"Invalid observed price: {symbol}")
        frames[symbol] = frame
    if "SPY" not in frames:
        raise ValueError("SPY required to establish the observed US-equity session calendar")
    calendar = frames["SPY"].index
    symbols = pd.read_csv(universe)["Symbol"].astype(str).str.replace(".","-",regex=False).tolist()
    missing = [symbol for symbol in symbols if symbol not in frames]
    if set(missing) != {s for s,v in receipt["symbols"].items() if v["status"]=="failed"}:
        raise ValueError("Unrecorded missing symbols; acquisition manifest incomplete")
    close = pd.DataFrame({s:frames[s]["Close"] for s in symbols if s in frames}).reindex(calendar)
    adjusted = pd.DataFrame({s:frames[s]["Adj Close"] for s in close.columns}).reindex(calendar)
    return close, adjusted, frames["SPY"]["Adj Close"], receipt
