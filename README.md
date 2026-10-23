# Hedge Investment Research Prototype

Prototype for a decision-support product for seed-stage hedge funds allocating up to £100,000. It evaluates bonds, real-estate exposure, and the S&P 500, builds risk-averse, average, and risk-seeking allocations, and can explain the result with the hackathon Azure OpenAI endpoint.

## What this prototype does

The default command reads client context, source links, risk/reward factors, and return assumptions for three asset classes from JSON. It computes a potential base case and downside case for each asset, then creates three allocations and calculates their GBP outcomes. With `--explain`, GPT-6 Astra describes the tradeoffs using only the supplied inputs. A legacy two-portfolio mode remains available; that mode can also retrieve public SEC company facts with `--sec-data`.

All return assumptions are entered by the user; they are not forecasts. The allocation rules are visible heuristics, not an optimizer or personalized investment advice. They do not estimate probabilities, account for correlations, or execute trades. The AI explains the supplied case and must surface missing details such as bond mix, property vehicle, and currency hedging. SEC facts in legacy mode are current public filing data, not a point-in-time backtest dataset.

## Inputs

The default `examples/investment_options.json` schema contains `capital_gbp`, a common `horizon`, optional `client_profile`, and exactly one option per `asset_class`: `bonds`, `real_estate`, and `sp500`. Each option includes:

- `instrument`: the intended investment vehicle and any unresolved details
- `base_return_assumption`: human-entered base scenario over the stated horizon, as a decimal
- `downside_return_assumption`: human-entered adverse scenario over that horizon, as a decimal
- `rewards` and `risks`: evidence-linked factors considered by the AI analyst
- `sources`: labels and URLs supporting the factors

Optional `client_profile` fields include `fund_stage`, `objective`, `risk_tolerance`, `liquidity_needs`, and `constraints`. They provide context to the AI but do not alter the arithmetic.

All return assumptions must cover the same horizon. The outputs label the base and downside calculations as assumptions and show both sterling P&L and ending values.

## Allocation rules

The project uses three readable heuristics based on the input scenarios:

- Risk-averse: weights are proportional to the inverse of each option's downside magnitude.
- Average: weights are proportional to its base return divided by its downside magnitude.
- Risk-seeking: weights are proportional to its base return multiplied by its downside magnitude.

The resulting weights are normalized to 100%. These simple rules help illustrate a risk spectrum; they do not account for correlations, fees, taxes, leverage, liquidity, currency effects, or suitability. Change the assumptions and review the outputs before presenting them to a client.

## Run

Requires Python 3.10 or later. From the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m hedge_investment examples/investment_options.json
```

Install the Azure OpenAI client dependency before using the AI option:

```powershell
python -m pip install -r requirements.txt
```

Set `AZURE_OPENAI_API_KEY` as a Codespaces secret (recommended) or local environment variable. `.env.example` lists the available settings; copying it to `.env` does not load it automatically. In a GitHub Codespace, use its Bash terminal and run:

```bash
export PYTHONPATH=src
python -m hedge_investment examples/investment_options.json --explain
```

In local Windows PowerShell, run:

```powershell
$env:PYTHONPATH = "src"
python -m hedge_investment examples/investment_options.json --explain
```

To use public SEC company facts with the legacy single-company portfolio format, set `SEC_USER_AGENT` to an application name and contact email, use real SEC-listed tickers in the input, and add `--sec-data`. The SEC asks automated clients to identify themselves with a User-Agent and to keep requests efficient; this connector fetches one company facts document per unique ticker. See the [SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) and [fair access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

```powershell
python -m hedge_investment path\to\your_portfolios.json --sec-data --explain
```

The Azure API key is read only from `AZURE_OPENAI_API_KEY`; never add a real key to JSON, source files, or Git. The default model/deployment name is `gpt6-astra`; endpoint, API version, and model can be overridden with the corresponding `AZURE_OPENAI_*` environment variables. The playground itself requires team login; this project calls its API endpoint directly using the SDK configuration from the hackathon sample.

If no file is passed, the command reads `examples/investment_options.json`. Its return assumptions are fictional demonstration values only, not forecasts or current market estimates. Replace them with reviewed, dated research before using the output. Do not run `src/hedge_investment/__init__.py` directly; Python must import the package for its relative imports to work.

The JSON return assumptions are decimals over the stated horizon: `0.04` means 4%, while `-0.12` means -12%. SEC data in the legacy mode covers public company filings and does not supply forward-looking return estimates.

## Development principles

1. Keep user objectives, constraints, horizon, currency, and liquidity needs explicit.
2. Separate source facts, analyst assumptions, model outputs, and AI-written explanation.
3. Show base and adverse scenarios for each asset and risk tier on the same capital and horizon.
4. Preserve citations and timestamps for every material claim; surface missing or stale data.
5. Expand public data sources only after licensing, point-in-time quality, and out-of-sample validation are established.
6. Present results for human review; do not describe scenario outputs as guaranteed or personalised investment advice.

## Challenge brief and scope

The supplied Bloomberg challenge brief asks teams to build an AI analyst for a defined client, use public data and an LLM, provide an evidence-based recommendation, and demonstrate a working solution. This product targets seed-stage hedge funds and £100,000 GBP. It now compares bonds, real estate, and the S&P 500, and produces risk-averse, average, and risk-seeking alternatives. The example still uses fictional returns; replace them with dated public-data research for a live demo. Outputs are educational decision support, not financial advice.

## Next steps

- Add a versioned input/output schema and a simple web interface.
- Add UK and other market public filing sources, with source links, dates, and extracted claim review.
- Add portfolio-level risk calculations only when a documented covariance or risk methodology is supplied.
- Add historical backtesting with point-in-time data and realistic transaction costs before presenting model performance claims.
- Keep a human approval step before any recommendation is used to trade.
