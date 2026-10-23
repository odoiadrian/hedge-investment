"""Client preferences -> validated constraints -> supplied optimiser -> explanations."""
import json
import math
import os
from pathlib import Path

from . import llm
from .config import ROOT
from .models import Allocation, BUDGET_CENTS, ClientProfile, PortfolioDashboard, PortfolioOption
from ..analyst import client_profile, config, data_loader, optimizer


class DataUnavailable(Exception):
    pass


def data_directory() -> Path:
    configured = os.getenv("ANALYST_DATA_DIR", "").strip()
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else ROOT / path
    return ROOT / "data" / "market"


def dataset_status():
    try:
        meta = json.loads((data_directory() / "meta.json").read_text())
        return {"mode": meta["mode"], "retrieved_at": meta.get("retrieved_at"), "datasets": meta.get("datasets", {})}
    except (OSError, ValueError, KeyError):
        return {"mode": "unavailable"}


def report_warnings(warnings):
    """Keep source diagnostics in meta.json; present their investment impact."""
    output = []
    for warning in warnings:
        if warning.startswith("FRED "):
            series = warning.split()[1]
            if series in ("DGS10", "DTB3"):
                warning = f"FRED {series} was unavailable; the rate uses the alternative provider listed under Data sources."
            else:
                warning = "The optional FRED oil/gas spot-price cross-check was unavailable. Portfolio calculations use Yahoo futures prices."
        elif "TOKEN_RE" in warning and "PLACEHOLDER" in warning:
            continue  # One explicit exclusion message is added below.
        output.append(warning)
    return list(dict.fromkeys(output))


def cents_for_holdings(holdings):
    """Largest-remainder rounding, retaining tiny positions until cent rounding."""
    weights = [h["weight"] for h in holdings]
    if not weights or any(not math.isfinite(w) or w < 0 for w in weights) or abs(sum(weights) - 1) > 1e-8:
        raise DataUnavailable("The optimiser returned invalid portfolio weights.")
    amounts = [w / sum(weights) * BUDGET_CENTS for w in weights]
    cents = [math.floor(a) for a in amounts]
    remaining = BUDGET_CENTS - sum(cents)
    for i in sorted(range(len(cents)), key=lambda i: amounts[i] - cents[i], reverse=True)[:remaining]:
        cents[i] += 1
    return cents


def build_rules(profile, preferences):
    problems = list(preferences.unresolved)
    allowed = set(config.UNIVERSE)
    excluded = set(preferences.excluded_assets)
    if excluded - allowed or "CASH" in excluded:
        problems.append("Please specify exclusions using the supported assets or sectors.")
    raw = {
        "capital": BUDGET_CENTS / 100, "currency": "USD", "horizon_weeks": profile.horizon_weeks,
        "risk_appetite": profile.risk_appetite, "max_loss_pct": profile.max_loss_pct,
        "max_single_holding_pct": profile.max_single_holding_pct, "objective": profile.objective,
        "min_cash_pct": profile.min_cash_pct, "min_sellable_2day_pct": profile.min_sellable_2day_pct,
        "target_return_pct": profile.target_return_pct, "benchmark": "us_equities",
        "max_illiquid_pct": 0, "allow_leverage_or_shorting": False,
        "exclusions": sorted(excluded | {"TOKEN_RE"}), "class_limits": {}, "asset_limits": {},
    }
    for limit in preferences.limits:
        valid = allowed if limit.kind == "asset" else set(client_profile.CLASSES)
        lo = 0 if limit.minimum_pct is None else limit.minimum_pct
        hi = 100 if limit.maximum_pct is None else limit.maximum_pct
        if limit.key not in valid or not 0 <= lo <= hi <= 100:
            problems.append("An investment limit could not be interpreted. Use a supported asset/class and percentages between zero and one hundred.")
            continue
        if limit.key in ("TOKEN_RE", "tokenized_real_estate") and lo > 0:
            problems.append("Tokenized real estate is unavailable until its placeholder data is replaced.")
        limits = raw["asset_limits" if limit.kind == "asset" else "class_limits"]
        existing = limits.get(limit.key, {"min_pct": 0, "max_pct": 100})
        limits[limit.key] = {"min_pct": max(lo, existing["min_pct"]), "max_pct": min(hi, existing["max_pct"])}
    return raw, problems


def verify_rounded_constraints(holdings, cents, rules):
    """Check displayed monetary allocations as well as the solver's real weights."""
    weights = {h["asset"]: c / BUDGET_CENTS for h, c in zip(holdings, cents)}
    tolerance = 1 / BUDGET_CENTS + 1e-12  # At most one cent of rounding at a bound.
    P, _ = client_profile.normalise(rules)
    if P is None:
        raise DataUnavailable("The resulting client rules could not be validated.")
    violations = []
    for asset, w in weights.items():
        if asset in P["excluded"] and w > 0:
            violations.append(asset)
        if asset != "CASH" and w > P["max_single"] + tolerance:
            violations.append(asset)
    for asset, (lo, hi) in P["asset_bounds"].items():
        if not lo - tolerance <= weights.get(asset, 0) <= hi + tolerance:
            violations.append(asset)
    for cls, (lo, hi) in P["class_bounds"].items():
        value = sum(w for a, w in weights.items() if config.UNIVERSE[a]["cls"] == cls)
        if not lo - tolerance <= value <= hi + tolerance:
            violations.append(cls)
    if weights.get("CASH", 0) < P["cash_min"] - tolerance:
        violations.append("cash minimum")
    if sum(w for a, w in weights.items() if not config.UNIVERSE[a]["liquid"]) > P["illiquid_cap"] + tolerance:
        violations.append("illiquid limit")
    if violations:
        raise DataUnavailable("Numerical rounding could not preserve all client limits. Please adjust the constraints slightly.")


