import { useState, useEffect } from 'react'
import jsPDF from 'jspdf'
import autoTable from 'jspdf-autotable'
import { apiFetch, displayStatus, getUser } from '../../api'
import Reveal from '../../components/Reveal'
import StatTile from '../../components/StatTile'
import pageBg from '../../assets/bg2.jpg'
import './Ranking.css'

function Ranking() {
  const [ranked, setRanked] = useState([])
  const [loading, setLoading] = useState(true)
  const [slots, setSlots] = useState(20)
  const [savedLimit, setSavedLimit] = useState(20)
  const [approvedCount, setApprovedCount] = useState(0)
  const [savingLimit, setSavingLimit] = useState(false)
  const [limitError, setLimitError] = useState('')

  const fetchRanking = async () => {
    setLoading(true)
    try {
      const res = await apiFetch('/api/rank-applicants?cycle=current')
      const data = await res.json()
      setRanked(data.ranked || [])
    } catch (err) {
      console.error('Error:', err)
    }
    setLoading(false)
  }

  const fetchSettings = async () => {
    try {
      const res = await apiFetch('/api/settings')
      const data = await res.json()
      if (typeof data.max_accepted === 'number') {
        setSlots(data.max_accepted)
        setSavedLimit(data.max_accepted)
      }
      if (typeof data.approved_count === 'number') setApprovedCount(data.approved_count)
    } catch (err) {
      console.error('Settings error:', err)
    }
  }

  useEffect(() => {
    fetchRanking()
    fetchSettings()
  }, [])

  const handleSaveLimit = async () => {
    setLimitError('')
    setSavingLimit(true)
    try {
      const res = await apiFetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_accepted: slots })
      })
      const data = await res.json()
      if (!res.ok) {
        setLimitError(data.error || 'Failed to update the applicant limit')
        return
      }
      setSavedLimit(data.max_accepted)
      setApprovedCount(data.approved_count)
      await fetchRanking()
    } catch {
      setLimitError('Cannot connect to server. Please try again.')
    } finally {
      setSavingLimit(false)
    }
  }

  const withinSlots = ranked.slice(0, savedLimit)
  const waitlisted = ranked.slice(savedLimit)

  const handleExportRankingPdf = () => {
    const doc = new jsPDF()
    const generatedAt = new Date().toLocaleString('en-PH', { dateStyle: 'medium', timeStyle: 'short' })
    const orgName = getUser()?.organization_name || 'EcoScholar'

    doc.setFontSize(16)
    doc.text(`${orgName} - Applicant Ranking`, 14, 18)
    doc.setFontSize(10)
    doc.setTextColor(120)
    doc.text(`Generated ${generatedAt}`, 14, 25)

    const rowFor = app => [
      `#${app.rank}`,
      app.full_name,
      app.course || '',
      app.gpa ?? '',
      app.monthly_income != null ? `P${Number(app.monthly_income).toLocaleString()}` : 'N/A',
      app.family_size ?? '',
      app.has_other_scholarship ? 'Yes' : 'No',
      `${app.ml_score}%`,
      displayStatus(app.application_status, app.ml_status),
    ]
    const columns = ['Rank', 'Applicant', 'Course', 'GPA', 'Income', 'Family', 'Other Sch.', 'ML Score', 'Status']

    autoTable(doc, {
      startY: 32,
      head: [[{ content: `Within Scholarship Slots (Top ${slots}) - ${withinSlots.length} scholars`, colSpan: columns.length }]],
      body: [],
      theme: 'plain',
      headStyles: { fontStyle: 'bold', fontSize: 11 },
    })
    autoTable(doc, {
      startY: doc.lastAutoTable.finalY,
      head: [columns],
      body: withinSlots.map(rowFor),
      theme: 'grid',
      headStyles: { fillColor: [61, 111, 163] },
      styles: { fontSize: 8 },
    })

    if (waitlisted.length > 0) {
      autoTable(doc, {
        startY: doc.lastAutoTable.finalY + 10,
        head: [[{ content: `Waitlisted Applicants - ${waitlisted.length}`, colSpan: columns.length }]],
        body: [],
        theme: 'plain',
        headStyles: { fontStyle: 'bold', fontSize: 11 },
      })
      autoTable(doc, {
        startY: doc.lastAutoTable.finalY,
        head: [columns],
        body: waitlisted.map(rowFor),
        theme: 'grid',
        headStyles: { fillColor: [61, 111, 163] },
        styles: { fontSize: 8 },
      })
    }

    doc.save(`ecoscholar-ranking-${new Date().toISOString().slice(0, 10)}.pdf`)
  }

  return (
    <div className="ranking-page page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>

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
            <label>Accepted Applicant Limit:</label>
            <input
              type="number"
              value={slots}
              min={1}
              onChange={e => setSlots(Number(e.target.value))}
              className="slots-input"
            />
            <button
              className="btn-save-limit"
              onClick={handleSaveLimit}
              disabled={savingLimit || slots === savedLimit}>
              {savingLimit ? 'Saving...' : 'Save'}
            </button>
          </div>
          <button className="btn-refresh" onClick={fetchRanking}>
            Refresh
          </button>
          <button className="btn-export" onClick={handleExportRankingPdf} disabled={ranked.length === 0}>
            Export Ranking PDF
          </button>
        </div>
      </div>

      {limitError && <div className="limit-error">{limitError}</div>}
      <p className="limit-note">
        Currently <strong>{approvedCount}</strong> of <strong>{savedLimit}</strong> slots
        accepted. Approved status is always the top-{savedLimit} eligible applicants by ML
        score - raising or lowering this limit, or verifying a new stronger applicant, can
        automatically promote or bump others.
      </p>

      {/* Stats */}
      <div className="ranking-stats">
        <StatTile value={ranked.length} label="Total Applicants" color="#7c3aed" index={0} />
        <StatTile value={withinSlots.length} label="Within Slots" color="#0f9d64" index={1} />
        <StatTile value={waitlisted.length} label="Waitlisted" color="#b5790a" index={2} />
        <StatTile value={slots} label="Available Slots" color="#3d6fa3" index={3} />
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
          <Reveal className="ranking-card">
            <div className="ranking-card-header">
              <h3>Within Scholarship Slots (Top {slots})</h3>
              <span className="badge badge-green">{withinSlots.length} scholars</span>
            </div>
            <div className="table-scroll">
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
                      {app.city && <p className="rank-city">{app.city}</p>}
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
                        displayStatus(app.application_status, app.ml_status) === 'Approved' ? 'badge-green' :
                        displayStatus(app.application_status, app.ml_status) === 'Rejected' ? 'badge-red' :
                        'badge-yellow'
                      }`}>
                        {displayStatus(app.application_status, app.ml_status)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </Reveal>

          {/* Waitlisted Table */}
          {waitlisted.length > 0 && (
            <Reveal className="ranking-card">
              <div className="ranking-card-header">
                <h3>Waitlisted Applicants</h3>
                <span className="badge badge-yellow">
                  {waitlisted.length} waitlisted
                </span>
              </div>
              <div className="table-scroll">
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
                      <td>
                        <p className="rank-name">{app.full_name}</p>
                        {app.city && <p className="rank-city">{app.city}</p>}
                      </td>
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
                          displayStatus(app.application_status, app.ml_status) === 'Approved' ? 'badge-green' :
                          displayStatus(app.application_status, app.ml_status) === 'Rejected' ? 'badge-red' :
                          'badge-yellow'
                        }`}>
                          {displayStatus(app.application_status, app.ml_status)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </Reveal>
          )}
        </>
      )}
    </div>
  )
}

export default Ranking