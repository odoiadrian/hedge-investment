#!/usr/bin/env python3
"""
fetch_data.py - pull the free public data for the demo universe and cache it as CSV + Excel.

    python fetch_data.py                 # real data (needs normal internet access)
    python fetch_data.py --synthetic     # SYNTHETIC test data, clearly labelled, for offline development

Outputs (in ./data):
    prices.csv           daily adjusted closes, one column per asset_id (+ MKT benchmark)
    rates.csv            FRED series (DGS10, DTB3, spot oil/gas cross-checks)
    options_iv.csv       ATM IV, skew, term slope, implied move per optionable equity (snapshot)
    earnings_events.csv  past earnings events with 2-day abnormal return
    next_earnings.csv    next scheduled earnings date per equity
    token_re.csv         tokenized real estate token inputs (from inputs/token_re.json)
    meta.json            mode, retrieval time, per-dataset status and warnings
    data_pack.xlsx       everything above + Source_Register + Assumptions (built by build_excel.py)
"""
import argparse
import datetime as dt
import io
import json
import os
import sys

import numpy as np
import pandas as pd

from . import config

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (hackathon research prototype)"}
OPTION_COLS = ["asset", "asof", "spot", "expiry_30", "dte_30", "atm_iv_30", "expiry_60", "dte_60", "atm_iv_60",
               "skew_30", "term_slope", "atm_straddle_pct_30", "atm_open_interest_30", "atm_rel_spread_30", "source"]
EVENT_COLS = ["asset", "event_date", "eps_estimate", "eps_reported", "surprise_pct", "car_2day", "source"]
NEXT_COLS = ["asset", "next_earnings_date", "source"]


def now_utc():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


# ------------------------------------------------------------------------------------------
# REAL DATA
# ------------------------------------------------------------------------------------------
def fetch_prices(meta):
    import yfinance as yf
    tick_to_id = {v["ticker"]: k for k, v in config.UNIVERSE.items() if v["ticker"]}
    tick_to_id[config.BENCHMARK_TICKER] = "MKT"
    tickers = list(tick_to_id)
    raw = yf.download(tickers, period=config.HISTORY_PERIOD, auto_adjust=True, progress=False,
                      group_by="column", threads=False)
    if raw is None or len(raw) == 0 or "Close" not in raw:
        raise RuntimeError("Yahoo Finance returned no price data (no internet access, blocked network, or rate limit). "
                           "Try again on a normal connection, or use --synthetic for offline test data.")
    close = raw["Close"]
    close = close.rename(columns=tick_to_id)
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close = close.sort_index().dropna(how="all")
    missing = [i for i in tick_to_id.values() if i not in close.columns or close[i].dropna().empty]
    if missing:
        raise RuntimeError(f"No price data returned for required assets: {missing}. Retry the refresh.")
    close = close.ffill(limit=3)
    meta["datasets"]["prices"] = dict(status="OK" if not missing else "PARTIAL",
                                      source="Yahoo Finance via yfinance", rows=len(close),
                                      first=str(close.index.min().date()), last=str(close.index.max().date()))
    return close


def _fred_csv(series_id):
    import requests
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    date_col = df.columns[0]
    s = pd.to_numeric(df[series_id], errors="coerce")
    s.index = pd.to_datetime(df[date_col])
    s.name = series_id
    return s.dropna()


def fetch_rates(meta, prices_ref=None):
    out, used = {}, {}
    for sid in config.FRED_SERIES:
        try:
            out[sid] = _fred_csv(sid)
            used[sid] = "FRED"
        except Exception as e:  # noqa: BLE001
            meta["warnings"].append(f"FRED {sid} failed: {e}")
    # Yahoo fallback for the two rates the model actually needs
    import yfinance as yf
    for sid, tick in config.YAHOO_RATE_FALLBACK.items():
        if sid not in out:
            try:
                h = yf.download(tick, period=config.HISTORY_PERIOD, auto_adjust=False, progress=False)
                s = h["Close"].squeeze()
                s.index = pd.to_datetime(s.index).tz_localize(None)
                s.name = sid
                out[sid] = s.dropna()
                used[sid] = f"Yahoo Finance fallback ({tick}, percent)"
            except Exception as e:  # noqa: BLE001
                meta["warnings"].append(f"Yahoo fallback {tick} failed: {e}")
    rates = pd.concat(out.values(), axis=1).sort_index() if out else pd.DataFrame()
    meta["datasets"]["rates"] = dict(status="OK" if {"DGS10", "DTB3"} <= set(out) else "PARTIAL",
                                     source=used, last=str(rates.index.max().date()) if len(rates) else None)
    return rates


