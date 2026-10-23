# Hedge Investment Research Prototype

Prototype for a decision-support product for seed-stage hedge funds allocating up to £100,000. It compares a higher-risk strategy and a more defensive strategy, with an optional explanation from the hackathon Azure OpenAI endpoint and optional read-only public SEC company facts.

## What this prototype does

The command-line tool reads client and portfolio assumptions from JSON and converts them into comparable GBP scenarios. For each portfolio it reports the invested amount, cash reserve, weighted base and downside return assumptions, illustrative ending values, and largest position. Every holding carries a rationale and a source reference so a reviewer can trace the case. With `--explain`, the Azure model turns those supplied inputs into a client-oriented explanation. With `--sec-data`, it also retrieves latest reported company facts from SEC EDGAR for the tickers.

The calculations are scenario arithmetic, not forecasts. Return assumptions remain human-entered; the AI layer does not choose securities, estimate returns or probabilities, or execute trades. SEC facts are current public filing data, not a point-in-time backtest dataset. The AI must identify missing evidence and separate SEC-reported facts from user-entered assumptions.

## Inputs

The input JSON contains `capital_gbp` and exactly two portfolios. Each portfolio has a name, a risk profile (`defensive` or `aggressive`), a shared time horizon, and holdings. A holding contains:

- `ticker`: security identifier
- `weight`: fraction of the fund's capital, from 0 to 1
- `expected_return`: research team's base-case return over the stated horizon, as a decimal
- `downside_return`: research team's adverse scenario return over that same horizon, as a decimal
- `rationale`: concise investment thesis
- `source`: URL or internal research reference supporting the thesis and assumptions
- `sec_cik` (optional): SEC Central Index Key; use this when ticker resolution is ambiguous

An optional root-level `client_profile` object can include human-readable fields such as `fund_stage`, `objective`, `risk_tolerance`, `liquidity_needs`, and `constraints`. It is sent to the AI for context and does not change scenario arithmetic.

Weights may sum to less than 1; the remainder is treated as uninvested cash with a zero return. They may not exceed 1. Returns are not annualised by the calculator; both scenarios must refer to the portfolio's stated horizon.

## Run

Requires Python 3.10 or later. From the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m hedge_investment examples/portfolio_comparison.json
```

Install the Azure OpenAI client dependency before using the AI option:

```powershell
python -m pip install -r requirements.txt
```

Set `AZURE_OPENAI_API_KEY` as a Codespaces secret (recommended) or local environment variable. `.env.example` lists the available settings; copying it to `.env` does not load it automatically. In a GitHub Codespace, use its Bash terminal and run:

```bash
export PYTHONPATH=src
python -m hedge_investment examples/portfolio_comparison.json --explain
```

In local Windows PowerShell, run:

```powershell
$env:PYTHONPATH = "src"
python -m hedge_investment examples/portfolio_comparison.json --explain
```

To include public SEC company facts in the explanation, set `SEC_USER_AGENT` to an application name and contact email, use real SEC-listed tickers in the input, and add `--sec-data`. The SEC asks automated clients to identify themselves with a User-Agent and to keep requests efficient; this connector fetches one company facts document per unique ticker. See the [SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) and [fair access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

```powershell
python -m hedge_investment path\to\your_portfolios.json --sec-data --explain
```

The Azure API key is read only from `AZURE_OPENAI_API_KEY`; never add a real key to JSON, source files, or Git. Endpoint, API version, and model can be overridden with the corresponding `AZURE_OPENAI_*` environment variables. The playground itself requires team login; this project calls its API endpoint directly using the SDK configuration from the hackathon sample.

If no file is passed, the command reads the same fictional example. The sample uses fictitious identifiers and made-up assumptions only to demonstrate the interface. Replace them with reviewed, dated research before using the output. Do not run `src/hedge_investment/__init__.py` directly; Python must import the package for its relative imports to work.

The JSON return assumptions are decimals over the stated horizon: `0.04` means 4%, while `-0.12` means -12%. Weights are fractions of fund capital, so `0.5` means 50%. Weights may total less than 1; the remainder is treated as cash with a zero return. They may not exceed 1. SEC data covers US public company filings and does not supply UK-listed issuer coverage or forward-looking return estimates.

## Development principles

1. Keep user objectives, constraints, horizon, currency, and liquidity needs explicit.
2. Separate source facts, analyst assumptions, model outputs, and AI-written explanation.
3. Show base and adverse scenarios for both strategies on the same capital and horizon.
4. Preserve citations and timestamps for every material claim; surface missing or stale data.
5. Expand public data sources only after licensing, point-in-time quality, and out-of-sample validation are established.
6. Present results for human review; do not describe scenario outputs as guaranteed or personalised investment advice.

## Challenge brief and scope

The supplied Bloomberg challenge brief asks teams to build an AI analyst for a defined client, use public data and an LLM, provide a concrete evidence-based recommendation, and demonstrate a working solution. This product targets seed-stage hedge funds and £100,000 GBP. This prototype provides scenario comparison, an optional grounded LLM explanation, and optional public SEC data. Outputs are educational decision support, not financial advice. SEC coverage is US-focused, while the fund's operating market and jurisdiction still need to be specified for a production data source.

## Next steps

- Add a versioned input/output schema and a simple web interface.
- Add UK and other market public filing sources, with source links, dates, and extracted claim review.
- Add portfolio-level risk calculations only when a documented covariance or risk methodology is supplied.
- Add historical backtesting with point-in-time data and realistic transaction costs before presenting model performance claims.
- Keep a human approval step before any recommendation is used to trade.
