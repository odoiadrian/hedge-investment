import { useState } from 'react'
const money = cents => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(cents / 100)
const share = (amount, total) => new Intl.NumberFormat('en-US', { style: 'percent', maximumFractionDigits: 2 }).format(amount / total)
const percent = value => value == null ? 'Unavailable' : `${value.toFixed(2)}%`
const names = { A: 'Shield', B: 'Balanced', C: 'Growth' }
const displayValue = value => typeof value === 'object' && value !== null ? Object.entries(value).map(([key, item]) => `${key}: ${item}`).join('; ') : String(value)

export default function Portfolio({ dashboard, onEdit, headingRef }) {
  const [selected, setSelected] = useState(dashboard.recommended_option)
  const ready = dashboard.status === 'ready'
  const option = dashboard.options.find(o => o.id === selected)
  const budget = dashboard.budget_cents
  const m = option?.metrics
  return (
    <section className="portfolio">
      <div className="portfolio-heading"><div><p className="eyebrow">02 / PORTFOLIO</p><h1 ref={headingRef} tabIndex={-1}>{dashboard.client_reference}</h1></div><button className="text-button" onClick={onEdit}>Edit client</button></div>
      <p className="intro">Where to invest, and why it fits.</p>
      {!ready ? <div className="pending" role="status"><h2>{dashboard.message}</h2><ul>{dashboard.questions.map((q, i) => <li key={i}>{q}</li>)}</ul><p>No money has been allocated. Edit the client details to continue.</p></div> : <>
        <div className={dashboard.data_mode === 'SYNTHETIC' ? 'data-note warning' : 'data-note'}>{dashboard.data_mode === 'SYNTHETIC' ? 'Synthetic test data — not real market results.' : 'Public market data'} <span>· As of {dashboard.data_as_of} · {dashboard.horizon_trading_days} trading-day horizon</span></div>
        <div className="option-picker" role="group" aria-label="Portfolio option">{dashboard.options.map(o => <button key={o.id} type="button" aria-pressed={o.id === selected} onClick={() => setSelected(o.id)}>{names[o.id]}{o.id === dashboard.recommended_option && <small>Suggested</small>}</button>)}</div>
        <section className="allocation-section" aria-labelledby="allocation-title">
          <div className="allocation-heading"><div><h2 id="allocation-title">{names[selected]} allocation</h2><p className="total">$100,000 <small>USD</small></p></div><span className="muted">{option.allocations.length} investments</span></div>
          <div className="allocation-bar" aria-hidden="true">{option.allocations.map((item, index) => <span key={item.asset_id} className={`tone-${index % 5}`} style={{ width: `${item.amount_cents / budget * 100}%` }} />)}</div>
          <div className="result-metrics"><div><span>Expected horizon return</span><strong>{percent(m.expected_return_pct)}</strong></div><div><span>Annualised volatility</span><strong>{percent(m.vol_annualised_pct)}</strong></div><div><span>Modelled 1-in-20 outcome</span><strong>{percent(m.loss_1_in_20_pct)}</strong></div><div><span>Worst historical horizon</span><strong>{percent(m.worst_historical_horizon_return_pct)}</strong></div></div>
          {m.stress_breaches_loss_limit && <p className="warning">The worst historical period exceeded this client’s loss limit, despite passing the model’s normal-tail constraint.</p>}
          {dashboard.target_return && !dashboard.target_return.achievable && <p className="warning">The {percent(dashboard.target_return.target_pct)} target is above the growth portfolio’s {percent(dashboard.target_return.max_expected_return_achievable_pct)} model estimate.</p>}
          <div className="allocations"><div className="allocation-columns" aria-hidden="true"><span>Investment · select for reasoning</span><span>Amount</span><span>Share</span></div>
            {option.allocations.map((item, index) => <details className="allocation" key={`${selected}-${item.asset_id}`}><summary><span className="instrument"><i className={`tone-${index % 5}`} aria-hidden="true" /><span>{item.instrument}<small>{item.asset_class.replaceAll('_', ' ')}</small></span></span><span>{money(item.amount_cents)}</span><span>{share(item.amount_cents, budget)}</span></summary><div className="reasons"><div><h3>Financial basis</h3><p>{item.financial_reason}</p></div><div><h3>Client fit</h3><p>{item.client_reason}</p></div></div><p className="evidence">Evidence: {item.evidence.join(' · ')}</p></details>)}
          </div>
          <div className="portfolio-total"><span>Total allocated</span><strong>{money(budget)}</strong><span>100%</span></div>
        </section>
        <section className="analysis"><div><h2>Client fit</h2><p>{dashboard.client_assessment}</p></div><div><h2>{dashboard.ai_status === 'generated' ? 'AI analyst summary' : 'Financial model'}</h2><p>{dashboard.ai_summary || dashboard.financial_assessment}</p></div></section>
        <details className="report-details"><summary>Constraints, sources & assumptions</summary><h3>Rules closest to their limits</h3><ul>{option.tightest_rules.map(rule => <li key={rule}>{rule}</li>)}</ul>{option.note && <p>{option.note}</p>}<p>{option.resampled ? 'This option averages resampled return scenarios.' : 'This option uses the base solution.'} Expected returns are uncertain model estimates.</p><h3>Data sources</h3>{Object.entries(dashboard.data_sources).map(([name, source]) => <p key={name}><strong>{name.replaceAll('_', ' ')}:</strong> {displayValue(source.source)} · {source.status}{source.last && ` · ${source.last}`}</p>)}<h3>Applied client limits</h3><p>Risk appetite {dashboard.applied_profile.risk_appetite}/5 · Horizon {dashboard.applied_profile.horizon_weeks} weeks · Modelled loss limit {dashboard.applied_profile.max_loss_pct}% · Maximum holding {dashboard.applied_profile.max_single_holding_pct}% (cash exempt) · Minimum cash {dashboard.applied_profile.min_cash_pct}% · Sellable within two days {dashboard.applied_profile.min_sellable_2day_pct}%.</p><p>Excluded assets: {dashboard.applied_profile.exclusions.join(', ') || 'None'}.</p>{['class_limits', 'asset_limits'].flatMap(group => Object.entries(dashboard.applied_profile[group]).map(([name, bounds]) => <p key={`${group}-${name}`}>{name.replaceAll('_', ' ')}: minimum {bounds.min_pct}%, maximum {bounds.max_pct}%.</p>))}<h3>Data and model limitations</h3><ul>{dashboard.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul><h3>Modelling assumptions</h3>{Object.entries(dashboard.assumptions).map(([name, a]) => <p key={name}><strong>{name.replaceAll('_', ' ')}: {displayValue(a.value)}.</strong> {a.why}</p>)}<p>AI explanation: {dashboard.ai_status}. Model: {dashboard.model_name}. Reported API tokens: {dashboard.tokens_used}.</p></details>
      </>}
    </section>
  )
}
