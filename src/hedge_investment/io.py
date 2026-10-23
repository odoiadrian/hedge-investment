"""JSON input support for portfolio comparison."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .portfolio import Holding, Portfolio, compare


def _required_text(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string.")
    return value


def _portfolio_from_dict(data: Any, index: int) -> Portfolio:
    context = f"portfolios[{index}]"
    if not isinstance(data, dict):
        raise ValueError(f"{context} must be an object.")

    name = _required_text(data, "name", context)
    risk_profile = _required_text(data, "risk_profile", context)
    horizon = _required_text(data, "horizon", context)
    raw_holdings = data.get("holdings")
    if not isinstance(raw_holdings, list):
        raise ValueError(f"{context}.holdings must be a list.")

    holdings: list[Holding] = []
    for holding_index, raw_holding in enumerate(raw_holdings):
        holding_context = f"{context}.holdings[{holding_index}]"
        if not isinstance(raw_holding, dict):
            raise ValueError(f"{holding_context} must be an object.")
        try:
            holding = Holding(
                ticker=_required_text(raw_holding, "ticker", holding_context),
                weight=raw_holding["weight"],
                expected_return=raw_holding["expected_return"],
                downside_return=raw_holding["downside_return"],
                rationale=_required_text(raw_holding, "rationale", holding_context),
                source=_required_text(raw_holding, "source", holding_context),
            )
        except KeyError as exc:
            raise ValueError(f"{holding_context}.{exc.args[0]} is required.") from exc
        holdings.append(holding)

    return Portfolio(name, risk_profile, horizon, tuple(holdings))


def load_analysis_input(path: str | Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Load comparison assumptions, client context, and optional SEC CIKs."""
    input_path = Path(path)
    try:
        with input_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {input_path}: {exc.msg} on line {exc.lineno}.") from exc

    if not isinstance(data, dict):
        raise ValueError("The input JSON root must be an object.")
    raw_portfolios = data.get("portfolios")
    if not isinstance(raw_portfolios, list) or len(raw_portfolios) != 2:
        raise ValueError("The input must contain exactly two portfolios.")

    capital_gbp = data.get("capital_gbp", 100_000)
    portfolios = [_portfolio_from_dict(item, index) for index, item in enumerate(raw_portfolios)]
    profile = data.get("client_profile", {})
    if not isinstance(profile, dict):
        raise ValueError("client_profile must be an object when provided.")
    cik_by_ticker: dict[str, str] = {}
    for portfolio in raw_portfolios:
        for holding in portfolio.get("holdings", []):
            if not isinstance(holding, dict) or "sec_cik" not in holding:
                continue
            ticker = _required_text(holding, "ticker", "holding")
            cik = str(holding["sec_cik"]).strip()
            if not cik.isdigit() or len(cik) > 10:
                raise ValueError(f"{ticker}.sec_cik must be a numeric SEC CIK of up to 10 digits.")
            cik_by_ticker[ticker.upper()] = cik.zfill(10)
    comparison = compare(portfolios[0], portfolios[1], capital_gbp)
    return comparison, profile, cik_by_ticker


def load_comparison(path: str | Path) -> dict[str, Any]:
    """Load two portfolio proposals from JSON and return their comparison."""
    comparison, _, _ = load_analysis_input(path)
    return comparison