def _nearest(df, col, target):
    i = (df[col] - target).abs().idxmin()
    return df.loc[i]


def _pick_expiries(expiries, today):
    cand = []
    for e in expiries:
        dte = (pd.Timestamp(e) - today).days
        if dte >= 7:
            cand.append((e, dte))
    if not cand:
        return None, None
    e30 = min(cand, key=lambda x: abs(x[1] - 30))
    rest = [c for c in cand if c[0] != e30[0]]
    e60 = min(rest, key=lambda x: abs(x[1] - 60)) if rest else None
    return e30, e60


def _atm_iv(calls, puts, spot):
    c, p = _nearest(calls, "strike", spot), _nearest(puts, "strike", spot)
    ivs = [x for x in (c["impliedVolatility"], p["impliedVolatility"]) if x and x > 0.01]
    iv = float(np.mean(ivs)) if ivs else np.nan
    return iv, c, p


def fetch_options(prices, meta):
    import yfinance as yf
    today = pd.Timestamp.today().normalize()
    rows = []
    for aid, u in config.UNIVERSE.items():
        if not u.get("options"):
            continue
        try:
            t = yf.Ticker(u["ticker"])
            spot = float(prices[aid].dropna().iloc[-1])
            e30, e60 = _pick_expiries(t.options, today)
            if e30 is None:
                raise RuntimeError("no expiries >= 7 days")
            ch30 = t.option_chain(e30[0])
            iv30, c30, p30 = _atm_iv(ch30.calls, ch30.puts, spot)
            put95 = _nearest(ch30.puts, "strike", 0.95 * spot)["impliedVolatility"]
            call105 = _nearest(ch30.calls, "strike", 1.05 * spot)["impliedVolatility"]
            skew = float(put95 - call105)
            mid_c = (c30["bid"] + c30["ask"]) / 2 if c30["ask"] > 0 else c30["lastPrice"]
            mid_p = (p30["bid"] + p30["ask"]) / 2 if p30["ask"] > 0 else p30["lastPrice"]
            implied_move = float((mid_c + mid_p) / spot)
            spread = float((c30["ask"] - c30["bid"]) / mid_c) if mid_c and c30["ask"] > 0 else np.nan
            iv60 = np.nan
            if e60:
                ch60 = t.option_chain(e60[0])
                iv60, _, _ = _atm_iv(ch60.calls, ch60.puts, spot)
            rows.append(dict(asset=aid, asof=now_utc(), spot=spot, expiry_30=e30[0], dte_30=e30[1],
                             atm_iv_30=iv30, expiry_60=e60[0] if e60 else None,
                             dte_60=e60[1] if e60 else None, atm_iv_60=iv60, skew_30=skew,
                             term_slope=(iv60 - iv30) if pd.notna(iv60) else np.nan,
                             atm_straddle_pct_30=implied_move, atm_open_interest_30=float(c30["openInterest"]),
                             atm_rel_spread_30=spread, source="Yahoo Finance via yfinance option_chain()"))
        except Exception as e:  # noqa: BLE001
            meta["warnings"].append(f"Options {aid} failed: {e}")
    df = pd.DataFrame(rows, columns=OPTION_COLS) if not rows else pd.DataFrame(rows)
    meta["datasets"]["options_iv"] = dict(status="OK" if len(df) == sum(
        1 for u in config.UNIVERSE.values() if u.get("options")) else "PARTIAL",
        source="Yahoo Finance via yfinance", rows=len(df))
    return df


def _car_2day(px, mkt, event_date):
    """Market-adjusted return from the close before the event date to the close after it."""
    common = pd.concat([px.rename("asset"), mkt.rename("market")], axis=1).dropna()
    px, mkt = common["asset"], common["market"]
    before = px.index[px.index < event_date]
    after = px.index[px.index > event_date]
    if len(before) == 0 or len(after) == 0:
        return np.nan
    i0, i1 = before[-1], after[0]
    r_s = px[i1] / px[i0] - 1
    r_m = mkt[i1] / mkt[i0] - 1
    return float(r_s - r_m)


