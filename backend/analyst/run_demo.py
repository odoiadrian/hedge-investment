#!/usr/bin/env python3
"""
run_demo.py - run the optimiser on the hypothetical seed-fund client WITHOUT the LLM.

    python run_demo.py            # print the three portfolios
    python run_demo.py --check    # also verify every client rule against the output (independent of the solver)
    python run_demo.py --json     # dump the full result JSON (this is what the LLM receives)
"""
import argparse
import json
import sys

from . import config
from . import optimizer

HYPOTHETICAL_CLIENT = {
    "capital": 100000, "currency": "USD", "horizon_weeks": 4, "benchmark": "us_equities",
    "objective": "balanced_growth", "target_return_pct": 2, "max_loss_pct": 8, "risk_appetite": 3,
    "max_single_holding_pct": 20, "max_illiquid_pct": 5, "min_sellable_2day_pct": 90,
    "class_limits": {"bonds": {"min_pct": 10}, "commodities": {"max_pct": 20}},
    "asset_limits": {"WTI": {"max_pct": 10}, "NATGAS": {"max_pct": 10}},
    "exclusions": [], "allow_leverage_or_shorting": False, "min_cash_pct": 5,
}


def verify(res, profile, tol=0.15):
    """Re-check the client's rules from the printed holdings only (percent, tolerance for rounding)."""
    problems = []
    for k, opt in res["options"].items():
        h = {x["asset"]: x["weight_pct"] for x in opt["holdings"]}
        tot = sum(h.values())
        if abs(tot - 100) > tol:
            problems.append(f"{k}: weights sum to {tot}")
        for a, w in h.items():
            if a != "CASH" and w > profile["max_single_holding_pct"] + tol:
                problems.append(f"{k}: {a} {w}% above single cap")
            lim = profile["asset_limits"].get(a, {}).get("max_pct")
            if lim is not None and w > lim + tol:
                problems.append(f"{k}: {a} {w}% above asset limit {lim}%")
        cls = {}
        for a, w in h.items():
            cls[config.UNIVERSE[a]["cls"]] = cls.get(config.UNIVERSE[a]["cls"], 0) + w
        for c, b in profile["class_limits"].items():
            if cls.get(c, 0) < b.get("min_pct", 0) - tol or cls.get(c, 0) > b.get("max_pct", 100) + tol:
                problems.append(f"{k}: class {c} at {cls.get(c, 0):.1f}% outside {b}")
        illiq = sum(w for a, w in h.items() if not config.UNIVERSE[a]["liquid"])
        if illiq > profile["max_illiquid_pct"] + tol:
            problems.append(f"{k}: illiquid {illiq}% above cap")
        if h.get("CASH", 0) < profile["min_cash_pct"] - tol:
            problems.append(f"{k}: cash {h.get('CASH', 0)}% below minimum")
        cap = res["client"]["vol_cap_annual_pct"]
        if opt["metrics"]["vol_annualised_pct"] > cap + 0.1:
            problems.append(f"{k}: vol {opt['metrics']['vol_annualised_pct']}% above cap {cap}%")
        if opt["metrics"]["loss_1_in_20_pct"] < -profile["max_loss_pct"] - 0.05:
            problems.append(f"{k}: 1-in-20 loss {opt['metrics']['loss_1_in_20_pct']}% beyond limit")
    return problems


def show(res):
    if res["status"] != "OK":
        print(json.dumps(res, indent=2, default=str))
        return
    print(f"DATA: {res['data_mode']}  as of {res['data_as_of']}   risk-free over horizon {res['risk_free_horizon_pct']}%")
    for w in res["warnings"]:
        print("  !", w)
    for k, o in res["options"].items():
        star = "  <-- recommended for the stated objective" if k == res["recommended_option"] else ""
        m = o["metrics"]
        print(f"\nOPTION {k}: {o['label']}{star}")
        for h in o["holdings"]:
            print(f"   {h['asset']:9s} {h['weight_pct']:5.1f}%  ${h['amount']:>9,.0f}   {h['name']}")
        print(f"   exp. return {m['expected_return_pct']}%  vol(ann) {m['vol_annualised_pct']}%  Sharpe {m['sharpe_annualised']}  "
              f"1-in-20 {m['loss_1_in_20_pct']}%  worst hist. {m['worst_historical_horizon_return_pct']}%")
        if m["stress_breaches_loss_limit"]:
            print("   ! worst historical period was WORSE than the client's loss limit")
        print(f"   binding rules: {o['binding_rules'] or 'none'}   |   tightest: {o['tightest_rules']}")
        if o.get("note"):
            print("   note:", o["note"])
    if res["cost_of_tight_rules_in_recommended_option"]:
        print("\nCost of the tightest rules (recommended option):")
        for c in res["cost_of_tight_rules_in_recommended_option"]:
            print("   ", c)
    if res["target_return"]:
        print("\nTarget:", res["target_return"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--data", default=None)
    a = ap.parse_args()
    res = optimizer.recommend(HYPOTHETICAL_CLIENT, data_dir=a.data)
    if a.json:
        print(json.dumps(res, indent=2, default=str))
    else:
        show(res)
    if a.check and res["status"] == "OK":
        probs = verify(res, HYPOTHETICAL_CLIENT)
        print("\nCHECK:", "all client rules satisfied in every option" if not probs else probs)
        sys.exit(1 if probs else 0)
