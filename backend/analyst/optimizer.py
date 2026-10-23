"""
optimizer.py - client profile + cached data  ->  three optimal portfolios (A shield / B balanced / C growth).

    from optimizer import recommend
    result = recommend(profile_dict)          # JSON-serialisable dict, safe to hand to an LLM

Maths (all over the client's horizon H trading days):
  risk     Sigma_H = H * LedoitWolf(daily log-return covariance), vol of optionable stocks blended with
           implied vol, token risk derived from the listed REIT (assumption).
  return   mu_i = anchor_i + phi * clip(tilt_i): CAPM-style anchor + small event/momentum tilt;
           bond = carry; token = yield after haircut; cash = T-bill.
  options  A  min variance                       s.t. constraints and mu_p >= rf
           B  max Sharpe (convex reformulation)  s.t. constraints
           C  max expected return                s.t. constraints (vol cap + 1-in-20 loss limit bind)
  robust   each option is the average of solutions over resampled mu (return uncertainty).
The LLM never touches these numbers; it only parses the profile and explains the output.
"""
import itertools
from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

from . import client_profile
from . import config
from . import data_loader

Z = config.A("var_z")
SOLVER = cp.CLARABEL
BIND_TOL = 5e-4

GROUP_TEXT = {
    "long_only": "long-only (no shorting)",
    "single_cap": "maximum single holding",
    "asset_limits": "per-asset limits",
    "class_limits": "asset-class limits",
    "illiquid": "illiquid / 2-day-sellable limit",
    "cash_min": "minimum cash",
    "vol_cap": "volatility cap from risk appetite",
    "var_limit": "1-in-20 loss limit",
}


class ModelError(Exception):
    pass


def _f(x, nd=6):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), nd)


# ----------------------------------------------------------------------------------------------
# 1. Build expected returns and covariance
# ----------------------------------------------------------------------------------------------
@dataclass
class Model:
    ids: list
    mu: np.ndarray
    Sigma: np.ndarray
    G: np.ndarray                 # Sigma = G G'
    rf_H: float
    H: int
    details: dict
    hist_returns: pd.DataFrame    # daily arithmetic returns incl. token proxy and cash
    warnings: list = field(default_factory=list)


def _factor(S):
    vals, vecs = np.linalg.eigh((S + S.T) / 2)
    vals = np.clip(vals, 0, None)
    return vecs * np.sqrt(vals)


