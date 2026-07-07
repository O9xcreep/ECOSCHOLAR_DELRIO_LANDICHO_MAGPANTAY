import { useState, useEffect } from 'react'
import { apiFetch } from '../../api'
import './Ranking.css'

function Ranking() {
  const [ranked, setRanked] = useState([])
  const [loading, setLoading] = useState(true)
  const [slots, setSlots] = useState(20)

  const fetchRanking = async () => {
    setLoading(true)
    try {
      const res = await apiFetch('/api/rank-applicants')
      const data = await res.json()
      setRanked(data.ranked || [])
    } catch (err) {
      console.error('Error:', err)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchRanking()
  }, [])

  const withinSlots = ranked.slice(0, slots)
  const waitlisted = ranked.slice(slots)

  return (
    <div className="ranking-page">

      {/* Header */}
      <div className="ranking-header">
        <div>
          <h2 className="page-title">Applicant Ranking</h2>
          <p className="page-sub">
            ML-based ranking using the eligibility model (XGBoost + Random Forest Regressor)
          </p>
        </div>
        <div className="ranking-controls">
          <div className="slots-control">
            <label>Scholarship Slots:</label>
            <input
              type="number"
              value={slots}
              min={1}
              max={ranked.length}
              onChange={e => setSlots(Number(e.target.value))}
              className="slots-input"
            />
          </div>
          <button className="btn-refresh" onClick={fetchRanking}>
            Refresh
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="ranking-stats">
        <div className="rank-stat purple">
          <h3>{ranked.length}</h3>
          <p>Total Applicants</p>
        </div>
        <div className="rank-stat green">
          <h3>{withinSlots.length}</h3>
          <p>Within Slots</p>
        </div>
        <div className="rank-stat yellow">
          <h3>{waitlisted.length}</h3>
          <p>Waitlisted</p>
        </div>
        <div className="rank-stat blue">
          <h3>{slots}</h3>
          <p>Available Slots</p>
        </div>
      </div>

      {/* ML Note */}
      <div className="ml-note-box">
        <p>
          Rank is the eligibility model's <strong>Total Score</strong> (Random
          Forest Regressor), computed from GPA, household income, family size,
          siblings, parents' education and occupation, and housing situation.
          The <strong>Status</strong> column (Approved/Rejected) comes from the
          separate XGBoost classifier once an admin verifies documents -
          they can disagree on a given applicant, which is expected.
        </p>
      </div>

      {loading ? (
        <div className="ranking-loading">
          Generating ML rankings...
        </div>
      ) : (
        <>
          {/* Within Slots Table */}
          <div className="ranking-card">
            <div className="ranking-card-header">
              <h3>Within Scholarship Slots (Top {slots})</h3>
              <span className="badge badge-green">{withinSlots.length} scholars</span>
            </div>
            <table className="ranking-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Applicant</th>
                  <th>Course</th>
                  <th>GPA</th>
                  <th>Income</th>
                  <th>Family</th>
                  <th>Other Sch.</th>
                  <th>ML Score</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {withinSlots.map((app, i) => (
                  <tr key={app.id} className="within-slot-row">
                    <td>
                      <div className={`rank-badge ${i < 3 ? 'top-3' : ''}`}>
                        #{app.rank}
                      </div>
                    </td>
                    <td>
                      <p className="rank-name">{app.full_name}</p>
                    </td>
                    <td className="rank-course">{app.course}</td>
                    <td className="rank-gwa">{app.gpa}</td>
                    <td className="rank-income">
                      {app.monthly_income != null ? `₱${Number(app.monthly_income).toLocaleString()}` : 'N/A'}
                    </td>
                    <td>{app.family_size}</td>
                    <td>
                      {app.has_other_scholarship
                        ? <span className="badge badge-red">Yes</span>
                        : <span className="badge badge-green">No</span>}
                    </td>
                    <td>
                      <div className="ml-score-cell">
                        <div className="ml-score-bar-track">
                          <div
                            className="ml-score-bar-fill"
                            style={{
                              width: `${app.ml_score}%`,
                              background: app.ml_score >= 80
                                ? '#10b981' : app.ml_score >= 60
                                ? '#f59e0b' : '#ef4444'
                            }}
                          />
                        </div>
                        <span className="ml-score-num">{app.ml_score}%</span>
                      </div>
                    </td>
                    <td>
                      <span className={`badge ${
                        app.application_status === 'Approved' ? 'badge-green' :
                        app.application_status === 'Rejected' ? 'badge-red' :
                        'badge-yellow'
                      }`}>
                        {app.application_status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Waitlisted Table */}
          {waitlisted.length > 0 && (
            <div className="ranking-card">
              <div className="ranking-card-header">
                <h3>Waitlisted Applicants</h3>
                <span className="badge badge-yellow">
                  {waitlisted.length} waitlisted
                </span>
              </div>
              <table className="ranking-table">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Applicant</th>
                    <th>Course</th>
                    <th>GPA</th>
                    <th>ML Score</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {waitlisted.map(app => (
                    <tr key={app.id} className="waitlist-row">
                      <td>#{app.rank}</td>
                      <td><p className="rank-name">{app.full_name}</p></td>
                      <td className="rank-course">{app.course}</td>
                      <td className="rank-gwa">{app.gpa}</td>
                      <td>
                        <div className="ml-score-cell">
                          <div className="ml-score-bar-track">
                            <div
                              className="ml-score-bar-fill"
                              style={{
                                width: `${app.ml_score}%`,
                                background: '#aaa'
                              }}
                            />
                          </div>
                          <span className="ml-score-num">{app.ml_score}%</span>
                        </div>
                      </td>
                      <td>
                        <span className={`badge ${
                          app.application_status === 'Approved' ? 'badge-green' :
                          app.application_status === 'Rejected' ? 'badge-red' :
                          'badge-yellow'
                        }`}>
                          {app.application_status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default Ranking