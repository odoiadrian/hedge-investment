"""
profile.py - the client profile: schema the LLM fills in, validation, and normalisation.

The LLM never sets weights or probabilities. It only turns the client's chat messages into this
structured profile; this module validates it and converts it into the numbers the optimiser uses.
All percentages in the schema are PERCENT NUMBERS (20 means 20%), because that is how people speak.
"""
from . import config

CLASSES = ["equities", "commodities", "bonds", "real_estate", "tokenized_real_estate", "cash"]
CLASS_ALIASES = {"stocks": "equities", "stock": "equities", "equity": "equities", "shares": "equities",
                 "commodity": "commodities", "oil": "commodities", "oil_and_gas": "commodities",
                 "bond": "bonds", "fixed_income": "bonds", "treasuries": "bonds",
                 "reit": "real_estate", "reits": "real_estate", "property": "real_estate",
                 "tokenized": "tokenized_real_estate", "token": "tokenized_real_estate",
                 "tokenised_real_estate": "tokenized_real_estate"}
OBJECTIVES = ["preserve_capital", "income", "balanced_growth", "max_growth"]
OBJECTIVE_TO_OPTION = {"preserve_capital": "A", "income": "A", "balanced_growth": "B", "max_growth": "C"}
BENCHMARKS = ["us_equities", "cash", "none"]

REQUIRED = ["capital", "horizon_weeks", "max_loss_pct", "risk_appetite", "max_single_holding_pct"]
DEFAULTS = {"currency": "USD", "objective": "balanced_growth", "benchmark": "none",
            "max_illiquid_pct": 5.0, "min_sellable_2day_pct": 90.0, "min_cash_pct": 0.0,
            "allow_leverage_or_shorting": False, "exclusions": [], "class_limits": {}, "asset_limits": {}}

# JSON schema handed to the LLM as the input of the build_portfolio tool
PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "capital": {"type": "number", "description": "Amount to invest, e.g. 100000."},
        "currency": {"type": "string", "description": "Currency code. Only USD is modelled; default USD."},
        "horizon_weeks": {"type": "number", "description": "Investment horizon in weeks (1 month = 4)."},
        "benchmark": {"type": "string", "enum": BENCHMARKS,
                      "description": "What to compare against. us_equities uses SPY as the proxy."},
        "objective": {"type": "string", "enum": OBJECTIVES},
        "target_return_pct": {"type": "number", "description": "Optional target return over the horizon, in percent."},
        "max_loss_pct": {"type": "number", "description": "Worst loss the client accepts over the horizon in a "
                         "bad (1-in-20) case, as a positive percent, e.g. 8."},
        "risk_appetite": {"type": "integer", "minimum": 1, "maximum": 5,
                          "description": "1 = very cautious ... 5 = very aggressive."},
        "max_single_holding_pct": {"type": "number", "description": "Maximum percent of capital in any one holding."},
        "max_illiquid_pct": {"type": "number", "description": "Maximum percent in illiquid assets (tokenized real estate)."},
        "min_sellable_2day_pct": {"type": "number", "description": "Minimum percent that must be sellable within 2 trading days."},
        "class_limits": {"type": "object",
                         "description": "Per asset class bounds in percent. Keys: " + ", ".join(CLASSES) +
                                        ". Values: {\"min_pct\": x, \"max_pct\": y} (either optional).",
                         "additionalProperties": {"type": "object", "properties": {
                             "min_pct": {"type": "number"}, "max_pct": {"type": "number"}}}},
        "asset_limits": {"type": "object",
                         "description": "Per asset bounds in percent. Keys are asset ids: " +
                                        ", ".join(config.UNIVERSE) + ".",
                         "additionalProperties": {"type": "object", "properties": {
                             "min_pct": {"type": "number"}, "max_pct": {"type": "number"}}}},
        "exclusions": {"type": "array", "items": {"type": "string"},
                       "description": "Asset ids, asset classes, or sectors to exclude, e.g. [\"Energy\", \"PG\"]."},
        "allow_leverage_or_shorting": {"type": "boolean", "description": "Not supported (long-only). Must be false."},
        "min_cash_pct": {"type": "number", "description": "Minimum percent held in cash."},
    },
    "required": REQUIRED,
}


def _pct(v, name, errors, lo=0.0, hi=100.0):
    try:
        x = float(v)
    except (TypeError, ValueError):
        errors.append(f"{name} must be a number (percent)")
        return None
    if not (lo <= x <= hi):
        errors.append(f"{name}={x} is outside {lo}-{hi}")
        return None
    return x / 100.0


def _bounds(d, kind, valid_keys, aliases, errors):
    out = {}
    for key, b in (d or {}).items():
        k = aliases.get(str(key).lower().replace(" ", "_"), str(key))
        if k not in valid_keys:
            errors.append(f"{kind} limit key '{key}' is not one of {sorted(valid_keys)}")
            continue
        lo = _pct(b.get("min_pct", 0), f"{kind}[{key}].min_pct", errors) if isinstance(b, dict) else None
        hi = _pct(b.get("max_pct", 100), f"{kind}[{key}].max_pct", errors) if isinstance(b, dict) else None
        if lo is None or hi is None:
            continue
        if lo > hi:
            errors.append(f"{kind}[{key}]: min {lo*100:g}% is above max {hi*100:g}%")
            continue
        out[k] = (lo, hi)
    return out