def build_model(bundle, P):
    H = P["horizon_days"]
    td = config.A("trading_days_per_year")
    rf_H = bundle.rf_annual * H / td
    warn = []

    priced = [a for a, u in config.UNIVERSE.items() if u["ticker"]]
    miss = [a for a in priced + ["MKT"] if a not in bundle.prices.columns or bundle.prices[a].dropna().empty]
    if miss:
        raise ModelError(f"Missing price data for {sorted(miss)}. Re-run fetch_data.py "
                         f"(or change the tickers in config.py).")

    px = bundle.prices[priced + ["MKT"]].dropna()
    if len(px) < config.A("min_history_days"):
        raise ModelError(f"Only {len(px)} common price days; need {config.A('min_history_days')}.")
    R = np.log(px / px.shift(1)).dropna()
    S = LedoitWolf().fit(R[priced].values).covariance_ if config.A("ledoit_wolf") else R[priced].cov().values
    hist_vol = np.sqrt(np.diag(S) * td)

    # --- implied-vol blend (rescale vols, keep correlations)
    d = np.ones(len(priced))
    iv_used = {}
    for i, a in enumerate(priced):
        if len(bundle.options) and a in bundle.options.index:
            iv = bundle.options.loc[a, "atm_iv_30"]
            if pd.notna(iv) and 0.05 < iv < 2.0:
                blend = np.sqrt(config.A("iv_blend") * iv ** 2 + (1 - config.A("iv_blend")) * hist_vol[i] ** 2)
                d[i] = blend / hist_vol[i]
                iv_used[a] = float(iv)
            else:
                warn.append(f"{a}: implied vol unusable ({iv}); using historical vol.")
    S = S * np.outer(d, d)
    SH = S * H

    # --- earnings inside the horizon: add event variance where IV did not already capture it
    cal_days = int(H * 7 / 5) + 1
    ev_info = {}
    events = bundle.events if len(bundle.events) and "asset" in bundle.events else pd.DataFrame(columns=["asset", "car_2day"])
    for a in priced:
        ev = events[events["asset"] == a]["car_2day"].dropna()
        nxt = bundle.next_earnings.get(a)
        days = (nxt - bundle.asof).days if nxt is not None else None
        inside = days is not None and 0 <= days <= cal_days
        ev_info[a] = dict(n=len(ev), mean=float(np.mean(ev)) if len(ev) else None,
                          std=float(np.std(ev, ddof=1)) if len(ev) > 2 else None, next=nxt, days=days, inside=inside)
        if inside and a not in iv_used and ev_info[a]["std"]:
            SH[priced.index(a), priced.index(a)] += ev_info[a]["std"] ** 2

    # --- token as a one-factor extension of the listed REIT (PSD by construction)
    rho, mult = config.A("token_corr_to_reit"), config.A("token_vol_multiple")
    b_tok = rho * mult
    r = priced.index("REIT")
    n_p = len(priced)
    full = list(config.UNIVERSE)                      # priced..., TOKEN_RE, CASH (see config order)
    assert full[:n_p] == priced and full[n_p:] == ["TOKEN_RE", "CASH"], "UNIVERSE order changed"
    SF = np.zeros((n_p + 2, n_p + 2))
    SF[:n_p, :n_p] = SH
    SF[n_p, :n_p] = SF[:n_p, n_p] = b_tok * SH[r, :]
    SF[n_p, n_p] = (mult ** 2) * SH[r, r]

    # --- expected returns
    ret_basis, mu = {}, np.zeros(n_p + 2)
    mom = {}
    lb = config.A("momentum_lookback_days")
    risk_set = [a for a in priced if config.UNIVERSE[a]["cls"] in ("equities", "real_estate", "commodities")]
    for a in risk_set:
        s = bundle.prices[a].dropna()
        mom[a] = float(s.iloc[-1] / s.iloc[-1 - lb] - 1) if len(s) > lb else np.nan
    mv = pd.Series(mom)
    zs = ((mv - mv.mean()) / mv.std(ddof=0)).fillna(0.0) if mv.std(ddof=0) > 0 else mv * 0.0

    last252 = R.tail(252)
    beta = {a: float(np.cov(last252[a], last252["MKT"])[0, 1] / last252["MKT"].var()) for a in priced}
    erp_H = config.A("erp_annual") * H / td
    phi, cap = config.A("tilt_weight_phi"), config.A("tilt_cap")

    tilt = {}
    for i, a in enumerate(priced):
        cls = config.UNIVERSE[a]["cls"]
        if cls in ("equities", "real_estate"):
            anchor, basis = rf_H + beta[a] * erp_H, "CAPM anchor rf + beta*ERP, plus small event/momentum tilt"
        elif cls == "commodities":
            anchor, basis = rf_H, "risk-free anchor (no roll-yield model), plus small momentum tilt"
        else:  # bonds
            anchor, basis = bundle.y10_annual * H / td, "carry only: 10y Treasury yield * H/252 (no price-change forecast)"
        e = ev_info[a]
        ev_ev = (config.A("event_shrink") * e["mean"]) if (e["inside"] and e["n"] >= 4 and e["mean"] is not None) else 0.0
        t = float(np.clip(ev_ev + config.A("momentum_tilt_per_z") * zs.get(a, 0.0), -cap, cap)) if cls != "bonds" else 0.0
        tilt[a] = dict(event_ev=ev_ev, tilt=t)
        mu[i] = anchor + phi * t
        ret_basis[a] = basis
    yld = float(bundle.token.get("yield_apy_pct", np.nan)) / 100
    mu[n_p] = yld * (1 - config.A("token_yield_haircut")) * H / td
    ret_basis["TOKEN_RE"] = "RWA.xyz yield * (1 - haircut) * H/252" + (" [PLACEHOLDER INPUT]" if bundle.token.get("is_placeholder") else "")
    mu[n_p + 1] = rf_H
    ret_basis["CASH"] = "3-month T-bill"
    if bundle.token.get("is_placeholder"):
        warn.append("TOKEN_RE inputs are a PLACEHOLDER (assumed yield). Replace with a real token from RWA.xyz.")

    # --- historical daily returns incl. token proxy and cash (for stress test)
    arith = bundle.prices[priced].pct_change().dropna()
    hist = arith.copy()
    hist["TOKEN_RE"] = b_tok * arith["REIT"]
    hist["CASH"] = bundle.rf_annual / td
    hist["MKT"] = bundle.prices["MKT"].pct_change().reindex(hist.index)

    # --- details per asset (for the explanation layer)
    details = {}
    for i, a in enumerate(full):
        u = config.UNIVERSE[a]
        dd = dict(name=u["name"], cls=u["cls"], sector=u["sector"], liquid=u["liquid"],
                  mu_horizon_pct=_f(mu[i] * 100, 3), vol_annual_pct=_f(np.sqrt(SF[i, i] * td / H) * 100, 2),
                  return_basis=ret_basis[a])
        if a in priced:
            e = ev_info.get(a, {})
            dd.update(beta=_f(beta[a], 2), momentum_120d_pct=_f(mom.get(a, np.nan) * 100, 1) if a in mom else None,
                      momentum_z=_f(zs.get(a, 0.0), 2) if a in mom else None,
                      vol_basis=("50/50 blend of option-implied and historical vol" if a in iv_used else "historical vol (Ledoit-Wolf shrunk)"))
            if config.UNIVERSE[a]["options"]:
                row = bundle.options.loc[a] if len(bundle.options) and a in bundle.options.index else None
                dd.update(next_earnings=str(e["next"].date()) if e.get("next") is not None else None,
                          days_to_earnings=e.get("days"), earnings_inside_horizon=bool(e.get("inside")),
                          past_earnings_events=e.get("n"), avg_2day_reaction_pct=_f(e["mean"] * 100, 2) if e.get("mean") is not None else None,
                          reaction_std_pct=_f(e["std"] * 100, 2) if e.get("std") else None,
                          event_tilt_pct=_f(tilt[a]["event_ev"] * 100, 2),
                          iv_30d_pct=_f(row["atm_iv_30"] * 100, 1) if row is not None else None,
                          skew_proxy_pct=_f(row["skew_30"] * 100, 1) if row is not None else None,
                          term_slope_pct=_f(row["term_slope"] * 100, 1) if row is not None else None,
                          implied_move_30d_pct=_f(row["atm_straddle_pct_30"] * 100, 1) if row is not None else None)
        elif a == "TOKEN_RE":
            dd.update(vol_basis=f"ASSUMPTION: {mult}x REIT vol, {rho} correlation to REIT",
                      token_name=str(bundle.token.get("name")), token_tvl_usd=bundle.token.get("tvl_usd"),
                      token_holders=bundle.token.get("holders"), placeholder=bool(bundle.token.get("is_placeholder")))
        details[a] = dd

    ids = full
    return Model(ids=ids, mu=mu, Sigma=SF, G=_factor(SF), rf_H=rf_H, H=H, details=details,
                 hist_returns=hist, warnings=warn)