def fetch_earnings(prices, meta):
    import yfinance as yf
    today = pd.Timestamp.today().normalize()
    ev_rows, nxt_rows = [], []
    for aid, u in config.UNIVERSE.items():
        if not u.get("options"):   # only equities have earnings
            continue
        try:
            ed = yf.Ticker(u["ticker"]).get_earnings_dates(limit=16)
            if ed is None or ed.empty:
                raise RuntimeError("empty earnings table")
            idx = pd.to_datetime(ed.index).tz_localize(None).normalize()
            ed = ed.copy()
            ed.index = idx
            px, mkt = prices[aid].dropna(), prices["MKT"].dropna()
            for d, r in ed.iterrows():
                reported = r.get("Reported EPS")
                if pd.notna(reported) and d < today:
                    ev_rows.append(dict(asset=aid, event_date=d.date(), eps_estimate=r.get("EPS Estimate"),
                                        eps_reported=reported, surprise_pct=r.get("Surprise(%)"),
                                        car_2day=_car_2day(px, mkt, d),
                                        source="Yahoo Finance via yfinance get_earnings_dates()"))
            future = [d for d, r in ed.iterrows() if d >= today and pd.isna(r.get("Reported EPS"))]
            nxt_rows.append(dict(asset=aid, next_earnings_date=min(future).date() if future else None,
                                 source="Yahoo Finance via yfinance get_earnings_dates()"))
        except Exception as e:  # noqa: BLE001
            meta["warnings"].append(f"Earnings {aid} failed: {e}")
    ev = pd.DataFrame(ev_rows, columns=EVENT_COLS) if not ev_rows else pd.DataFrame(ev_rows)
    nxt = pd.DataFrame(nxt_rows, columns=NEXT_COLS) if not nxt_rows else pd.DataFrame(nxt_rows)
    meta["datasets"]["earnings"] = dict(status="OK" if len(nxt) else "FAILED",
                                        source="Yahoo Finance via yfinance", events=len(ev))
    return ev, nxt


def load_token(meta):
    path = os.path.join(HERE, "inputs", "token_re.json")
    with open(path) as f:
        tok = json.load(f)
    if tok.get("is_placeholder"):
        meta["warnings"].append("TOKEN_RE is a PLACEHOLDER - copy a real token's yield/TVL/holders from "
                                "https://app.rwa.xyz into inputs/token_re.json and set is_placeholder=false.")
    meta["datasets"]["token_re"] = dict(status="PLACEHOLDER" if tok.get("is_placeholder") else "MANUAL_ENTRY",
                                        source="RWA.xyz dashboard (manual)")
    return pd.DataFrame([tok])


