export default function Loading({ headingRef }) {
  return <section className="loading-screen">
    <p className="eyebrow">FROM FUND TO CLIENT</p>
    <h1 ref={headingRef} tabIndex={-1}>A portfolio with purpose.</h1>
    <div className="hh-loader" role="status" aria-live="polite">
      <div><p className="hh-title">Getting your dashboard ready</p><p className="hh-sub">Interpreting client preferences and calculating three portfolios from the market dataset. This can take up to two minutes.</p></div>
      <div className="hh-track" aria-hidden="true">
        <div className="hh-base" /><div className="hh-fill" /><div className="hh-dot fund" /><div className="hh-dot client" />
        <div className="hh-walker"><svg width="64" height="38" viewBox="-2 0 68 40"><path d="M14 34 A18 18 0 0 1 46 24.5 Q53 26.5 57 30.5 Q53.5 33 50 34" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round" /><path d="M15.1 27.8 L9.4 25.8 M18.2 22.4 L13.6 18.6 M23 18.4 L20 13.2 M28.9 16.3 L27.8 10.4 M35.1 16.3 L36.2 10.4 M41 18.4 L44 13.2 M45.8 22.4 L50.4 18.6" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" fill="none" /><circle cx="50.6" cy="28.8" r="1.4" fill="currentColor" /><circle cx="57.2" cy="30.6" r="1.8" fill="currentColor" /></svg></div>
      </div>
      <div className="hh-ends" aria-hidden="true"><span>Fund</span><span>Client</span></div>
    </div>
  </section>
}
