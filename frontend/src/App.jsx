import { useEffect, useRef, useState } from 'react'
import { createDashboard } from './api.js'
import ClientForm, { EMPTY_PROFILE } from './components/ClientForm.jsx'
import Portfolio from './components/Portfolio.jsx'
import Loading from './components/Loading.jsx'
import logo from './assets/hedgehog-logo.svg'

export default function App() {
  const [profile, setProfile] = useState({ ...EMPTY_PROFILE })
  const [dashboard, setDashboard] = useState(null)
  const [editing, setEditing] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [view, setView] = useState('overview')
  const request = useRef(null)
  const heading = useRef(null)

  useEffect(() => () => request.current?.abort(), [])
  useEffect(() => {
    heading.current?.focus({ preventScroll: true })
    window.scrollTo(0, 0)
  }, [editing, view, loading])

  async function submit(event) {
    event.preventDefault()
    if (request.current) return
    const controller = new AbortController()
    request.current = controller
    const timeout = setTimeout(() => controller.abort(), 180000)
    setLoading(true)
    setError('')
    setDashboard(null)
    try {
      const result = await createDashboard({
        ...profile,
        reference: profile.reference.trim(),
        age: profile.age === '' ? null : Number(profile.age),
        horizon_weeks: Number(profile.horizon_weeks),
        risk_appetite: Number(profile.risk_appetite),
        max_loss_pct: Number(profile.max_loss_pct),
        max_single_holding_pct: Number(profile.max_single_holding_pct),
        min_cash_pct: Number(profile.min_cash_pct),
        min_sellable_2day_pct: Number(profile.min_sellable_2day_pct),
        target_return_pct: profile.target_return_pct === '' ? null : Number(profile.target_return_pct),
      }, controller.signal)
      setDashboard(result)
      setView('overview')
      setEditing(false)
    } catch (cause) {
      setError(cause.name === 'AbortError'
        ? 'The request timed out. Your details are still here; try again.'
        : cause instanceof TypeError
          ? 'Cannot reach the service. Start the backend and try again.'
          : cause.message)
    } finally {
      clearTimeout(timeout)
      request.current = null
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="header"><div className="header-inner"><span className="brand"><img src={logo} width="48" height="29" alt="" />hedgehog</span>
        <nav aria-label="Workspace">
          {dashboard?.status === 'ready' && !loading && <><button className="nav-button" aria-current={!editing && view === 'overview' ? 'page' : undefined} onClick={() => { setEditing(false); setView('overview') }}>Overview</button><button className="nav-button" aria-current={!editing && view === 'holdings' ? 'page' : undefined} onClick={() => { setEditing(false); setView('holdings') }}>Portfolio</button></>}
          <button className="nav-button" disabled={loading} aria-current={editing && !loading ? 'page' : undefined} onClick={() => setEditing(true)}>Client profile</button>
        </nav><span className="workspace-label">Investment workspace</span></div></header>
      <main id="main">
        {loading ? <Loading headingRef={heading} /> : editing
          ? <ClientForm profile={profile} setProfile={setProfile} onSubmit={submit} loading={loading} error={error} headingRef={heading} />
          : <Portfolio dashboard={dashboard} view={view} setView={setView} onEdit={() => { setError(''); setEditing(true) }} headingRef={heading} />}
      </main>
      <footer>Educational prototype · Model estimates, not guaranteed returns. Preferences are processed by the event AI service; client records are not saved.</footer>
    </div>
  )
}
