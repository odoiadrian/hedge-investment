"""Transparent risk-tier allocations for three user-supplied asset assumptions."""

from __future__ import annotations

from math import isfinite
from typing import Any


ASSET_CLASSES = ("bonds", "real_estate", "sp500")
STRATEGY_LABELS = {
    "risk_averse": "Risk-averse",
    "average": "Average",
    "risk_seeking": "Risk-seeking",
}


def _finite_number(value: Any, field: str, asset: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
    ):
        raise ValueError(f"{asset}.{field} must be a finite number.")
    return float(value)


def _normalise(scores: dict[str, float]) -> dict[str, float]:
    total = sum(scores.values())
    if total <= 0:
        return {asset: 1 / len(scores) for asset in scores}
    return {asset: score / total for asset, score in scores.items()}


def _number_summary(weighted_return: float, capital: float) -> dict[str, float]:
    return {
        "weighted_return_assumption": round(weighted_return, 6),
        "pnl_gbp": round(capital * weighted_return, 2),
        "ending_value_gbp": round(capital * (1 + weighted_return), 2),
    }


def build_investment_analysis(document: dict[str, Any]) -> dict[str, Any]:
    """Evaluate bonds, real estate, and S&P 500 using supplied assumptions.

    The allocation rules are simple, visible heuristics. They are not an
    optimizer and do not model covariance, fees, taxes, inflation, or FX.
    """
    capital = _finite_number(document.get("capital_gbp", 100_000), "capital_gbp", "input")
    if capital <= 0:
        raise ValueError("capital_gbp must be greater than zero.")
    horizon = document.get("horizon")
    if not isinstance(horizon, str) or not horizon.strip():
        raise ValueError("horizon must be a non-empty string.")
    profile = document.get("client_profile", {})
    if not isinstance(profile, dict):
        raise ValueError("client_profile must be an object when provided.")

    options = document.get("investment_options")
    if not isinstance(options, list) or len(options) != 3:
        raise ValueError("investment_options must contain exactly bonds, real_estate, and sp500.")

    by_class: dict[str, dict[str, Any]] = {}
    for option in options:
        if not isinstance(option, dict):
            raise ValueError("Each investment option must be an object.")
        asset = option.get("asset_class")
        if asset not in ASSET_CLASSES or asset in by_class:
            raise ValueError("Provide each asset_class exactly once: bonds, real_estate, sp500.")

        base_return = _finite_number(option.get("base_return_assumption"), "base_return_assumption", asset)
        downside_return = _finite_number(option.get("downside_return_assumption"), "downside_return_assumption", asset)
        if base_return < -1 or downside_return < -1 or downside_return > 0:
            raise ValueError(f"{asset} returns must be at least -100%, with downside at or below 0%.")

        name = option.get("name", asset.replace("_", " ").title())
        instrument = option.get("instrument", "")
        risks = option.get("risks")
        rewards = option.get("rewards")
        sources = option.get("sources")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{asset}.name must be a non-empty string.")
        if not isinstance(instrument, str):
            raise ValueError(f"{asset}.instrument must be a string.")
        for field, value in (("risks", risks), ("rewards", rewards), ("sources", sources)):
            if not isinstance(value, list) or not value:
                raise ValueError(f"{asset}.{field} must be a non-empty list.")
            if any(not isinstance(item, (str, dict)) for item in value):
                raise ValueError(f"{asset}.{field} entries must be strings or source objects.")
        if any(not isinstance(item, str) or not item.strip() for item in risks + rewards):
            raise ValueError(f"{asset}.risks and rewards must contain non-empty strings.")
        for source in sources:
            if isinstance(source, dict) and not all(
                isinstance(source.get(key), str) and source[key].strip()
                for key in ("label", "url")
            ):
                raise ValueError(f"{asset}.source objects need non-empty label and url fields.")
            if isinstance(source, str) and not source.strip():
                raise ValueError(f"{asset}.sources cannot contain empty strings.")

        loss = abs(downside_return)
        by_class[asset] = {
            "asset_class": asset,
            "name": name.strip(),
            "instrument": instrument.strip(),
            "base_return_assumption": base_return,
            "downside_return_assumption": downside_return,
            "base_case_pnl_gbp": round(capital * base_return, 2),
            "downside_case_pnl_gbp": round(capital * downside_return, 2),
            "assumption_reward_to_downside_ratio": (
                round(base_return / loss, 4) if loss else None
            ),
            "rewards": rewards,
            "risks": risks,
            "sources": sources,
        }

    downside_order = sorted(
        ASSET_CLASSES,
        key=lambda asset: abs(by_class[asset]["downside_return_assumption"]),
    )
    return_order = sorted(
        ASSET_CLASSES,
        key=lambda asset: by_class[asset]["base_return_assumption"],
        reverse=True,
    )
    for rank, asset in enumerate(downside_order, start=1):
        by_class[asset]["assumed_downside_rank"] = rank
    for rank, asset in enumerate(return_order, start=1):
        by_class[asset]["assumed_base_return_rank"] = rank

    # These rules use the client's entered scenario assumptions; they are
    # explainable sorting/weighting heuristics, not forecasts or optimization.
    risk_averse_weights = _normalise({
        asset: 1 / max(abs(row["downside_return_assumption"]), 0.01)
        for asset, row in by_class.items()
    })
    average_weights = _normalise({
        asset: max(row["base_return_assumption"], 0)
        / max(abs(row["downside_return_assumption"]), 0.01)
        for asset, row in by_class.items()
    })
    risk_seeking_weights = _normalise({
        asset: max(row["base_return_assumption"], 0)
        * max(abs(row["downside_return_assumption"]), 0.01)
        for asset, row in by_class.items()
    })

    rules = {
        "risk_averse": "Weights are proportional to the inverse of each asset's supplied downside magnitude.",
        "average": "Weights are proportional to each asset's supplied base return divided by its downside magnitude.",
        "risk_seeking": "Weights are proportional to each asset's supplied base return multiplied by its downside magnitude.",
    }
    profiles = {
        "risk_averse": risk_averse_weights,
        "average": average_weights,
        "risk_seeking": risk_seeking_weights,
    }
    strategies: list[dict[str, Any]] = []
    for key, weights in profiles.items():
        allocations = []
        base_return = 0.0
        downside_return = 0.0
        for asset in ASSET_CLASSES:
            row = by_class[asset]
            weight = weights[asset]
            base_return += weight * row["base_return_assumption"]
            downside_return += weight * row["downside_return_assumption"]
            allocations.append({
                "asset_class": asset,
                "name": row["name"],
                "weight": round(weight, 6),
                "amount_gbp": round(capital * weight, 2),
            })
        strategies.append({
            "risk_profile": key,
            "label": STRATEGY_LABELS[key],
            "allocation_method": rules[key],
            "allocations": allocations,
            "base_case": _number_summary(base_return, capital),
            "downside_case": _number_summary(downside_return, capital),
        })

    return {
        "mode": "asset_class_recommendations",
        "currency": "GBP",
        "capital_gbp": round(capital, 2),
        "horizon": horizon,
        "client_profile": profile,
        "input_assumptions_note": document.get("assumptions_note", ""),
        "asset_evaluations": [by_class[asset] for asset in ASSET_CLASSES],
        "strategy_options": strategies,
        "limitations": (
            "All return values are user-supplied illustrative assumptions, not forecasts. "
            "The three weights are transparent heuristics, not personalized investment advice "
            "or an optimized portfolio. The arithmetic omits fees, taxes, inflation, currency "
            "effects, liquidity constraints, leverage, and correlations between assets."
        ),
    }