def subset(m, P):
    """Drop excluded assets (cash is always kept)."""
    keep = [i for i, a in enumerate(m.ids) if a not in P["excluded"]]
    ids = [m.ids[i] for i in keep]
    S = m.Sigma[np.ix_(keep, keep)]
    return Model(ids=ids, mu=m.mu[keep], Sigma=S, G=_factor(S), rf_H=m.rf_H, H=m.H,
                 details={a: m.details[a] for a in ids}, hist_returns=m.hist_returns, warnings=m.warnings)


# ----------------------------------------------------------------------------------------------
# 2. Constraints and solving
# ----------------------------------------------------------------------------------------------
def _bounds_for(m, P, relax):
    n = len(m.ids)
    lo, hi = np.zeros(n), np.ones(n)
    single = min(1.0, P["max_single"] + relax.get("single_cap", 0.0))
    for i, a in enumerate(m.ids):
        if a != "CASH":
            hi[i] = single
        if a in P["asset_bounds"]:
            lo[i] = max(lo[i], P["asset_bounds"][a][0])
            hi[i] = min(hi[i], P["asset_bounds"][a][1])
    return lo, hi, single


def make_constraints(m, P, w, kappa, mu, relax=None, fully_invested=True):
    relax = relax or {}
    n, ids = len(m.ids), m.ids
    lo, hi, single = _bounds_for(m, P, relax)
    g = {"long_only": [w >= 0]}
    g["single_cap"] = [w[i] <= single * kappa for i, a in enumerate(ids) if a != "CASH"]
    g["asset_limits"] = []
    for a, (l, h) in P["asset_bounds"].items():
        if a in ids:
            i = ids.index(a)
            g["asset_limits"] += [w[i] >= l * kappa, w[i] <= h * kappa]
        elif l > 0:
            g["asset_limits"].append(cp.Constant(0.0) >= l * kappa)
    g["class_limits"] = []
    for cls, (l, h) in P["class_bounds"].items():
        idx = [i for i, a in enumerate(ids) if config.UNIVERSE[a]["cls"] == cls]
        if idx:
            g["class_limits"] += [cp.sum(w[idx]) >= l * kappa, cp.sum(w[idx]) <= h * kappa]
        elif l > 0:
            g["class_limits"].append(cp.Constant(0.0) >= l * kappa)
    il = [i for i, a in enumerate(ids) if not config.UNIVERSE[a]["liquid"]]
    g["illiquid"] = [cp.sum(w[il]) <= min(1.0, P["illiquid_cap"] + relax.get("illiquid", 0.0)) * kappa] if il else []
    g["cash_min"] = [w[ids.index("CASH")] >= P["cash_min"] * kappa] if P["cash_min"] else []
    vol_h = P["vol_cap_annual"] * (1 + relax.get("vol_cap", 0.0)) * np.sqrt(m.H / config.A("trading_days_per_year"))
    risk = cp.norm(m.G.T @ w, 2)
    g["vol_cap"] = [risk <= vol_h * kappa]
    g["var_limit"] = [mu @ w - Z * risk >= -P["max_loss"] * (1 + relax.get("var_limit", 0.0)) * kappa]
    if fully_invested:
        g["_budget"] = [cp.sum(w) == 1]
    return g


