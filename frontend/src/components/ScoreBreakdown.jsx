import './ScoreBreakdown.css'

// Renders build_score_breakdown()'s output: how many points each factor moved
// the ML score above (+) or below (-) the average applicant, as bars that grow
// right or left from a center line. `audience="admin"` also shows the baseline.
function ScoreBreakdown({ breakdown, audience = 'student' }) {
  const factors = breakdown?.factors || []
  if (factors.length === 0) return null

  // Scale bars to the largest factor, with a floor so tiny effects stay tiny.
  const maxAbs = Math.max(5, ...factors.map(f => Math.abs(f.points)))

  return (
    <div className="score-breakdown">
      <p className="score-breakdown-intro">
        {audience === 'admin'
          ? `Points each factor added to or took from the average applicant's score of ${breakdown.baseline}.`
          : 'How each part of your application raised or lowered your score compared with a typical applicant.'}
      </p>
      {factors.map(f => {
        const width = `${(Math.abs(f.points) / maxAbs) * 50}%`
        const positive = f.points >= 0
        return (
          <div key={f.label} className="sb-row">
            <div className="sb-header">
              <span className="sb-label">{f.label}</span>
              <span className={`sb-value ${positive ? 'sb-up' : 'sb-down'}`}>
                {positive ? '+' : '−'}{Math.abs(f.points).toFixed(1)} pts
              </span>
            </div>
            <div className="sb-track">
              <div className="sb-center" />
              <div
                className={`sb-fill ${positive ? 'sb-fill-up' : 'sb-fill-down'}`}
                style={positive ? { left: '50%', width } : { right: '50%', width }} />
            </div>
          </div>
        )
      })}
      <p className="sb-legend">
        <span className="sb-dot sb-fill-up" /> Helped
        <span className="sb-dot sb-fill-down" /> Held back
      </p>
    </div>
  )
}

export default ScoreBreakdown
