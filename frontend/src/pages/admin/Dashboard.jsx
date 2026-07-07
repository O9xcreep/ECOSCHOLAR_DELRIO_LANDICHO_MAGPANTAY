import { useState, useEffect } from 'react'
import { apiFetch } from '../../api'
import './Dashboard.css'

const statusClass = {
  'Approved': 'badge-green',
  'Under Review': 'badge-yellow',
  'Rejected': 'badge-red',
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
              <th>Course</th>
              <th>GWA</th>
              <th>Status</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {recentApps.length === 0 ? (
              <tr>
                <td colSpan="5" style={{ textAlign: 'center', color: '#aaa', padding: '20px' }}>
                  No recent applications
                </td>
              </tr>
            ) : (
              recentApps.map((app, i) => (
                <tr key={i}>
                  <td>{app.full_name}</td>
                  <td>{app.course}</td>
                  <td className="gwa">{app.gpa}</td>
                  <td>
                    <span className={`badge ${statusClass[app.application_status] || 'badge-yellow'}`}>
                      {app.application_status || 'Pending'}
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

    </div>
  )
}

export default Dashboard