# ------------------------------------------------------------------------------------------
# SYNTHETIC DATA (for offline development / testing only - never present as real)
# ------------------------------------------------------------------------------------------
def make_synthetic(meta, seed=7):
    rng = np.random.default_rng(seed)
    ids = ["MSFT", "JNJ", "JPM", "PG", "CAT", "WTI", "NATGAS", "UST10", "REIT", "MKT"]
    beta = np.array([1.10, 0.55, 1.15, 0.50, 1.20, 0.35, 0.10, -0.10, 0.90, 1.00])
    idio = np.array([0.011, 0.008, 0.009, 0.007, 0.010, 0.020, 0.030, 0.0035, 0.008, 0.0])
    drift = np.array([0.12, 0.05, 0.10, 0.04, 0.09, 0.02, 0.00, 0.02, 0.05, 0.09]) / 252
    n = 1260
    dates = pd.bdate_range(end=pd.Timestamp("2026-10-23"), periods=n)
    mkt = rng.normal(0.0, 0.0085, n)
    rets = np.outer(mkt, beta) + rng.normal(0, 1, (n, len(ids))) * idio + drift
    px = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates, columns=ids)

    rates = pd.DataFrame({"DGS10": 4.20 + rng.normal(0, 0.02, n).cumsum() * 0.1,
                          "DTB3": 3.90 + rng.normal(0, 0.01, n).cumsum() * 0.1}, index=dates)

    hist_vol = px.pct_change().std() * np.sqrt(252)
    opt_rows = []
    for aid in [k for k, v in config.UNIVERSE.items() if v.get("options")]:
        iv30 = float(hist_vol[aid] * rng.uniform(0.95, 1.25))
        opt_rows.append(dict(asset=aid, asof=now_utc(), spot=float(px[aid].iloc[-1]),
                             expiry_30="SYNTHETIC", dte_30=30, atm_iv_30=iv30, expiry_60="SYNTHETIC",
                             dte_60=60, atm_iv_60=iv30 * rng.uniform(0.97, 1.05),
                             skew_30=float(rng.uniform(0.0, 0.06)), term_slope=float(rng.uniform(-0.01, 0.02)),
                             atm_straddle_pct_30=float(iv30 * np.sqrt(30 / 365) * 0.8),
                             atm_open_interest_30=float(rng.integers(500, 20000)),
                             atm_rel_spread_30=float(rng.uniform(0.01, 0.06)), source="SYNTHETIC"))
    opts = pd.DataFrame(opt_rows)

    ev_rows, nxt_rows = [], []
    offsets = {"MSFT": 5, "JNJ": 78, "JPM": 82, "PG": 7, "CAT": 70}
    today = pd.Timestamp("2026-10-23")
    for aid, off in offsets.items():
        for q in range(1, 13):
            d = today + pd.Timedelta(days=off) - pd.Timedelta(days=91 * q)
            ev_rows.append(dict(asset=aid, event_date=d.date(), eps_estimate=np.nan, eps_reported=np.nan,
                                surprise_pct=float(rng.normal(3, 5)), car_2day=float(rng.normal(0.004, 0.035)),
                                source="SYNTHETIC"))
        nxt_rows.append(dict(asset=aid, next_earnings_date=(today + pd.Timedelta(days=off)).date(),
                             source="SYNTHETIC"))
    meta["datasets"] = {k: dict(status="SYNTHETIC", source="SYNTHETIC test data") for k in
                        ["prices", "rates", "options_iv", "earnings", "token_re"]}
    meta["warnings"].append("ALL DATA IS SYNTHETIC. For development only. Do not present as real.")
    return px, rates, opts, pd.DataFrame(ev_rows), pd.DataFrame(nxt_rows)


# ------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true", help="generate labelled synthetic test data")
    ap.add_argument("--out", default=os.path.join(HERE, "data"))
    ap.add_argument("--no-excel", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    meta = dict(mode="SYNTHETIC" if args.synthetic else "REAL", retrieved_at=now_utc(),
                datasets={}, warnings=[])

    if args.synthetic:
        prices, rates, opts, events, nxt = make_synthetic(meta)
        token = load_token(meta)
        meta["datasets"]["token_re"] = dict(status="PLACEHOLDER", source="inputs/token_re.json")
    else:
        try:
            prices = fetch_prices(meta)
            rates = fetch_rates(meta)
            if not {"DGS10", "DTB3"} <= set(rates.columns):
                raise RuntimeError("Could not get the 10y yield (DGS10) and 3m bill rate (DTB3) from FRED or Yahoo.")
            opts = fetch_options(prices, meta)
            events, nxt = fetch_earnings(prices, meta)
            token = load_token(meta)
        except Exception as e:  # noqa: BLE001
            print(f"\nERROR: real data could not be fetched: {e}")
            for w in meta["warnings"]:
                print("  -", w)
            print("Nothing was written. Fix the connection, or run:  python fetch_data.py --synthetic")
            return 2

    prices.to_csv(os.path.join(args.out, "prices.csv"), index_label="date")
    rates.to_csv(os.path.join(args.out, "rates.csv"), index_label="date")
    opts.to_csv(os.path.join(args.out, "options_iv.csv"), index=False)
    events.to_csv(os.path.join(args.out, "earnings_events.csv"), index=False)
    nxt.to_csv(os.path.join(args.out, "next_earnings.csv"), index=False)
    token.to_csv(os.path.join(args.out, "token_re.csv"), index=False)
    with open(os.path.join(args.out, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2, default=str)

    print(f"mode={meta['mode']}  prices={prices.shape}  options={len(opts)}  earnings events={len(events)}")
    for k, v in meta["datasets"].items():
        print(f"  {k:12s} {v.get('status')}")
    for w in meta["warnings"]:
        print("  WARNING:", w)

    if not args.no_excel:
        from . import build_excel
        path = build_excel.build(args.out)
        print("Excel written:", path)


if __name__ == "__main__":
    sys.exit(main())