def _flat(groups, drop=()):
    return [c for k, v in groups.items() if k not in drop for c in v]


class Prepared:
    """A cvxpy problem built once with mu as a Parameter, so resampling just updates mu and re-solves."""

    def __init__(self, kind, m, P, relax=None, drop=(), floor=True):
        self.kind, self.m = kind, m
        n = len(m.ids)
        self.mu = cp.Parameter(n)
        if kind == "B":
            # stage 1: best achievable Sharpe, via the convex reformulation (y = w * kappa)
            y = cp.Variable(n, nonneg=True)
            groups = make_constraints(m, P, y, cp.sum(y), self.mu, relax, fully_invested=False)
            self.prob1 = cp.Problem(cp.Minimize(cp.sum_squares(m.G.T @ y)),
                                    _flat(groups, drop) + [(self.mu - m.rf_H) @ y == 1])
            self.y = y
            # stage 2: keep >= sharpe_keep of that Sharpe, then use the remaining risk budget for return
            w = cp.Variable(n)
            groups2 = make_constraints(m, P, w, 1.0, self.mu, relax)
            self.s = cp.Parameter(nonneg=True)
            self.prob = cp.Problem(cp.Maximize(self.mu @ w),
                                   _flat(groups2, drop) + [(self.mu - m.rf_H) @ w >= self.s * cp.norm(m.G.T @ w, 2)])
            self.var = w
        else:
            w = cp.Variable(n)
            groups = make_constraints(m, P, w, 1.0, self.mu, relax)
            cons = _flat(groups, drop)
            if kind == "A":
                if floor:
                    cons.append(self.mu @ w >= m.rf_H)
                self.prob = cp.Problem(cp.Minimize(cp.sum_squares(m.G.T @ w)), cons)
            else:
                self.prob = cp.Problem(cp.Maximize(self.mu @ w), cons)
            self.var = w

    @staticmethod
    def _run(prob, var):
        try:
            prob.solve(solver=SOLVER)
        except cp.error.SolverError:
            return None
        if prob.status not in ("optimal", "optimal_inaccurate") or var.value is None:
            return None
        x = np.clip(np.asarray(var.value, float), 0, None)
        s = x.sum()
        return x / s if s > 1e-9 else None

    def solve(self, mu):
        mu = np.asarray(mu, float)
        self.mu.value = mu
        if self.kind != "B":
            return self._run(self.prob, self.var)
        w1 = self._run(self.prob1, self.y)
        if w1 is None:
            return None
        risk, exc = float(np.linalg.norm(self.m.G.T @ w1)), float((mu - self.m.rf_H) @ w1)
        if risk <= 1e-12 or exc <= 1e-12:
            return w1
        self.s.value = config.A("sharpe_keep") * exc / risk
        w2 = self._run(self.prob, self.var)
        return w2 if w2 is not None else w1


