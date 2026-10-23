import { useEffect, useRef, useState } from 'react'

export default function MicrosoftUpdate({ dataMode, baselineAsOf, horizonWeeks }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const pending = useRef(null)
  useEffect(() => () => pending.current?.abort(), [])

  async function update() {
    if (pending.current) return
    const controller = new AbortController()
    pending.current = controller
    setLoading(true)
    setError('')
    const timeout = setTimeout(() => controller.abort(), 65000)
    try {
      const response = await fetch('/api/holdings/MSFT/update', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, cache: 'no-store',
        body: JSON.stringify({ baseline_as_of: baselineAsOf, data_mode: dataMode, horizon_weeks: horizonWeeks }), signal: controller.signal,
      })
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Microsoft update failed. Try again.')
      setResult(data)
    } catch (cause) {
      setError(cause.name === 'AbortError' ? 'The update timed out. Try again.' : cause instanceof TypeError ? 'Cannot reach the update service. Check that the backend is running.' : cause.message)
    } finally {
      clearTimeout(timeout)
      pending.current = null
      setLoading(false)
    }
  }

  return <section className="panel microsoft-update" aria-labelledby="msft-update-title">
    <div className="section-heading"><h2 id="msft-update-title">Microsoft · evidence update</h2><span className="status-chip">{loading ? 'Connecting over MCP…' : result ? 'Last update connected over MCP' : 'MCP · ready to connect'}</span></div>
    <p>Check the latest available Microsoft market inputs and official company announcements against the dataset behind this recommendation.</p>
    {result && <div>
      <p className="caption">Last successful retrieval: {new Date(result.retrieved_at).toLocaleString()}. {error && 'The last refresh failed; the evidence below is from the earlier successful retrieval.'}</p>
      {result.action_flags?.length > 0 ? result.action_flags.map(flag => <div className="event-flag" key={flag.source_url}>
        <p className="eyebrow">ACTION NEEDED · VERIFIED COMPANY EVENT</p><h3>{flag.title}</h3>
        <p>{flag.finding}</p><p>{flag.implication}</p>
        <div className="event-action"><strong>Suggested change</strong><p>{flag.action}</p></div>
        <a href={flag.source_url} target="_blank" rel="noreferrer">Microsoft announcement · {flag.published} ↗</a>
        <details><summary>What this flag establishes</summary><p>{flag.baseline_note}</p><p>{flag.allocation_note}</p></details>
      </div>) : <h3>{result.assessment}</h3>}
      {result.market && <div className="update-market"><strong>${result.market.price.toFixed(2)} USD</strong><span>Adjusted daily observation · {result.market.as_of}</span><span>120-session momentum: {result.market.momentum_pct.toFixed(2)}% · Historical annualised volatility: {result.market.volatility_pct.toFixed(2)}%</span><a href={result.market.source} target="_blank" rel="noreferrer">Yahoo Finance market data ↗</a><small>{result.market.observation}</small></div>}
      <ul className="verification-checks">{result.checks.map(check => <li key={check.title}><strong>{check.title} · {check.status === 'consistent' ? 'Consistent' : check.status === 'review' ? 'Review' : 'Unverified'}</strong><p>{check.detail}</p></li>)}</ul>
      {result.news.length > 0 && <><h3>From Microsoft</h3><ul className="company-news">{result.news.map(item => <li key={item.url}><a href={item.url} target="_blank" rel="noreferrer">{item.title} ↗</a><small>{item.published}</small></li>)}</ul></>}
      {result.warnings.map(w => <p key={w} className="warning">{w}</p>)}
      <p className="caption">{result.methodology}</p>
    </div>}
    {error && <p className="error" role="alert">{error} Your original recommendation is unchanged.</p>}
    <div className="update-action"><button onClick={update} disabled={loading}>{loading ? 'Updating…' : 'Update'}</button><span className="caption" role="status">{loading ? 'Fetching evidence. The portfolio remains available.' : 'Evidence check only · allocation unchanged'}</span></div>
  </section>
}
