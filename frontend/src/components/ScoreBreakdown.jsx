import './ScoreBreakdown.css'

// Student-facing names for the factor labels build_score_breakdown() returns.
const STUDENT_LABELS = {
  'GWA Score': 'Academic standing (GWA)',
  'Income Need Score': 'Household income need',
  'Family Size Score': 'Family size',
  'Parental Education Need': "Parents' education",
  'Housing Need Score': 'Housing situation',
}

function ScoreBreakdown({ breakdown }) {
  if (!breakdown || breakdown.length === 0) return null

  return (
    <div className="score-breakdown">
      <p className="score-breakdown-intro">
        How each part of your application was weighed. Higher means it counted
        more in your favor.
      </p>
      {breakdown.map(item => (
        <div key={item.label} className="sb-row">
          <div className="sb-header">
            <span className="sb-label">{STUDENT_LABELS[item.label] || item.label}</span>
            <span className="sb-value">{item.value}%</span>
          </div>
          <div className="sb-track">
            <div className="sb-fill" style={{ width: `${item.value}%`, background: item.color }} />
          </div>
        </div>
      ))}
    </div>
  )
}

export default ScoreBreakdown