def diagnose_infeasible(m, P, mu):
    names = [k for k in GROUP_TEXT if k != "long_only"]
    for r in (1, 2):
        hits = []
        for combo in itertools.combinations(names, r):
            if Prepared("C", m, P, drop=set(combo)).solve(mu) is not None:
                hits.append(combo)
        if hits:
            return [[GROUP_TEXT[k] for k in c] for c in hits]
    return []


# ----------------------------------------------------------------------------------------------
# 3. Reporting helpers
# ----------------------------------------------------------------------------------------------
def constraint_report(m, P, w, mu):
    ids = m.ids
    lo, hi, single = _bounds_for(m, P, {})
    risk = float(np.sqrt(w @ m.Sigma @ w))
    vol_h = P["vol_cap_annual"] * np.sqrt(m.H / config.A("trading_days_per_year"))
    out = []

    def add(group, text, slack):
        out.append(dict(group=group, rule=text, slack_pct=_f(slack * 100, 3), binding=bool(slack <= BIND_TOL)))

    for i, a in enumerate(ids):
        if a != "CASH":
            add("single_cap", f"{a} vs max single holding {single*100:g}%", single - w[i])
        if a in P["asset_bounds"]:
            l, h = P["asset_bounds"][a]
            add("asset_limits", f"{a} upper limit {h*100:g}%", h - w[i])
            if l > 0:
                add("asset_limits", f"{a} lower limit {l*100:g}%", w[i] - l)
    for cls, (l, h) in P["class_bounds"].items():
        s = sum(w[i] for i, a in enumerate(ids) if config.UNIVERSE[a]["cls"] == cls)
        add("class_limits", f"{cls} upper limit {h*100:g}%", h - s)
        if l > 0:
            add("class_limits", f"{cls} lower limit {l*100:g}%", s - l)
    il = [i for i, a in enumerate(ids) if not config.UNIVERSE[a]["liquid"]]
    if il:
        add("illiquid", f"illiquid assets vs cap {P['illiquid_cap']*100:g}%", P["illiquid_cap"] - w[il].sum())
    if P["cash_min"]:
        add("cash_min", f"cash vs minimum {P['cash_min']*100:g}%", w[ids.index('CASH')] - P["cash_min"])
    add("vol_cap", f"volatility vs cap {P['vol_cap_annual']*100:g}% annualised (risk appetite {P['risk_appetite']})", vol_h - risk)
    add("var_limit", f"1-in-20 loss vs limit -{P['max_loss']*100:g}%", float(mu @ w - Z * risk + P["max_loss"]))
    return out


def stress_and_benchmark(m, P, w):
    ids = m.ids
    hr = m.hist_returns
    pr = sum(w[i] * hr[a] for i, a in enumerate(ids) if w[i] > 1e-9)
    roll = np.log1p(pr).rolling(m.H).sum().dropna()
    worst = float(np.expm1(roll.min())) if len(roll) else np.nan
    te = float((pr - hr["MKT"]).dropna().std() * np.sqrt(m.H)) if "MKT" in hr else np.nan
    return worst, te


