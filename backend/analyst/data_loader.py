"""
data_loader.py - read the cached CSVs written by fetch_data.py into one object the optimiser uses.
"""
import json
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config

HERE = os.path.dirname(os.path.abspath(__file__))


@dataclass
class DataBundle:
    prices: pd.DataFrame            # daily adjusted closes, columns = asset ids (+ MKT)
    rf_annual: float                # latest 3m T-bill, fraction
    y10_annual: float               # latest 10y Treasury yield, fraction
    options: pd.DataFrame           # index = asset id
    events: pd.DataFrame            # past earnings events (asset, event_date, car_2day, ...)
    next_earnings: dict             # asset id -> pandas Timestamp or None
    token: dict                     # tokenized real estate inputs
    meta: dict                      # mode, retrieved_at, datasets, warnings
    asof: pd.Timestamp              # last price date
    warnings: list = field(default_factory=list)

    @property
    def is_synthetic(self):
        return self.meta.get("mode") == "SYNTHETIC"


def _latest(rates, col):
    if col not in rates or rates[col].dropna().empty:
        return None
    return float(rates[col].dropna().iloc[-1]) / 100.0


def load(data_dir=None):
    data_dir = data_dir or os.path.join(HERE, "data")
    if not os.path.exists(os.path.join(data_dir, "meta.json")):
        raise FileNotFoundError(f"No data in {data_dir}. Run: python fetch_data.py  "
                                f"(or python fetch_data.py --synthetic for test data)")
    meta = json.load(open(os.path.join(data_dir, "meta.json")))
    prices = pd.read_csv(os.path.join(data_dir, "prices.csv"), index_col="date", parse_dates=True)
    rates = pd.read_csv(os.path.join(data_dir, "rates.csv"), index_col="date", parse_dates=True)
    opts = pd.read_csv(os.path.join(data_dir, "options_iv.csv"))
    opts = opts.set_index("asset") if len(opts) else pd.DataFrame()
    ev = pd.read_csv(os.path.join(data_dir, "earnings_events.csv"))
    nxt = pd.read_csv(os.path.join(data_dir, "next_earnings.csv"))
    tok = pd.read_csv(os.path.join(data_dir, "token_re.csv")).iloc[0].to_dict()

    warnings = list(meta.get("warnings", []))
    rf, y10 = _latest(rates, "DTB3"), _latest(rates, "DGS10")
    if rf is None or y10 is None:
        raise ValueError("Missing DTB3 (3m T-bill) or DGS10 (10y yield) in rates.csv; re-run fetch_data.py")

    nxt_map = {r["asset"]: (pd.Timestamp(r["next_earnings_date"]) if pd.notna(r["next_earnings_date"]) else None)
               for _, r in nxt.iterrows()} if len(nxt) else {}

    asof = prices.index.max()
    age = (pd.Timestamp.today().normalize() - asof).days
    if not meta.get("mode") == "SYNTHETIC" and age > 5:
        warnings.append(f"Price data is {age} days old (last date {asof.date()}). Re-run fetch_data.py.")

    return DataBundle(prices=prices, rf_annual=rf, y10_annual=y10, options=opts, events=ev,
                      next_earnings=nxt_map, token=tok, meta=meta, asof=asof, warnings=warnings)