def generate_dashboard(profile: ClientProfile) -> PortfolioDashboard:
    try:
        bundle = data_loader.load(str(data_directory()))
        if bundle.meta.get("mode") not in ("REAL", "SYNTHETIC"):
            raise ValueError("Unknown data provenance")
    except (OSError, ValueError, KeyError) as exc:
        raise DataUnavailable("The market dataset is unavailable. Run the documented data refresh command.") from exc

    preferences, tokens = llm.interpret_preferences(profile)
    rules, questions = build_rules(profile, preferences)
    common = dict(client_reference=profile.reference, data_mode=bundle.meta["mode"],
                  data_as_of=str(bundle.asof.date()), tokens_used=tokens,
                  data_sources=bundle.meta.get("datasets", {}),
                  applied_profile=rules, model_name=os.getenv("AZURE_OPENAI_DEPLOYMENT", ""))
    if questions:
        return PortfolioDashboard(status="needs_clarification", message="A few client preferences need clarification.",
                                  questions=questions, **common)
    try:
        result = optimizer.recommend(rules, bundle=bundle)
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        raise DataUnavailable("The financial model could not process this dataset/profile. Check the local dataset and constraints.") from exc
    if result["status"] == "INFEASIBLE":
        suggestions = ["Review " + " and ".join(group) + "." for group in result.get("relaxing_any_one_of_these_would_make_it_feasible", [])]
        return PortfolioDashboard(status="infeasible", message="No portfolio satisfies all of these constraints together.",
                                  questions=suggestions or ["Review the holding, loss and asset-class limits."], **common)
    if result["status"] != "OK":
        raise DataUnavailable("The financial model could not produce a portfolio for these inputs.")

    warnings = report_warnings(result["warnings"]) + preferences.notes + result["profile_notes"]
    warnings += ["TOKEN_RE is excluded: its source inputs are placeholders.",
                 "Model estimates are not forecasts or guaranteed profits. No walk-forward backtest is included.",
                 "Risk appetite maps to an assumed volatility limit; age does not automatically change that limit."]
    explanation = None
    try:
        explanation, used = llm.explain(result, preferences.summary)
        common["tokens_used"] += used
    except llm.AnalystUnavailable:
        warnings.append("AI explanation unavailable. The displayed reasoning uses the computed model inputs directly.")
    reasons = {h.asset_id: h for h in explanation.holdings} if explanation else {}
    options = []
    for option_id, option in result["options"].items():
        cents = cents_for_holdings(option["holdings"])
        verify_rounded_constraints(option["holdings"], cents, rules)
        metrics = option["metrics"]
        if metrics["vol_annualised_pct"] > result["client"]["vol_cap_annual_pct"] + .02 or metrics["loss_1_in_20_pct"] < -profile.max_loss_pct - .02:
            raise DataUnavailable("The optimiser returned a portfolio outside the risk limits.")
        allocations = []
        for holding, amount in zip(option["holdings"], cents):
            if not amount:
                continue
            asset = holding["asset"]
            inputs = result["asset_inputs"][asset]
            reason = reasons.get(asset)
            sources = [f"{result['data_mode']} dataset; prices as of {result['data_as_of']}",
                       inputs["return_basis"], inputs.get("vol_basis", "Cash rate from Treasury bill series")]
            allocations.append(Allocation(
                asset_id=asset, instrument=holding["name"], asset_class=inputs["cls"], amount_cents=amount,
                financial_reason=reason.financial_reason if reason else f"{inputs['return_basis']}. Model horizon return: {inputs['mu_horizon_pct']}%.",
                client_reason=reason.client_reason if reason else "Included within the client's risk, concentration and explicit exclusion constraints. " + preferences.summary,
                evidence=sources,
            ))
        options.append(PortfolioOption(id=option_id, label=option["label"], allocations=allocations,
                                       metrics=metrics, tightest_rules=option["tightest_rules"],
                                       note=option["note"], resampled=option["resampled_average"]))
    return PortfolioDashboard(
        status="ready", recommended_option=result["recommended_option"], options=options,
        client_assessment=f"Risk appetite {profile.risk_appetite}/5 maps to a {result['client']['vol_cap_annual_pct']}% annual volatility cap (model assumption). " + preferences.summary,
        financial_assessment=result["method"], ai_status="generated" if explanation else "unavailable",
        ai_summary=explanation.summary if explanation else "", warnings=list(dict.fromkeys(warnings)),
        assumptions=result["assumptions"], target_return=result["target_return"],
        horizon_trading_days=result["client"]["horizon_trading_days"], **common,
    )
