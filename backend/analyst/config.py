"""
config.py - single place for the universe, data sources and modelling assumptions.

Everything the optimiser treats as an ASSUMPTION (not data) lives in ASSUMPTIONS so it can be
shown on screen, exported to Excel, and changed by a teammate without touching model code.
"""

# ----------------------------------------------------------------------------------------------
# Universe: 11 holdable assets (9 priced, 1 token with no price history, 1 cash)
#   asset_id -> metadata. 'ticker' is the Yahoo Finance symbol used by yfinance.
#   'class' is used for class limits; 'sector' is used for exclusions; 'liquid' marks assets
#   sellable within ~2 trading days; 'options' marks equities we pull option chains for.
# Swap tickers freely - nothing else in the code is ticker specific.
# ----------------------------------------------------------------------------------------------
UNIVERSE = {
    "MSFT": dict(name="Microsoft", ticker="MSFT", cls="equities", sector="Technology",
                 liquid=True, options=True),
    "JNJ": dict(name="Johnson & Johnson", ticker="JNJ", cls="equities", sector="Healthcare",
                liquid=True, options=True),
    "JPM": dict(name="JPMorgan Chase", ticker="JPM", cls="equities", sector="Financials",
                liquid=True, options=True),
    "PG": dict(name="Procter & Gamble", ticker="PG", cls="equities", sector="Consumer Staples",
               liquid=True, options=True),
    "CAT": dict(name="Caterpillar", ticker="CAT", cls="equities", sector="Industrials",
                liquid=True, options=True),
    "WTI": dict(name="WTI crude oil (front-month futures)", ticker="CL=F", cls="commodities",
                sector="Energy", liquid=True, options=False),
    "NATGAS": dict(name="Henry Hub natural gas (front-month futures)", ticker="NG=F",
                   cls="commodities", sector="Energy", liquid=True, options=False),
    "UST10": dict(name="iShares 7-10yr Treasury ETF (10y Treasury proxy)", ticker="IEF",
                  cls="bonds", sector="Government bonds", liquid=True, options=False),
    "REIT": dict(name="Vanguard Real Estate ETF (listed REITs)", ticker="VNQ",
                 cls="real_estate", sector="Real estate", liquid=True, options=False),
    "TOKEN_RE": dict(name="Tokenized real estate token (pick one on RWA.xyz)", ticker=None,
                     cls="tokenized_real_estate", sector="Real estate", liquid=False,
                     options=False),
    "CASH": dict(name="Cash / 3-month T-bill", ticker=None, cls="cash", sector="Cash",
                 liquid=True, options=False),
}

BENCHMARK_TICKER = "SPY"          # market proxy for beta and event abnormal returns
HISTORY_PERIOD = "5y"             # price history window

# FRED series (public CSV endpoint, no key needed for fredgraph.csv)
FRED_SERIES = {
    "DGS10": "10-Year Treasury constant maturity yield (%)",
    "DTB3": "3-Month Treasury bill secondary market rate (%)",
    "DCOILWTICO": "WTI spot price (USD/bbl) - cross-check for CL=F",
    "DHHNGSP": "Henry Hub spot price (USD/MMBtu) - cross-check for NG=F",
}
# Yahoo fallbacks if FRED is unreachable (yield index quotes, in percent)
YAHOO_RATE_FALLBACK = {"DGS10": "^TNX", "DTB3": "^IRX"}

# ----------------------------------------------------------------------------------------------
# Modelling assumptions (NOT data). Shown on screen and exported to the Excel 'Assumptions' sheet.
# ----------------------------------------------------------------------------------------------
ASSUMPTIONS = {
    "erp_annual": dict(value=0.05, why="Equity risk premium used in the CAPM-style anchor: "
                       "mu = rf + beta * ERP. Round-number assumption; change freely."),
    "tilt_weight_phi": dict(value=0.25, why="Share of the signal tilt (event + momentum) added to the "
                            "anchor return. Low on purpose: expected returns are the noisiest input."),
    "tilt_cap": dict(value=0.03, why="Signal tilt capped at +/-3% over the horizon."),
    "momentum_lookback_days": dict(value=120, why="Momentum measured over 120 trading days."),
    "momentum_tilt_per_z": dict(value=0.01, why="1% horizon-return tilt per cross-sectional z-score "
                                "of momentum."),
    "event_shrink": dict(value=0.5, why="Past average earnings reaction shrunk 50% toward zero "
                         "because there are only ~8-12 events per stock."),
    "iv_blend": dict(value=0.5, why="Risk = 50% implied vol + 50% historical vol where option "
                     "data exists (options carry forward-looking information)."),
    "token_vol_multiple": dict(value=1.5, why="Tokenized real estate token has no price history. "
                               "Assume 1.5x the listed REIT's volatility (illiquidity premium)."),
    "token_corr_to_reit": dict(value=0.7, why="Assumed correlation of the token with the listed REIT; "
                               "correlations with other assets inherited from the REIT."),
    "token_yield_haircut": dict(value=0.25, why="Token yield haircut for fees, vacancy and "
                                "illiquidity: expected return = yield * (1 - 25%)."),
    "var_z": dict(value=1.645, why="One-sided 95% normal quantile for the 1-in-20 loss limit. "
                  "Normal tails understate real tail risk, hence the historical stress test."),
    "sharpe_keep": dict(value=0.98, why="Option B keeps at least 98% of the best achievable Sharpe ratio, "
                        "then uses the client's remaining risk budget to maximise expected return "
                        "(Sharpe alone is indifferent to how much cash is held)."),
    "ledoit_wolf": dict(value=True, why="Covariance shrinkage (Ledoit-Wolf) to stabilise the "
                        "optimiser with a short history."),
    "resample_draws": dict(value=60, why="Number of return-uncertainty resamples averaged to reduce "
                           "the optimiser's sensitivity to noisy expected returns."),
    "mean_obs_months": dict(value=63, why="Effective independent horizon-length observations (5y/20d) "
                            "used to size uncertainty in expected returns."),
    "risk_appetite_to_vol": dict(value={1: 0.06, 2: 0.09, 3: 0.12, 4: 0.16, 5: 0.22},
                                 why="Mapping from the client's 1-5 risk appetite to an annualised "
                                 "volatility cap. A design choice, not a measured trait."),
    "trading_days_per_year": dict(value=252, why="Annualisation convention."),
    "min_history_days": dict(value=250, why="Assets with less price history are rejected."),
}


