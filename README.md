# HedgeHog

A minimal client-to-portfolio workspace for the Microsoft x LSEG hackathon. FastAPI runs the team's financial model; React presents three ways to allocate **$100,000 USD**, with financial evidence and client-fit explanations.

## Version one

1. Enter the client's objective, horizon (1–26 weeks), risk appetite, acceptable modelled loss and concentration limit. Optional preferences describe explicit exclusions or investment bounds.
2. The event AI translates preferences into structured constraints. Unsupported assets, unverifiable ethical/political requirements and ambiguous preferences require clarification.
3. The supplied quantitative optimiser calculates Shield, Balanced and Growth portfolios. It controls all weights, returns and risk numbers. Infeasible rules are reported without silently relaxing them.
4. The dashboard suggests the option matching the objective and lets the analyst compare all three. Expand investments for financial/client reasoning, or the report details for applied constraints, sources and assumptions.

The interface stays deliberately small: a client form and a portfolio view. Client records exist only in browser memory and are cleared on reload. There is no authentication, database, trade execution or hosting.

The interface follows the supplied `hedgehog-ui-handoff.zip`: its blue design tokens, Newsreader/IBM Plex fonts, hedgehog logo and reduced-motion-aware loading animation. The overview groups actual allocations by investment type; opening a holding shows its allocation, client fit and source evidence in keyboard-accessible tabs. Google Fonts supplies the fonts, with system fallbacks. Sample clients, sample signals and MCP connection claims from the design are not shown as live features.

## Run locally