def portfolio_metrics(m, P, w, mu):
    Sw = m.Sigma @ w
    var = float(w @ Sw)
    sig = np.sqrt(max(var, 0.0))
    mu_p = float(mu @ w)
    td = config.A("trading_days_per_year")
    worst, te = stress_and_benchmark(m, P, w)
    rc = (w * Sw / var) if var > 0 else np.zeros_like(w)
    return dict(
        expected_return_pct=_f(mu_p * 100, 3), vol_horizon_pct=_f(sig * 100, 3),
        vol_annualised_pct=_f(sig * np.sqrt(td / m.H) * 100, 2),
        sharpe_annualised=_f(((mu_p - m.rf_H) / sig) * np.sqrt(td / m.H), 2) if sig > 1e-9 else None,
        loss_1_in_20_pct=_f((mu_p - Z * sig) * 100, 2),
        p10_p50_p90_return_pct=[_f((mu_p - 1.2816 * sig) * 100, 2), _f(mu_p * 100, 2), _f((mu_p + 1.2816 * sig) * 100, 2)],
        worst_historical_horizon_return_pct=_f(worst * 100, 2),
        stress_breaches_loss_limit=bool(np.isfinite(worst) and worst < -P["max_loss"]),
        historical_tracking_error_vs_SPY_pct=_f(te * 100, 2),
        risk_share_pct={a: _f(rc[i] * 100, 1) for i, a in enumerate(m.ids) if w[i] > 5e-4}), mu_p, sig


