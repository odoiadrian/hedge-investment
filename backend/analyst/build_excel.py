"""
build_excel.py - turn the cached CSVs in ./data into data_pack.xlsx with a source line on every sheet.

Run standalone:  python build_excel.py [data_dir]
Called automatically by fetch_data.py.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import config

HERE = os.path.dirname(os.path.abspath(__file__))
HDR_FILL = PatternFill("solid", fgColor="4B2E83")
HDR_FONT = Font(bold=True, color="FFFFFF")
WARN_FILL = PatternFill("solid", fgColor="FFC7CE")
NOTE_FONT = Font(italic=True, color="444444")


def _read(data_dir, name, **kw):
    p = os.path.join(data_dir, name)
    return pd.read_csv(p, **kw) if os.path.exists(p) else pd.DataFrame()


def compute_stats(prices, rates):
    ret = np.log(prices / prices.shift(1)).dropna(how="all")
    out = []
    lb = config.A("momentum_lookback_days")
    mkt = ret["MKT"] if "MKT" in ret else None
    for c in prices.columns:
        r = ret[c].dropna()
        row = dict(asset=c, last_price=prices[c].dropna().iloc[-1], first_date=prices[c].dropna().index.min().date(),
                   last_date=prices[c].dropna().index.max().date(), obs=len(r),
                   ann_vol=r.std() * np.sqrt(252),
                   momentum_120d=prices[c].dropna().iloc[-1] / prices[c].dropna().iloc[-1 - lb] - 1
                   if len(prices[c].dropna()) > lb else np.nan)
        if mkt is not None and c != "MKT":
            j = pd.concat([r.tail(252), mkt.tail(252)], axis=1).dropna()
            row["beta_1y_vs_MKT"] = j.iloc[:, 0].cov(j.iloc[:, 1]) / j.iloc[:, 1].var() if len(j) > 60 else np.nan
        out.append(row)
    return pd.DataFrame(out)


def _write(writer, df, sheet, source_line, mode, index=False):
    df.to_excel(writer, sheet_name=sheet, startrow=2, index=index)
    ws = writer.sheets[sheet]
    ws["A1"] = ("SYNTHETIC TEST DATA - NOT REAL MARKET DATA.  " if mode == "SYNTHETIC" else "") + source_line
    ws["A1"].font = Font(bold=True) if mode != "SYNTHETIC" else Font(bold=True, color="9C0006")
    if mode == "SYNTHETIC":
        ws["A1"].fill = WARN_FILL
    ncols = (len(df.columns) + (1 if index else 0))
    for c in range(1, ncols + 1):
        cell = ws.cell(row=3, column=c)
        cell.fill, cell.font = HDR_FILL, HDR_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        width = max(12, min(48, int(max([len(str(cell.value))] + [len(str(v)) for v in
                                         df.iloc[:200, c - 1 - (1 if index else 0)].astype(str)]
                                        if c - 1 - (1 if index else 0) >= 0 else [14]) * 1.1)))
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.freeze_panes = "A4"
    return ws


def build(data_dir=None, out_name="data_pack.xlsx"):
    data_dir = data_dir or os.path.join(HERE, "data")
    meta = json.load(open(os.path.join(data_dir, "meta.json")))
    mode = meta["mode"]
    prices = pd.read_csv(os.path.join(data_dir, "prices.csv"), index_col="date", parse_dates=True)
    rates = _read(data_dir, "rates.csv", index_col="date", parse_dates=True)
    opts, ev = _read(data_dir, "options_iv.csv"), _read(data_dir, "earnings_events.csv")
    nxt, tok = _read(data_dir, "next_earnings.csv"), _read(data_dir, "token_re.csv")
    stats = compute_stats(prices, rates)
    ts = meta["retrieved_at"]

    path = os.path.join(data_dir, out_name if mode == "REAL" else out_name.replace(".xlsx", "_SYNTHETIC_test.xlsx"))
    with pd.ExcelWriter(path, engine="openpyxl", datetime_format="yyyy-mm-dd", date_format="yyyy-mm-dd") as xw:
        readme = pd.DataFrame({"item": [
            "Mode", "Retrieved (UTC)", "Purpose", "How to regenerate", "Sheets", "Read this first"],
            "detail": [
                mode + (" - SYNTHETIC TEST DATA, NOT REAL" if mode == "SYNTHETIC" else " market data"),
                ts, "Data pack for the AI investment analyst demo (hackathon). Educational, not financial advice.",
                "python fetch_data.py   (needs internet; add --synthetic for offline test data)",
                "Source_Register, Universe, Prices, Rates, Options_IV, Earnings_Events, Next_Earnings, "
                "Token_RE, Stats, Assumptions",
                "Source_Register lists where every dataset comes from, its limits, and its status. "
                "Assumptions are modelling choices, NOT data."]})
        _write(xw, readme, "README", "Data pack overview", mode)

        reg = pd.DataFrame(config.SOURCE_REGISTER)
        status = {"Daily prices (equities, ETFs, futures)": "prices",
                  "Treasury yield and T-bill rate": "rates", "Spot oil / gas (cross-check)": "rates",
                  "Option chains -> ATM IV, skew, term slope": "options_iv",
                  "Earnings dates, EPS estimate/actual, surprise": "earnings",
                  "Tokenized real estate token (yield, TVL, holders)": "token_re"}
        reg["status_this_run"] = [meta["datasets"].get(status.get(d), {}).get("status", "NOT WIRED")
                                  for d in reg["dataset"]]
        reg["retrieved_at_utc"] = ts
        _write(xw, reg, "Source_Register", "Where each dataset comes from, and its limits", mode)

        uni = pd.DataFrame([dict(asset_id=k, name=v["name"], yahoo_ticker=v["ticker"], asset_class=v["cls"],
                                 sector=v["sector"], sellable_within_2_days=v["liquid"],
                                 option_chain_pulled=v["options"],
                                 price_source=("Yahoo Finance via yfinance" if v["ticker"] else
                                               ("FRED DTB3 (T-bill rate)" if k == "CASH" else
                                                "No price history - see Token_RE and Assumptions")))
                            for k, v in config.UNIVERSE.items()])
        _write(xw, uni, "Universe", "Holdable assets and the source of each price series", mode)

        _write(xw, prices.reset_index(), "Prices", f"Daily adjusted close. Source: Yahoo Finance via yfinance "
               f"(see Universe for tickers). Retrieved {ts}. MKT = {config.BENCHMARK_TICKER}.", mode)
        _write(xw, rates.reset_index(), "Rates", f"Source: FRED fredgraph.csv (DGS10, DTB3, spot oil/gas) with "
               f"Yahoo fallback where noted in meta.json. Retrieved {ts}. Rates in percent.", mode)
        _write(xw, opts, "Options_IV", f"Snapshot of ATM implied vol, skew proxy, term slope. Source: Yahoo "
               f"Finance option chains via yfinance. Retrieved {ts}. No history.", mode)
        _write(xw, ev, "Earnings_Events", "Past earnings events with 2-day market-adjusted reaction. "
               "Source: Yahoo Finance via yfinance + prices above.", mode)
        _write(xw, nxt, "Next_Earnings", "Next scheduled earnings date per equity. Source: Yahoo Finance via yfinance.", mode)
        _write(xw, tok, "Token_RE", "Tokenized real estate token. Source: RWA.xyz dashboard, entered by hand "
               "(inputs/token_re.json). If is_placeholder is True these numbers are ASSUMPTIONS.", mode)
        _write(xw, stats, "Stats", "Computed from the Prices sheet (log returns, 252-day annualisation, "
               "beta vs MKT over last 252 days).", mode)
        ass = pd.DataFrame([dict(name=k, value=str(v["value"]), type="ASSUMPTION (not data)", rationale=v["why"])
                            for k, v in config.ASSUMPTIONS.items()])
        _write(xw, ass, "Assumptions", "Modelling assumptions used by optimizer.py - change in config.py", mode)
    return path


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else None))