def resolve_exclusions(exclusions):
    """Match exclusion strings against asset id, class, sector or name. Returns (asset ids, unmatched)."""
    removed, unmatched = set(), []
    for raw in exclusions or []:
        s = str(raw).strip().lower().replace(" ", "_")
        s_alias = CLASS_ALIASES.get(s, s)
        hit = set()
        for aid, u in config.UNIVERSE.items():
            keys = {aid.lower(), u["cls"].lower(), u["sector"].lower().replace(" ", "_"),
                    u["name"].lower().replace(" ", "_")}
            if s in keys or s_alias in keys or s in u["name"].lower().replace(" ", "_"):
                hit.add(aid)
        hit.discard("CASH")
        if hit:
            removed |= hit
        else:
            unmatched.append(raw)
    return removed, unmatched


def normalise(raw):
    """Validate + convert the raw profile (as the LLM supplies it).

    Returns (P, report). P is None if the profile is unusable; report always has
    errors / missing / assumed_defaults / notes so the LLM can ask the client the right follow-up.
    """
    errors, notes, assumed = [], [], []
    raw = dict(raw or {})
    missing = [k for k in REQUIRED if raw.get(k) in (None, "")]
    if missing:
        return None, dict(ok=False, missing=missing, errors=[], assumed_defaults=[], notes=[])

    for k, v in DEFAULTS.items():
        if raw.get(k) in (None, ""):
            raw[k] = v
            if k in ("max_illiquid_pct", "min_sellable_2day_pct", "min_cash_pct", "objective", "benchmark"):
                assumed.append(f"{k} not given -> assumed {v}")

    P = {}
    try:
        P["capital"] = float(raw["capital"])
        if P["capital"] <= 0:
            errors.append("capital must be positive")
    except (TypeError, ValueError):
        errors.append("capital must be a number")
    P["currency"] = str(raw["currency"]).upper()
    if P["currency"] != "USD":
        notes.append("Only USD is modelled; amounts are treated as USD.")

    try:
        weeks = float(raw["horizon_weeks"])
        P["horizon_days"] = int(round(weeks * 5))
        if not (5 <= P["horizon_days"] <= 130):
            errors.append("horizon_weeks must be between 1 and 26")
    except (TypeError, ValueError):
        errors.append("horizon_weeks must be a number")

    try:
        P["risk_appetite"] = int(raw["risk_appetite"])
        if P["risk_appetite"] not in (1, 2, 3, 4, 5):
            errors.append("risk_appetite must be 1-5")
    except (TypeError, ValueError):
        errors.append("risk_appetite must be an integer 1-5")

    P["max_loss"] = _pct(raw["max_loss_pct"], "max_loss_pct", errors, 0.5, 60)
    P["max_single"] = _pct(raw["max_single_holding_pct"], "max_single_holding_pct", errors, 1, 100)
    P["illiquid_cap"] = _pct(raw["max_illiquid_pct"], "max_illiquid_pct", errors)
    sellable = _pct(raw["min_sellable_2day_pct"], "min_sellable_2day_pct", errors)
    P["cash_min"] = _pct(raw["min_cash_pct"], "min_cash_pct", errors)
    if P["illiquid_cap"] is not None and sellable is not None:
        P["illiquid_cap"] = min(P["illiquid_cap"], 1.0 - sellable)
    P["target_return"] = (_pct(raw["target_return_pct"], "target_return_pct", errors, -50, 100)
                          if raw.get("target_return_pct") not in (None, "") else None)

    if raw.get("objective") not in OBJECTIVES:
        errors.append(f"objective must be one of {OBJECTIVES}")
    P["objective"] = raw.get("objective")
    P["benchmark"] = raw.get("benchmark") if raw.get("benchmark") in BENCHMARKS else "none"
    if raw.get("benchmark") not in BENCHMARKS:
        notes.append(f"benchmark '{raw.get('benchmark')}' not supported; using none. "
                     f"Supported: {BENCHMARKS} (us_equities = SPY proxy).")
    if P["objective"] == "income":
        notes.append("Income objective is approximated by the lowest-risk option; no income model in this version.")

    if raw.get("allow_leverage_or_shorting"):
        errors.append("Leverage and shorting are not supported in this version (long-only, fully invested).")

    P["class_bounds"] = _bounds(raw["class_limits"], "class", set(CLASSES), CLASS_ALIASES, errors)
    P["asset_bounds"] = _bounds(raw["asset_limits"], "asset", set(config.UNIVERSE), {}, errors)

    removed, unmatched = resolve_exclusions(raw["exclusions"])
    P["excluded"] = removed
    if unmatched:
        notes.append(f"Exclusions that matched nothing: {unmatched}")
    if removed:
        notes.append(f"Excluded from the universe: {sorted(removed)}")

    appetite = P.get("risk_appetite")
    if appetite in config.A("risk_appetite_to_vol"):
        P["vol_cap_annual"] = config.A("risk_appetite_to_vol")[appetite]
    P["raw"] = raw

    report = dict(ok=not errors, missing=[], errors=errors, assumed_defaults=assumed, notes=notes)
    return (P if not errors else None), report