# ----------------------------------------------------------------------------------------------
# 4. Top level
# ----------------------------------------------------------------------------------------------
def recommend(raw_profile, data_dir=None, bundle=None, seed=11):
    P, rep = client_profile.normalise(raw_profile)
    if P is None:
        return dict(status="NEEDS_INPUT" if rep["missing"] else "INVALID_PROFILE", **rep)
    bundle = bundle or data_loader.load(data_dir)
    try:
        m_full = build_model(bundle, P)
    except ModelError as e:
        return dict(status="DATA_ERROR", message=str(e))
    m = subset(m_full, P)
    mu0 = m.mu.copy()

    # feasibility of the client's rules (using the base expected returns)
    if Prepared("C", m, P).solve(mu0) is None:
        return dict(status="INFEASIBLE", profile_notes=rep["notes"], assumed_defaults=rep["assumed_defaults"],
                    message="No portfolio satisfies all of the client's rules together.",
                    relaxing_any_one_of_these_would_make_it_feasible=diagnose_infeasible(m, P, mu0))

    rng = np.random.default_rng(seed)
    T = config.A("mean_obs_months")
    draws = config.A("resample_draws")
    shocks = [m.G @ rng.standard_normal(len(m.ids)) / np.sqrt(T) for _ in range(draws)]

    options, notes = {}, list(rep["notes"])
    for kind, label in (("A", "Capital shield (minimum risk)"),
                        ("B", "Balanced core (best risk-adjusted return)"),
                        ("C", "Growth (return-seeking within the client's limits)")):
        prob = Prepared(kind, m, P)
        w0 = prob.solve(mu0)
        fallback_note, can_resample = None, True
        if w0 is None and kind == "A":
            # the 'at least as good as cash' return floor made it infeasible -> plain minimum variance
            prob = Prepared("A", m, P, floor=False)
            w0 = prob.solve(mu0)
            fallback_note = "Return floor (at least the cash return) could not be met; this is the plain minimum-risk portfolio."
        elif w0 is None and kind == "B":
            fallback_note = "No feasible portfolio has positive excess return over cash; showing option A's portfolio."
            w0, can_resample = options["A"]["_w"], False
        sols = [s for s in (prob.solve(mu0 + sh) for sh in shocks) if s is not None] if can_resample else []
        w, resampled = w0, False
        if len(sols) >= draws // 2:
            wa = np.mean(sols, axis=0)
            worst_viol = max([-r["slack_pct"] / 100 for r in constraint_report(m, P, wa, mu0)] + [0])
            if worst_viol < 1e-5:
                w, resampled = wa, True
            else:
                notes.append(f"Option {kind}: resampled average slightly violated a rule under base returns; showing the base solution.")
        metrics, mu_p, sig = portfolio_metrics(m, P, w, mu0)
        rules = constraint_report(m, P, w, mu0)
        opt = dict(label=label, resampled_average=resampled, note=fallback_note,
                   holdings=[dict(asset=a, name=m.details[a]["name"], weight=float(w[i]),
                                  weight_pct=_f(w[i] * 100, 6), amount=round(float(w[i] * P["capital"]), 2))
                             for i, a in sorted(enumerate(m.ids), key=lambda t: -w[t[0]]) if w[i] > 1e-12],
                   metrics=metrics, binding_rules=[r["rule"] + f" (slack {r['slack_pct']}pp)" for r in rules if r["binding"]],
                   tightest_rules=[f"{r['rule']} (slack {r['slack_pct']}pp)" for r in
                                   sorted((r for r in rules if r["group"] != "long_only"), key=lambda r: r["slack_pct"])[:3]],
                   _w=w, _rules=rules, _mu_p=mu_p, _sig=sig, _kind=kind)
        if P["target_return"] is not None:
            opt["meets_target_return"] = bool(mu_p >= P["target_return"])
        options[kind] = opt

    rec = client_profile.OBJECTIVE_TO_OPTION[P["objective"]]

    # what the tightest rules cost in the recommended option (base-return solutions, relaxed vs not)
    cost = []
    kind = rec
    w_ref = Prepared(kind, m, P).solve(mu0)
    tight_groups = {r["group"] for r in sorted((r for r in options[kind]["_rules"] if r["group"] != "long_only"),
                                               key=lambda r: r["slack_pct"])[:3]}
    for grp in sorted(tight_groups & {"vol_cap", "var_limit", "single_cap", "illiquid"}):
        relax = {"vol_cap": 0.25, "var_limit": 0.25, "single_cap": 0.05, "illiquid": 0.05}[grp]
        w2 = Prepared(kind, m, P, relax={grp: relax}).solve(mu0)
        if w2 is not None and w_ref is not None:
            dmu = float(mu0 @ w2 - mu0 @ w_ref) * 100
            dsg = float(np.sqrt(w2 @ m.Sigma @ w2) - np.sqrt(w_ref @ m.Sigma @ w_ref)) * 100
            what = {"vol_cap": "volatility cap 25% looser", "var_limit": "loss limit 25% looser",
                    "single_cap": "single-holding cap +5pp", "illiquid": "illiquid cap +5pp"}[grp]
            if abs(dmu) < 5e-4 and abs(dsg) < 5e-4:
                continue                      # relaxing this rule changes nothing: it is not what limits the portfolio
            cost.append(dict(if_relaxed=what, change_in_expected_return_pp=_f(dmu, 3), change_in_vol_pp=_f(dsg, 3)))

    max_ret = options["C"]["_mu_p"]
    out = dict(
        status="OK", data_mode=bundle.meta.get("mode"), data_as_of=str(bundle.asof.date()),
        data_retrieved_at=bundle.meta.get("retrieved_at"),
        client=dict(capital=P["capital"], currency=P["currency"], horizon_trading_days=P["horizon_days"],
                    objective=P["objective"], risk_appetite=P["risk_appetite"],
                    vol_cap_annual_pct=_f(P["vol_cap_annual"] * 100, 1), max_loss_pct=_f(P["max_loss"] * 100, 1),
                    max_single_holding_pct=_f(P["max_single"] * 100, 1), illiquid_cap_pct=_f(P["illiquid_cap"] * 100, 1),
                    excluded_assets=sorted(P["excluded"])),
        risk_free_horizon_pct=_f(m.rf_H * 100, 3),
        recommended_option=rec, options={k: {a: b for a, b in v.items() if not a.startswith("_")} for k, v in options.items()},
        cost_of_tight_rules_in_recommended_option=cost,
        target_return=None if P["target_return"] is None else dict(
            target_pct=_f(P["target_return"] * 100, 2), max_expected_return_achievable_pct=_f(max_ret * 100, 2),
            achievable=bool(max_ret >= P["target_return"])),
        asset_inputs=m.details, profile_notes=notes, assumed_defaults=rep["assumed_defaults"],
        warnings=list(dict.fromkeys(bundle.warnings + m.warnings)),
        assumptions={k: dict(value=str(v["value"]), why=v["why"]) for k, v in config.ASSUMPTIONS.items()
                     if k not in ("trading_days_per_year", "min_history_days")},
        method="Mean-variance optimisation with Ledoit-Wolf covariance, implied-vol blend, resampled expected "
               "returns. Expected returns are noisy; results are model outputs, not predictions or financial advice.")
    if out["data_mode"] == "SYNTHETIC":
        out["warnings"].insert(0, "SYNTHETIC TEST DATA: these numbers are NOT real market results.")
    return out
