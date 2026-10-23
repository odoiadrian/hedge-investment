export const EMPTY_PROFILE = {
  reference: '', age: '', horizon_weeks: '', risk_appetite: '', max_loss_pct: '',
  max_single_holding_pct: '', objective: 'balanced_growth', min_cash_pct: '0',
  min_sellable_2day_pct: '90', target_return_pct: '', objectives: '', values: '', exclusions: '', notes: '',
}

export default function ClientForm({ profile, setProfile, onSubmit, loading, error, headingRef }) {
  const update = event => setProfile(previous => ({ ...previous, [event.target.name]: event.target.value }))
  const example = () => setProfile({ ...EMPTY_PROFILE, reference: 'Example client', horizon_weeks: '4', risk_appetite: '3', max_loss_pct: '8', max_single_holding_pct: '20', min_cash_pct: '5', exclusions: 'No oil or natural gas investments.' })
  return (
    <section className="intake">
      <p className="eyebrow">01 / CLIENT DETAILS</p>
      <h1 ref={headingRef} tabIndex={-1}>Start with the client.</h1>
      <p className="intro">Their priorities. Financial evidence. One considered allocation.</p>
      <div className="budget-line"><span>Amount to invest</span><strong>$100,000 <small>USD</small></strong></div>
      <form onSubmit={onSubmit} onInvalid={event => { const details = event.target.closest('details'); if (details) details.open = true }}>
        <fieldset disabled={loading}>
          <div className="form-row two first-row">
            <div><label htmlFor="reference">Client reference</label><input id="reference" name="reference" value={profile.reference} onChange={update} required pattern=".*\S.*" maxLength={100} placeholder="Client 001" autoComplete="off" /></div>
            <div><label htmlFor="objective">Investment objective</label><select id="objective" name="objective" value={profile.objective} onChange={update}><option value="balanced_growth">Balanced growth</option><option value="preserve_capital">Preserve capital</option><option value="max_growth">Maximum growth</option><option value="income">Income (minimum-risk proxy)</option></select></div>
          </div>
          <div className="form-row two">
            <div><label htmlFor="horizon">Horizon <span>1–26 weeks</span></label><input id="horizon" name="horizon_weeks" type="number" min="1" max="26" step="1" required value={profile.horizon_weeks} onChange={update} placeholder="e.g. 4" /></div>
            <div><label htmlFor="risk">Risk appetite</label><select id="risk" name="risk_appetite" value={profile.risk_appetite} onChange={update} required><option value="">Select…</option><option value="1">1 · Very cautious</option><option value="2">2 · Cautious</option><option value="3">3 · Moderate</option><option value="4">4 · Adventurous</option><option value="5">5 · Aggressive</option></select></div>
            <div><label htmlFor="loss">Maximum bad-case loss <span>%</span></label><input id="loss" name="max_loss_pct" type="number" min="0.5" max="60" step="0.1" required value={profile.max_loss_pct} onChange={update} placeholder="e.g. 8" /><small className="field-help">Modelled one-in-twenty loss over the horizon.</small></div>
            <div><label htmlFor="cap">Maximum per holding <span>%</span></label><input id="cap" name="max_single_holding_pct" type="number" min="1" max="100" step="0.1" required value={profile.max_single_holding_pct} onChange={update} placeholder="e.g. 20" /><small className="field-help">Applies to investments; cash is exempt.</small></div>
          </div>
          <label htmlFor="values">Client priorities <span>optional</span></label><textarea id="values" name="values" rows={2} maxLength={3000} value={profile.values} onChange={update} placeholder="Goals, ethical standards or political preferences the client wants reflected. Be specific about investable constraints." />
          <label htmlFor="exclusions">Investments to avoid <span>optional</span></label><input id="exclusions" name="exclusions" value={profile.exclusions} maxLength={2000} onChange={update} placeholder="e.g. No oil or gas, or exclude Microsoft" />
          <details className="additional"><summary>Additional client details & limits</summary>
            <div className="form-row two"><div><label htmlFor="age">Age <span>optional</span></label><input id="age" name="age" type="number" min="0" max="120" step="1" value={profile.age} onChange={update} /></div><div><label htmlFor="cash">Minimum cash <span>%</span></label><input id="cash" name="min_cash_pct" type="number" min="0" max="100" step="0.1" required value={profile.min_cash_pct} onChange={update} /></div><div><label htmlFor="liquidity">Sellable within two days <span>%</span></label><input id="liquidity" name="min_sellable_2day_pct" type="number" min="0" max="100" step="0.1" required value={profile.min_sellable_2day_pct} onChange={update} /></div><div><label htmlFor="target">Target horizon return <span>%, optional</span></label><input id="target" name="target_return_pct" type="number" min="-50" max="100" step="0.1" value={profile.target_return_pct} onChange={update} /></div></div>
            <label htmlFor="notes">Other goals or limits</label><textarea id="notes" name="notes" rows={2} maxLength={3000} value={profile.notes} onChange={update} placeholder="e.g. At least 10% in bonds. Do not include identifying client details." />
          </details>
        </fieldset>
        <p className="form-note">This model covers a small US investment universe. Broad ethical preferences may need clarification; company ESG and political activity data are not included.</p>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="form-action"><button type="submit" disabled={loading}>{loading ? 'Building portfolio…' : 'Build portfolio'} <span aria-hidden="true">→</span></button><button type="button" className="link-button" onClick={example} disabled={loading}>Use example</button></div>
        {loading && <p className="form-note working" role="status">Interpreting preferences and calculating three portfolios. This can take up to two minutes.</p>}
      </form>
    </section>
  )
}