Dependencies, market data and the frontend build are already present in this checkout. The supplied event credentials are configured in the ignored root `.env`.

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open [HedgeHog](http://127.0.0.1:8000), choose **Use example**, then **Build portfolio**. A live run usually takes tens of seconds; the browser allows up to three minutes. Restart an older backend to load V1. If port 8000 is occupied, use `--port 8001` and open that port. Stop with Ctrl+C.

For frontend changes, rebuild and reload:

```powershell
npm.cmd --prefix frontend run build
```

For development, start the backend on port 8000 with `--reload`, then `npm.cmd --prefix frontend run dev` in another terminal. Vite serves port 5173 and proxies `/api` to 8000.

On a fresh checkout, install Python 3.12+ and Node 22.12+ (this checkout uses Python 3.12 and Node 24), then:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
Copy-Item .env.example .env
```

Only copy `.env.example` on a fresh setup; do not overwrite existing credentials. Set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT=gpt-6.1-sol`, and `AZURE_OPENAI_API_VERSION=2024-12-01-preview`. Process environment overrides `.env`. Keep keys out of frontend source and `VITE_` variables.

## Data

The supplied archive contains a generator, financial model and synthetic demonstration data, rather than an LSEG feed. V1 has fetched and uses **real public data** in ignored `data/market/`. Refresh explicitly:

```powershell
.\.venv\Scripts\python.exe -m backend.analyst.fetch_data --out data/market --no-excel
```

The current snapshot contains 1,258 daily observations from 2021-10-25 through 2026-10-23, a market benchmark, rate series, five equity options snapshots and 120 earnings events. Sources/statuses are recorded in `meta.json` and displayed in the report. Yahoo Finance supplies prices, options and earnings. FRED was unavailable during this fetch, so Treasury rates use the supplied Yahoo `^TNX`/`^IRX` fallback. Four equities have unusable implied volatility and transparently fall back to historical volatility. A snapshot date does not guarantee every input is current or a completed trading-day close.

The supported investments are MSFT, JNJ, JPM, PG, CAT, oil and natural-gas futures proxies, IEF (Treasury ETF), VNQ (REIT ETF), and cash/T-bills. Apple and gold are not in the supplied universe. **TOKEN_RE is always excluded by the web app** because its source data is a placeholder. Raw model demo scripts retain the teammate's original assumptions and may include that placeholder; use the web app for the V1 presentation.

For explicitly labelled synthetic development data:

```powershell
.\.venv\Scripts\python.exe -m backend.analyst.fetch_data --synthetic --out data/synthetic --no-excel
```

Set `ANALYST_DATA_DIR=data/synthetic` in `.env` and restart to use it. Default is `data/market`; there is no silent synthetic fallback. Switch back before a real-data demo. Tests generate their own temporary synthetic dataset and make no external API calls.

## Model and AI boundaries

The supplied model combines Ledoit–Wolf covariance, available implied volatility, a CAPM-style return anchor, small momentum/event adjustments, bond carry and a cash rate. It enforces long-only fully invested portfolios, asset/class bounds, liquidity, concentration, volatility and a normal-tail loss constraint. Sixty return resamples reduce sensitivity to a single estimated mean. Final amounts are rounded by largest remainder and rechecked against monetary bounds, totalling exactly 10,000,000 cents.

Risk appetite maps to assumed annual volatility caps of 6%, 9%, 12%, 16% and 22%. Age is optional context and does not infer beliefs or alter risk. The income objective uses the supplied minimum-risk proxy; it does not optimise distributions. Cash is exempt from the single-holding cap. A target return is assessed against the growth option, not promised or forced.

The Azure SDK configuration follows `mshack-example-python-master.zip`. The backend makes at most two structured Chat Completions calls per request: preference extraction (skipped for empty text) and a qualitative explanation. Validated numeric calculations stay in Python. Reference and age are omitted from the AI payload; free text is sent to the event service, so avoid identifying client information in those fields. Token usage is reported for successful structured responses; no currency-cost claim is made without event pricing.

If preference extraction fails, the request fails clearly rather than ignoring constraints. If only the explanation fails, valid portfolios still appear with deterministic model reasoning. The dataset has no verified company ESG/political-activity coverage, so broad alignment requests need clarification rather than invented screening. There is no walk-forward backtest, transaction-cost model, lot sizing or guarantee of profit. Futures are research proxies, not executable $1 fractional positions. Historical stress can exceed a normal-tail loss limit and is shown explicitly.

## Source map

### Microsoft evidence update (demo)

Open Microsoft in the portfolio and press **Update**. FastAPI connects over stdio to the local `backend.mcp_msft.server` using the official Python MCP SDK, discovers its read-only `refresh_microsoft` tool and calls it. This is a HedgeHog-built MCP connector, not an MCP server supplied by Microsoft. No separate process setup, credentials or new API key is needed; install the updated requirements and restart the backend.

The tool retrieves Microsoft's official Source RSS feed and MSFT adjusted daily history through Yahoo Finance. It shows retrieval time, source dates and linked announcements, then compares price, historical volatility and momentum direction with the real local baseline when their dates are comparable. It marks an older observation, synthetic baseline or missing source as unverified. One-percent price movement, three percentage points of volatility change or a momentum direction change trigger review; these are disclosed demo thresholds. Company announcements require human review. Expected-return assumptions, options data and client alignment are not automatically revalidated.

The refresh endpoint is `POST /api/holdings/MSFT/update`; other tickers have no endpoint. Updates never write the cached dataset or alter the generated allocations. Failure stays inside the holding panel and can be retried. The sources may be delayed or unavailable. No AI call or client-identifying information is needed for this update. SDK implementation reference: [official MCP Python v1 documentation](https://py.sdk.modelcontextprotocol.io/v1/).

For the 23 October demo, the connector also fetches and parses Microsoft's [7 October earnings announcement](https://news.microsoft.com/source/2026/10/07/microsoft-announces-quarterly-earnings-release-date-69/). Its confirmed 28 October results date falls within the example client's four-week horizon. Update surfaces **Action needed: Microsoft earnings in 5 days**, with a suggested change to the execution plan: require an earnings-risk review before funding and refresh inputs after results. The announcement URL is pinned for the demo, but the event is read from the live page; a failed fetch or an expired/out-of-horizon event cannot fabricate this flag. The panel discloses when the cached earnings calendar already contains the date. This is independent confirmation of event exposure, not evidence that the optimiser missed it or that a position cut is numerically justified.

| Location | Responsibility |
| --- | --- |
| `backend/app/models.py` | Validated intake and portfolio contracts |
| `backend/app/pipeline.py` | Constraint mapping, optimisation, rounding and report assembly |
| `backend/app/llm.py` | Event Azure API, structured preferences and explanations |
| `backend/analyst/` | Adapted teammate model, data fetcher, original handoff documents |
| `frontend/src/components/ClientForm.jsx` | Minimal client intake |
| `frontend/src/components/Portfolio.jsx` | Portfolio comparison and expandable evidence |
| `docs/HACKATHON.md` | Organiser source notes and current scope |

The original analyst package is retained for reference. Integration changes include package-relative imports, full-precision holdings for cent rounding, serial Yahoo downloads to avoid a cache lock, required-price checks and aligned stock/benchmark earnings windows. Its original Anthropic chat CLI is not used or required by the app; follow this README for setup.

## API and checks

- `POST /api/recommendations`: `ready`, `needs_clarification` or `infeasible`; HTTP 422 for invalid intake, 503 for unavailable data/preference analysis. Responses are not cached.
- `GET /api/status`: dataset metadata and configuration presence; this does not perform a connectivity test or expose credentials.
- `GET /api/health`: local service health.
- [Interactive API docs](http://127.0.0.1:8000/docs).

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
npm.cmd --prefix frontend run build
```

V1 was checked with 24 offline backend tests, the supplied model's rule verifier, a live real-data/event-API request, and browser interaction. Tests cover budget totals, risk/exclusion/concentration limits, clarification, infeasibility, outages, missing data, input validation and credential isolation. The local installed Starlette test adapter emits a non-failing httpx deprecation warning.
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
