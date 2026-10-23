"""Scenario arithmetic for two human-researched portfolio proposals.

Returns are input assumptions over the portfolio's stated horizon. This module
does not estimate their likelihood or recommend securities.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class Holding:
    ticker: str
    weight: float
    expected_return: float
    downside_return: float
    rationale: str
    source: str


@dataclass(frozen=True)
class Portfolio:
    name: str
    risk_profile: str
    horizon: str
    holdings: tuple[Holding, ...]


def _validate(portfolio: Portfolio) -> None:
    if not isinstance(portfolio.name, str) or not portfolio.name.strip():
        raise ValueError("Portfolio name is required.")
    if not isinstance(portfolio.horizon, str) or not portfolio.horizon.strip():
        raise ValueError("Portfolio name and horizon are required.")
    if not isinstance(portfolio.risk_profile, str) or portfolio.risk_profile not in {
        "defensive",
        "aggressive",
    }:
        raise ValueError("risk_profile must be 'defensive' or 'aggressive'.")
    if not isinstance(portfolio.holdings, (list, tuple)) or not portfolio.holdings:
        raise ValueError("A portfolio must contain at least one holding.")

    seen: set[str] = set()
    total_weight = 0.0
    for holding in portfolio.holdings:
        if not isinstance(holding.ticker, str) or not holding.ticker.strip() or holding.ticker in seen:
            raise ValueError("Holding tickers must be non-empty and unique per portfolio.")
        seen.add(holding.ticker)
        if (
            not isinstance(holding.rationale, str)
            or not holding.rationale.strip()
            or not isinstance(holding.source, str)
            or not holding.source.strip()
        ):
            raise ValueError(f"{holding.ticker} needs a rationale and source reference.")
        values = (holding.weight, holding.expected_return, holding.downside_return)
        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isfinite(value)
            for value in values
        ):
            raise ValueError(f"{holding.ticker} contains a non-finite numeric input.")
        if not 0 <= holding.weight <= 1:
            raise ValueError(f"{holding.ticker} weight must be between 0 and 1.")
        if holding.expected_return < -1 or holding.downside_return < -1:
            raise ValueError(f"{holding.ticker} scenario return cannot be below -100%.")
        total_weight += holding.weight

    if total_weight > 1 + 1e-9:
        raise ValueError("Portfolio weights cannot exceed 100% of capital.")


def _summarise(portfolio: Portfolio, capital_gbp: float) -> dict[str, Any]:
    _validate(portfolio)
    invested_weight = sum(holding.weight for holding in portfolio.holdings)
    base_return = sum(
        holding.weight * holding.expected_return for holding in portfolio.holdings
    )
    downside_return = sum(
        holding.weight * holding.downside_return for holding in portfolio.holdings
    )
    invested_gbp = capital_gbp * invested_weight
    largest = max(portfolio.holdings, key=lambda item: item.weight)

    return {
        "name": portfolio.name,
        "risk_profile": portfolio.risk_profile,
        "horizon": portfolio.horizon,
        "capital_gbp": round(capital_gbp, 2),
        "invested_gbp": round(invested_gbp, 2),
        "cash_gbp": round(capital_gbp - invested_gbp, 2),
        "base_case": {
            "weighted_return": round(base_return, 6),
            "ending_value_gbp": round(capital_gbp * (1 + base_return), 2),
            "pnl_gbp": round(capital_gbp * base_return, 2),
        },
        "downside_case": {
            "weighted_return": round(downside_return, 6),
            "ending_value_gbp": round(capital_gbp * (1 + downside_return), 2),
            "pnl_gbp": round(capital_gbp * downside_return, 2),
        },
        "largest_position": {
            "ticker": largest.ticker,
            "weight": round(largest.weight, 6),
            "amount_gbp": round(capital_gbp * largest.weight, 2),
        },
        "holdings": [asdict(holding) for holding in portfolio.holdings],
    }


def compare(
    portfolio_a: Portfolio,
    portfolio_b: Portfolio,
    capital_gbp: float = 100_000,
) -> dict[str, Any]:
    """Compare two proposals using transparent weighted scenario arithmetic.

    Uninvested capital is treated as cash earning zero. The output is an
    illustration based only on supplied assumptions; it is not a forecast.
    """
    if (
        not isinstance(capital_gbp, (int, float))
        or isinstance(capital_gbp, bool)
        or not isfinite(capital_gbp)
        or capital_gbp <= 0
    ):
        raise ValueError("capital_gbp must be a positive finite amount.")
    _validate(portfolio_a)
    _validate(portfolio_b)
    if portfolio_a.horizon.strip() != portfolio_b.horizon.strip():
        raise ValueError("Both portfolios must use the same stated horizon.")
    if portfolio_a.risk_profile == portfolio_b.risk_profile:
        raise ValueError("The comparison needs one defensive and one aggressive portfolio.")

    portfolios = sorted(
        (portfolio_a, portfolio_b),
        key=lambda item: 0 if item.risk_profile == "defensive" else 1,
    )
    return {
        "currency": "GBP",
        "horizon": portfolio_a.horizon,
        "capital_gbp": round(capital_gbp, 2),
        "portfolios": [_summarise(item, capital_gbp) for item in portfolios],
        "calculation_note": (
            "Scenario values are weighted arithmetic from supplied return assumptions. "
            "They do not include fees, taxes, slippage, correlation effects, or a probability "
            "of either scenario occurring. They are not predictions or guarantees."
        ),
    }
