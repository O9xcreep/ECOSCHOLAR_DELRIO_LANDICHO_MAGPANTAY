import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { apiFetch, displayStatus } from '../../api'
import './Dashboard.css'

const statusClass = {
  'Approved': 'badge-green',
  'Under Review': 'badge-yellow',
  'Rejected': 'badge-red',
  'Waitlisted': 'badge-yellow',
  'Newly Submitted': 'badge-blue',
  'Pending Verification': 'badge-yellow',
  'Not Yet Reviewed': 'badge-purple',
  'Incomplete': 'badge-red',
}

function Dashboard() {
  const [stats, setStats] = useState({
    total: 0,
    approved: 0,
    under_review: 0,
    rejected: 0
  })
  const [recentApps, setRecentApps] = useState([])
  const [loading, setLoading] = useState(true)

  const user = JSON.parse(localStorage.getItem('user') || '{}')

  const [duplicateFlags, setDuplicateFlags] = useState([])
  const [scholarsPerYear, setScholarsPerYear] = useState([])
  const [historyLog, setHistoryLog] = useState([])

useEffect(() => {
  // Fetch stats
  apiFetch('/api/stats')
    .then(res => res.json())
    .then(data => setStats(data))
    .catch(err => console.error('Stats error:', err))

  // Fetch recent applicants
  apiFetch('/api/applicants')
    .then(res => res.json())
    .then(data => {
      setRecentApps((data.applicants || []).slice(0, 5))
      setLoading(false)
    })
    .catch(err => {
      console.error('Applicants error:', err)
      setLoading(false)
    })

  // Fetch duplicate flags
  apiFetch('/api/duplicate-flags')
    .then(res => res.json())
    .then(data => setDuplicateFlags(data.flags || []))
    .catch(err => console.error('Flags error:', err))

  // Fetch scholars approved per academic year
  apiFetch('/api/stats/scholars-per-year')
    .then(res => res.json())
    .then(data => setScholarsPerYear(data.scholars_per_year || []))
    .catch(err => console.error('Scholars per year error:', err))

  // Fetch recent decision history log
  apiFetch('/api/history-log?limit=10')
    .then(res => res.json())
    .then(data => setHistoryLog(data.history || []))
    .catch(err => console.error('History log error:', err))
}, [])

  const statCards = [
    { label: 'Total Applicants', value: stats.total, color: 'purple' },
    { label: 'Under Review', value: stats.under_review, color: 'yellow' },
    { label: 'Approved', value: stats.approved, color: 'green' },
    { label: 'Rejected', value: stats.rejected, color: 'red' },
  ]

  return (
    <div className="dashboard">

      {/* Header */}
      <div className="dash-header">
        <div>
          <h2 className="dash-title">Home</h2>
          <p className="dash-sub">
            Welcome back, <strong>{user.full_name || 'Admin'}!</strong>
          </p>
        </div>
      </div>

      {/* Stats */}
      {loading ? (
        <div className="loading">Loading stats...</div>
      ) : (
        <div className="stats-grid">
          {statCards.map((stat, i) => (
            <div key={i} className={`stat-card stat-${stat.color}`}>
              <div>
                <h3 className="stat-value">{stat.value}</h3>
                <p className="stat-label">{stat.label}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Scholars Approved Per Year */}
      <div className="dash-card">
        <div className="card-header">
          <h3>Scholars Approved Per Academic Year</h3>
        </div>
        {scholarsPerYear.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={scholarsPerYear}>
              <XAxis dataKey="year" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" name="Scholars" fill="#7c3aed" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="chart-sub">No approved scholars yet.</p>
        )}
      </div>

      {/* Duplicate Alerts */}
      {duplicateFlags.length > 0 && (
        <div className="dash-card duplicate-alert-card">
          <div className="card-header">
            <h3>Duplicate Application Alerts</h3>
            <span className="badge badge-red">
              {duplicateFlags.length} flagged
            </span>
          </div>
          <div className="duplicate-list">
            {duplicateFlags.map((flag, i) => (
              <div key={i} className="duplicate-row">
                <div className="duplicate-info">
                  <div>
                    <p className="duplicate-name">{flag.applicant_name}</p>
                    <p className="duplicate-detail">
                      {flag.reason === 'email'
                        ? `Duplicate email: ${flag.applicant_email}`
                        : flag.reason === 'duplicate_document'
                        ? `"${flag.document_name}" is the exact same file already uploaded by ${flag.duplicate_of_name || 'another applicant'}`
                        : `Same name + birthdate as existing applicant`}
                    </p>
                    <p className="duplicate-date">
                      Flagged: {new Date(flag.flagged_at)
                        .toLocaleDateString('en-PH', {
                          month: 'short', day: 'numeric', year: 'numeric'
                        })}
                    </p>
                  </div>
                </div>
                <button
                  className="btn-resolve"
                  onClick={async () => {
                    await apiFetch(
                      `/api/duplicate-flags/${flag.id}/resolve`,
                      { method: 'PUT' }
                    )
                    setDuplicateFlags(prev => prev.filter(f => f.id !== flag.id))
                  }}>
                  Resolve
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
      {/* Recent Applications */}
      <div className="dash-card">
        <div className="card-header">
          <h3>Recent Applications</h3>
          <a href="/admin/applications" className="view-all">View All</a>
        </div>
        <table className="dash-table">
          <thead>
            <tr>
              <th>Applicant</th>
              <th>City</th>
              <th>Course</th>
              <th>GWA</th>
              <th>Status</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {recentApps.length === 0 ? (
              <tr>
                <td colSpan="6" style={{ textAlign: 'center', color: '#aaa', padding: '20px' }}>
                  No recent applications
                </td>
              </tr>
            ) : (
              recentApps.map((app, i) => (
                <tr key={i}>
                  <td>{app.full_name}</td>
                  <td className="date">{app.city || 'N/A'}</td>
                  <td>{app.course}</td>
                  <td className="gwa">{app.gpa}</td>
                  <td>
                    <span className={`badge ${statusClass[displayStatus(app.application_status, app.ml_status)] || 'badge-yellow'}`}>
                      {displayStatus(app.application_status, app.ml_status) || 'Pending'}
                    </span>
                  </td>
                  <td className="date">
                    {app.submitted_at
                      ? new Date(app.submitted_at).toLocaleDateString('en-PH', {
                          month: 'short', day: '2-digit', year: 'numeric'
                        })
                      : 'N/A'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* History Log - recent Approved/Rejected decisions with interpreted reasons */}
      <div className="dash-card">
        <div className="card-header">
          <h3>History Log</h3>
        </div>
        {historyLog.length === 0 ? (
          <p className="chart-sub">No decisions have been made yet.</p>
        ) : (
          <div className="history-list">
            {historyLog.map((entry, i) => (
              <div key={i} className="history-row">
                <div className="history-info">
                  <p className="history-name">
                    {entry.full_name}
                    {entry.city && <span className="history-city"> · {entry.city}</span>}
                  </p>
                  {entry.new_status === 'Rejected' && entry.remarks && (
                    <p className="history-reason">{entry.remarks}</p>
                  )}
                  <p className="history-date">
                    Decided by {entry.performed_by || 'System'} on{' '}
                    {entry.performed_at
                      ? new Date(entry.performed_at).toLocaleDateString('en-PH', {
                          month: 'short', day: 'numeric', year: 'numeric'
                        })
                      : 'N/A'}
                  </p>
                </div>
                <span className={`badge ${statusClass[entry.display_status] || 'badge-yellow'}`}>
                  {entry.display_status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  )
}

export default Dashboard