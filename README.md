# Hedge Investment Research Prototype

Prototype for a decision-support product for emerging hedge funds allocating up to £100,000. It compares two researched portfolios: a higher-risk strategy and a more defensive strategy. The current implementation is a transparent scenario calculator; it does not yet use an AI model or live market data.

## What this prototype does

The command-line tool reads portfolio assumptions from JSON and converts them into comparable GBP scenarios. For each portfolio it reports the invested amount, cash reserve, weighted base and downside return assumptions, illustrative ending values, and largest position. Every holding carries a rationale and a source reference so a reviewer can trace the case.

The calculations are scenario arithmetic, not forecasts. The prototype does not select securities, fetch market data, estimate probabilities, or execute trades. It must not fill missing evidence with generated claims. An AI research layer can later summarise supplied evidence, but quantitative inputs and citations should remain explicit and reviewable.

## Inputs

The input JSON contains `capital_gbp` and exactly two portfolios. Each portfolio has a name, a risk profile (`defensive` or `aggressive`), a shared time horizon, and holdings. A holding contains:

- `ticker`: security identifier
- `weight`: fraction of the fund's capital, from 0 to 1
- `expected_return`: research team's base-case return over the stated horizon, as a decimal
- `downside_return`: research team's adverse scenario return over that same horizon, as a decimal
- `rationale`: concise investment thesis
- `source`: URL or internal research reference supporting the thesis and assumptions

Weights may sum to less than 1; the remainder is treated as uninvested cash with a zero return. They may not exceed 1. Returns are not annualised by the calculator; both scenarios must refer to the portfolio's stated horizon.

## Run

Requires Python 3.10 or later. From the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m hedge_investment examples/portfolio_comparison.json
```

If no file is passed, the command reads the same fictional example. The sample uses fictitious identifiers and made-up assumptions only to demonstrate the interface. Replace them with reviewed, dated research before using the output. Do not run `src/hedge_investment/__init__.py` directly; Python must import the package for its relative imports to work.

The JSON return assumptions are decimals over the stated horizon: `0.04` means 4%, while `-0.12` means -12%. Weights are fractions of fund capital, so `0.5` means 50%. Weights may total less than 1; the remainder is treated as cash with a zero return. They may not exceed 1.

## Development principles

1. Keep user objectives, constraints, horizon, currency, and liquidity needs explicit.
2. Separate source facts, analyst assumptions, model outputs, and AI-written explanation.
3. Show base and adverse scenarios for both strategies on the same capital and horizon.
4. Preserve citations and timestamps for every material claim; surface missing or stale data.
5. Add market data and forecasting only after licensing, point-in-time quality, and out-of-sample validation are established.
6. Present results for human review; do not describe scenario outputs as guaranteed or personalised investment advice.

## Challenge brief and scope

The supplied Bloomberg challenge brief describes a separate, short-horizon competition strategy and marks its model results and some 2026 rule details as unverified. This product targets fund-level portfolio decision support instead. Treat the brief's data-quality, point-in-time, evidence, validation, and human-review practices as useful design constraints; verify competition-specific rules only if a competition mode is later added.

## Next steps

- Add a versioned input/output schema and a simple web interface.
- Add evidence ingestion with source links, dates, and extracted claim review.
- Add portfolio-level risk calculations only when a documented covariance or risk methodology is supplied.
- Add historical backtesting with point-in-time data and realistic transaction costs before presenting model performance claims.
- Keep a human approval step before any recommendation is used to trade.