def A(name):
    """Shortcut: get an assumption's value."""
    return ASSUMPTIONS[name]["value"]


# ----------------------------------------------------------------------------------------------
# Source register: one row per dataset - this is exported to the Excel 'Source_Register' sheet.
# ----------------------------------------------------------------------------------------------
SOURCE_REGISTER = [
    dict(dataset="Daily prices (equities, ETFs, futures)", provider="Yahoo Finance via yfinance",
         endpoint="yfinance.download()", url="https://finance.yahoo.com", key="No",
         history="5 years daily", used_for="Returns, volatility, correlations, beta, momentum, "
         "historical stress test",
         caveats="Unofficial library; not licensed for commercial use; adjusted closes; "
                 "no point-in-time guarantee; futures series are continuous front-month with roll gaps."),
    dict(dataset="Treasury yield and T-bill rate", provider="FRED (St. Louis Fed)",
         endpoint="https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10 and id=DTB3",
         url="https://fred.stlouisfed.org", key="No (CSV endpoint)", history="Daily",
         used_for="Bond carry (expected return), risk-free rate, cash return",
         caveats="Yahoo ^TNX / ^IRX used as fallback if FRED unreachable (recorded in meta)."),
    dict(dataset="Spot oil / gas (cross-check)", provider="FRED (DCOILWTICO, DHHNGSP)",
         endpoint="https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILWTICO",
         url="https://fred.stlouisfed.org", key="No", history="Daily",
         used_for="Sanity check of futures series only (not used in the optimiser)",
         caveats="Spot differs from futures by the roll/curve effect."),
    dict(dataset="Option chains -> ATM IV, skew, term slope", provider="Yahoo Finance via yfinance",
         endpoint="yfinance.Ticker.option_chain()", url="https://finance.yahoo.com", key="No",
         history="Current snapshot only (no history)",
         used_for="Forward-looking risk (implied vol blended into covariance); skew / term slope as flags",
         caveats="No history so the options layer cannot be backtested. Skew is a moneyness proxy "
                 "(95% put IV minus 105% call IV), not true 25-delta. American-style contracts."),
    dict(dataset="Earnings dates, EPS estimate/actual, surprise", provider="Yahoo Finance via yfinance",
         endpoint="yfinance.Ticker.get_earnings_dates()", url="https://finance.yahoo.com", key="No",
         history="Last ~12-16 quarters", used_for="Event study: 2-day abnormal return around earnings; "
         "next earnings date inside the horizon",
         caveats="Announcement time (before/after market) not recorded, so a 2-day window is used. "
                 "Estimates are not guaranteed to be contemporaneous consensus."),
    dict(dataset="Tokenized real estate token (yield, TVL, holders)", provider="RWA.xyz (manual entry)",
         endpoint="https://app.rwa.xyz (dashboard); API requires registration", url="https://app.rwa.xyz",
         key="Free registration for API", history="Snapshot",
         used_for="Expected return = yield x (1 - haircut); risk is an ASSUMPTION (see Assumptions)",
         caveats="Copied from the dashboard by hand into inputs/token_re.json. Ships as a PLACEHOLDER "
                 "until replaced. No price history exists, so risk and correlation are assumed."),
    dict(dataset="Company filings / news (for the LLM, optional)", provider="SEC EDGAR; Finnhub",
         endpoint="https://data.sec.gov (no key); https://finnhub.io (free key)", url="https://www.sec.gov/edgar",
         key="EDGAR: no (User-Agent header required); Finnhub: free key", history="Varies",
         used_for="Teammate extension: cited catalyst and risk notes for the shortlist",
         caveats="Not wired in this section. Hooks described in README."),
]
