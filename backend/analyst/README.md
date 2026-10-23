# AI investment analyst - data, optimiser and chat layer

> Original teammate handoff reference. For the integrated HedgeHog V1, follow the repository-root README. Modules now use package-relative imports (`python -m backend.analyst.fetch_data --out data/market --no-excel`). The app uses the event Azure API, not the Anthropic CLI described below, and excludes placeholder TOKEN_RE. Local datasets are ignored and generated separately.

Educational hackathon project (Microsoft x LSEG). Model output, not financial advice.

A client describes themselves in chat -> the LLM turns that into a structured profile -> code does all
the maths on free public data -> the LLM explains three portfolios (A shield / B balanced / C growth).

## Quick start

```bash
pip install -r requirements.txt
python fetch_data.py                 # REAL data (needs internet) -> data/*.csv + data/data_pack.xlsx
python run_demo.py --check           # hypothetical client, prints 3 portfolios, verifies every client rule
export ANTHROPIC_API_KEY=...         # then:
python advisor.py                    # chat demo; the client types their profile
python advisor.py --selftest         # plumbing test, no API key needed
```

No internet? `python fetch_data.py --synthetic` makes clearly-labelled **SYNTHETIC** test data
(`data/data_pack_SYNTHETIC_test.xlsx`). The repo ships with that, so everything runs out of the box.
Never present synthetic numbers as real - the code stamps them in `meta.json`, the Excel banner and the LLM warnings.

## Files

| File | Job |
|---|---|
| `config.py` | Universe (11 assets), tickers, FRED series, every modelling assumption, source register. **Edit here first.** |
| `fetch_data.py` | Pulls prices (yfinance), rates (FRED), option chains, earnings history; writes `data/` and the Excel pack. |
| `build_excel.py` | Builds `data_pack.xlsx`: Source_Register, Universe, Prices, Rates, Options_IV, Earnings_Events, Next_Earnings, Token_RE, Stats, Assumptions. A source line sits on row 1 of every sheet. |
| `data_loader.py` | Reads `data/` into one `DataBundle`. |
| `client_profile.py` | Profile schema (the LLM tool input), validation, defaults, exclusions, percent -> fraction. |
| `optimizer.py` | **The model.** `recommend(profile_dict) -> dict` (JSON-safe). |
| `advisor.py` | **The LLM layer.** `SYSTEM_PROMPT`, `TOOLS`, `run_tool()`, `chat_turn()`; CLI chat demo. |
| `run_demo.py` | Hypothetical seed-fund client, printing and rule-verification. |
| `scenarios_check.py` | Sweeps risk appetite, exclusions, infeasible and invalid profiles. |
| `inputs/token_re.json` | Tokenized real estate token inputs (hand-copied from RWA.xyz). **Ships as a PLACEHOLDER.** |

## What the optimiser does (`optimizer.py`)

All over the client's horizon of H trading days.

* **Risk**: Ledoit-Wolf covariance of daily log returns x H. Optionable stocks: variance = 50% implied (30d ATM)
  + 50% historical, correlations kept. Earnings inside the horizon with no IV: add the stock's past earnings-reaction variance.
  Token: one-factor extension of the listed REIT (1.5x vol, 0.7 correlation - ASSUMPTIONS).
* **Expected return**: equities/REIT `rf + beta*ERP` anchor; commodities `rf`; bond = 10y yield carry; token = yield x (1-haircut);
  cash = 3m T-bill. Plus a small tilt `phi * clip(event + momentum)` (phi = 0.25, cap 3%). Expected returns are the noisiest input.
* **Constraints from the profile**: long-only, fully invested, single-holding cap, per-asset and per-class limits, illiquid cap
  (and "x% sellable in 2 days"), minimum cash, volatility cap from risk appetite (1-5 mapping is an assumption), and the
  1-in-20 loss limit `mu_p - 1.645 sigma_p >= -max_loss`.
* **Options**: A = minimum variance (return >= cash). B = best Sharpe (convex reformulation), then highest return while keeping 98% of
  that Sharpe. C = maximum expected return. Each is the **average over 60 resampled return vectors** to avoid corner portfolios, so
  "binding rules" can be empty; `tightest_rules` always lists the three closest rules.
* **Reporting**: expected return, volatility, Sharpe, 1-in-20 loss, P10/P50/P90, worst historical H-day window (stress test),
  tracking error vs SPY, risk share per holding, cost of relaxing the tightest rules, target-return feasibility,
  infeasibility diagnosis (which rule to relax).

## How the LLM fits

The LLM never sets a weight or a probability. It (1) extracts the profile into `build_portfolio`'s input, (2) reads the JSON that
`optimizer.recommend()` returns, (3) explains it using only numbers in that JSON. Re-calling the tool with changed fields = what-if.
To embed in your own UI: keep a `messages` list and call `advisor.chat_turn(client, messages)` for each user message.

## Extending (ideas for the next section)

* **News / filings**: pull EDGAR 8-K/10-K or Finnhub news per equity, have Claude extract cited catalysts, and add them under
  `asset_inputs[asset]["notes"]` in `build_model()`. Keep numbers out of the LLM; add only cited text.
* **More assets**: add to `config.UNIVERSE` keeping the order *priced assets ... TOKEN_RE, CASH* (asserted in `build_model`).
* **Real token data**: edit `inputs/token_re.json` (set `is_placeholder` false) or wire the RWA.xyz API after registering.
* **Backtest**: not built. A walk-forward test of the signal layers is the main missing piece of evidence.

## Honest limitations

* **Tested here only on synthetic data.** The real-data path in `fetch_data.py` (yfinance, FRED) was written but could not be run
  from the build environment (network blocked). Run it once and read the printed warnings; failures are per-source and non-fatal where possible.
  yfinance is unofficial - its API can change; the `get_earnings_dates` and `option_chain` calls are the most fragile.
* The live LLM loop in `advisor.py` was not run (no API key in the build environment); the tool schema, tool execution and JSON output were tested.
* Free data has no point-in-time history; option data is a current snapshot only (no backtest); futures series have roll gaps;
  skew is a 95%/105% moneyness proxy, not true 25-delta; earnings timing (before/after market) is not recorded so a 2-day window is used.
* The risk-appetite -> volatility mapping, ERP, token risk and haircut are assumptions, listed in the Excel `Assumptions` sheet.
* Normal-tail 1-in-20 limit understates fat tails; use the historical stress number alongside it.
* Only 11 assets and ~60 independent monthly observations: results are illustrative, not statistically proven.
