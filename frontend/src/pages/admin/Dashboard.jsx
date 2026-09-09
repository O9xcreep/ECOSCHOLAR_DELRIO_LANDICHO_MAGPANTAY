import { useState, useEffect, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell
} from 'recharts'
import jsPDF from 'jspdf'
import autoTable from 'jspdf-autotable'
import { apiFetch, displayStatus, getUser } from '../../api'
import pageBg from '../../assets/bg4.jpg'
import './Dashboard.css'

const statusClass = {
  'Approved': 'badge-green',
  'Under Review': 'badge-yellow',
  'Rejected': 'badge-red',
  'Waitlisted': 'badge-yellow',
  'Newly Submitted': 'badge-blue',
  'Pending Verification': 'badge-yellow',
  'Incomplete': 'badge-red',
  'Withdrawn': 'badge-gray',
}

const STATUS_COLORS = {
  'Approved': '#10b981',
  'Rejected': '#ef4444',
  'Newly Submitted': '#2563eb',
  'Pending Verification': '#f59e0b',
  'Incomplete': '#ef4444',
  'Withdrawn': '#94a3b8',
}

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function Dashboard() {
  const [stats, setStats] = useState({
    total: 0,
    approved: 0,
    under_review: 0,
    rejected: 0
  })
  const [recentApps, setRecentApps] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)

  const user = JSON.parse(localStorage.getItem('user') || '{}')

  const [duplicateFlags, setDuplicateFlags] = useState([])
  const [scholarsPerYear, setScholarsPerYear] = useState([])
  const [historyLog, setHistoryLog] = useState([])
  const [openingDoc, setOpeningDoc] = useState('')

  // ── Analytics (formerly the standalone Reports page) ──
  const [allApplicants, setAllApplicants] = useState([])
  const [cycles, setCycles] = useState([])
  const [selectedCycle, setSelectedCycle] = useState('all')
  const [submittedPeriod, setSubmittedPeriod] = useState('monthly') // 'monthly' | 'yearly'

  const handleViewFlagDoc = async (applicantId, documentName, key) => {
    if (!applicantId || !documentName) return
    setOpeningDoc(key)
    try {
      const response = await apiFetch(
        `/api/documents/${applicantId}/view?document_name=${encodeURIComponent(documentName)}`
      )
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        alert(data.error || 'Could not load this document')
        return
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank')
    } catch {
      alert('Cannot connect to server')
    }
    setOpeningDoc('')
  }

useEffect(() => {
  // Fetch stats
  apiFetch('/api/stats?cycle=current')
    .then(res => res.json())
    .then(data => setStats(data))
    .catch(err => { console.error('Stats error:', err); setLoadError(true) })

  // Fetch recent applicants
  apiFetch('/api/applicants?cycle=current')
    .then(res => res.json())
    .then(data => {
      setRecentApps((data.applicants || []).slice(0, 5))
      setLoading(false)
    })
    .catch(err => {
      console.error('Applicants error:', err)
      setLoading(false)
      setLoadError(true)
    })

  // Fetch duplicate flags
  apiFetch('/api/duplicate-flags')
    .then(res => res.json())
    .then(data => setDuplicateFlags(data.flags || []))
    .catch(err => { console.error('Flags error:', err); setLoadError(true) })

  // Fetch scholars approved per academic year
  apiFetch('/api/stats/scholars-per-year')
    .then(res => res.json())
    .then(data => setScholarsPerYear(data.scholars_per_year || []))
    .catch(err => { console.error('Scholars per year error:', err); setLoadError(true) })

  // Fetch recent decision history log
  apiFetch('/api/history-log?limit=10')
    .then(res => res.json())
    .then(data => setHistoryLog(data.history || []))
    .catch(err => { console.error('History log error:', err); setLoadError(true) })

  // Fetch every applicant across every cycle, for the analytics charts below -
  // these look at long-term trends, not just the live current-cycle queue.
  apiFetch('/api/applicants')
    .then(res => res.json())
    .then(data => setAllApplicants(data.applicants || []))
    .catch(err => { console.error('Analytics applicants error:', err); setLoadError(true) })

  apiFetch('/api/program-cycles')
    .then(res => res.json())
    .then(data => setCycles(data.cycles || []))
    .catch(() => {})
}, [])

  const statCircles = [
    { label: 'Total', value: stats.total, tone: 'total' },
    { label: 'Review', value: stats.under_review, tone: 'review' },
    { label: 'Approved', value: stats.approved, tone: 'approved' },
    { label: 'Rejected', value: stats.rejected, tone: 'rejected' },
  ]

  // Every cycle option beyond "All cycles" narrows the already-fetched full list
  // client-side, rather than re-fetching - the charts already need every
  // applicant's full record regardless of which cycle is selected.
  const filtered = useMemo(() => {
    if (selectedCycle === 'all') return allApplicants
    if (selectedCycle === 'legacy') return allApplicants.filter(a => !a.cycle_id)
    return allApplicants.filter(a => a.cycle_id === selectedCycle)
  }, [allApplicants, selectedCycle])

  const analyticsTotal = filtered.length

  const statusBreakdown = useMemo(() => {
    const counts = {}
    for (const a of filtered) {
      const status = a.application_status || 'Newly Submitted'
      counts[status] = (counts[status] || 0) + 1
    }
    return Object.entries(counts)
      .map(([name, value]) => ({ name, value, color: STATUS_COLORS[name] || '#94a3b8' }))
      .sort((a, b) => b.value - a.value)
  }, [filtered])

  const acceptedVsRejected = useMemo(() => ([
    { name: 'Approved', count: filtered.filter(a => a.application_status === 'Approved').length, color: '#10b981' },
    { name: 'Rejected', count: filtered.filter(a => a.application_status === 'Rejected').length, color: '#ef4444' },
  ]), [filtered])

  const monthlyData = useMemo(() => {
    const counts = {}
    for (const a of filtered) {
      if (!a.submitted_at) continue
      const d = new Date(a.submitted_at)
      if (isNaN(d)) continue
      const key = `${d.getFullYear()}-${d.getMonth()}`
      counts[key] = (counts[key] || 0) + 1
    }
    return Object.entries(counts)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, count]) => {
        const [year, month] = key.split('-')
        return { label: `${MONTH_NAMES[Number(month)]} '${String(year).slice(2)}`, count }
      })
  }, [filtered])

  const yearlyData = useMemo(() => {
    const counts = {}
    for (const a of filtered) {
      if (!a.submitted_at) continue
      const d = new Date(a.submitted_at)
      if (isNaN(d)) continue
      const year = d.getFullYear()
      counts[year] = (counts[year] || 0) + 1
    }
    return Object.entries(counts)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([year, count]) => ({ label: year, count }))
  }, [filtered])

  const submittedData = submittedPeriod === 'yearly' ? yearlyData : monthlyData

  const handleExportPdf = () => {
    const doc = new jsPDF()
    const generatedAt = new Date().toLocaleString('en-PH', { dateStyle: 'medium', timeStyle: 'short' })

    const orgName = getUser()?.organization_name || 'EcoScholar'
    doc.setFontSize(16)
    doc.text(`${orgName} - Applications Report`, 14, 18)
    doc.setFontSize(10)
    doc.setTextColor(120)
    doc.text(`Generated ${generatedAt}`, 14, 25)

    autoTable(doc, {
      startY: 32,
      head: [['Metric', 'Value']],
      body: [
        ['Total Applicants', String(analyticsTotal)],
        ['Approved', String(acceptedVsRejected[0].count)],
        ['Rejected', String(acceptedVsRejected[1].count)],
      ],
      theme: 'grid',
      headStyles: { fillColor: [61, 111, 163] },
    })

    autoTable(doc, {
      startY: doc.lastAutoTable.finalY + 10,
      head: [['Status', 'Count', 'Share']],
      body: statusBreakdown.map(item => [
        item.name, String(item.value), analyticsTotal ? `${Math.round((item.value / analyticsTotal) * 100)}%` : '0%'
      ]),
      theme: 'grid',
      headStyles: { fillColor: [61, 111, 163] },
    })

    doc.save(`ecoscholar-report-${new Date().toISOString().slice(0, 10)}.pdf`)
  }

  return (
    <div className="dashboard page-enter">
      <div className="page-hero" style={{ '--page-bg-image': `url(${pageBg})` }} />

      {/* Header */}
      <div className="dash-header">
        <h2 className="dash-title">Welcome back, {user.full_name || 'Admin'}!</h2>
        <p className="dash-sub">System ledger report as of today.</p>
      </div>

      {loadError && (
        <div className="dash-error-banner">
          Some dashboard data couldn't be loaded. Try refreshing the page.
        </div>
      )}

      {/* Stats */}
      {loading ? (
        <div className="loading">Loading stats...</div>
      ) : (
        <div className="stat-circles">
          {statCircles.map((stat, i) => (
            <div key={i} className="stat-circle-item">
              <div className={`stat-circle tone-${stat.tone}`}>
                <span className="stat-circle-value">{stat.value}</span>
              </div>
              <p className="stat-circle-label">{stat.label}</p>
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
              <Bar dataKey="count" name="Scholars" fill="var(--accent)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="chart-sub">No approved scholars yet.</p>
        )}
      </div>

      {/* ── ANALYTICS (formerly the standalone Reports page) ── */}
      <div className="analytics-header">
        <h3>Analytics</h3>
        <div className="analytics-controls">
          {cycles.length > 0 && (
            <select
              className="cycle-select"
              value={selectedCycle}
              onChange={e => setSelectedCycle(e.target.value)}>
              <option value="all">All cycles</option>
              {cycles.map(c => (
                <option key={c.id || 'legacy'} value={c.id || 'legacy'}>
                  {c.label}{c.is_current ? ' (current)' : ''} — {c.applicant_count}
                </option>
              ))}
            </select>
          )}
          <button className="btn-export" onClick={handleExportPdf}>Export PDF</button>
        </div>
      </div>

      <div className="charts-row">
        {/* Status Distribution (donut) */}
        <div className="dash-card">
          <div className="card-header"><h3>Status distribution</h3></div>
          <p className="chart-sub-label">Share of all applications</p>
          {statusBreakdown.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={statusBreakdown}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={80}
                    paddingAngle={3}
                    dataKey="value">
                    {statusBreakdown.map((item, i) => (
                      <Cell key={i} fill={item.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <div className="donut-legend">
                {statusBreakdown.map((item, i) => (
                  <div key={i} className="legend-item">
                    <span className="legend-dot" style={{ background: item.color }} />
                    <span>{item.name} ({analyticsTotal ? Math.round((item.value / analyticsTotal) * 100) : 0}%)</span>
                  </div>
                ))}
              </div>
            </>
          ) : <p className="chart-sub">No applications yet.</p>}
        </div>

        {/* Accepted vs Rejected */}
        <div className="dash-card">
          <div className="card-header"><h3>Accepted vs Rejected</h3></div>
          <p className="chart-sub-label">Final decisions only - excludes applications still in review</p>
          {analyticsTotal > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={acceptedVsRejected}>
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {acceptedVsRejected.map((item, i) => (
                    <Cell key={i} fill={item.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="chart-sub">No applications yet.</p>}
        </div>
      </div>

      {/* Applications Submitted Over Time */}
      <div className="dash-card">
        <div className="card-header">
          <h3>Applications submitted</h3>
          <div className="period-toggle">
            <button
              className={submittedPeriod === 'monthly' ? 'active' : ''}
              onClick={() => setSubmittedPeriod('monthly')}>Monthly</button>
            <button
              className={submittedPeriod === 'yearly' ? 'active' : ''}
              onClick={() => setSubmittedPeriod('yearly')}>Yearly</button>
          </div>
        </div>
        {submittedData.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={submittedData}>
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#6ee7b7" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : <p className="chart-sub">No applications yet.</p>}
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
            {duplicateFlags.map((flag, i) => {
              const isDocFlag = flag.reason === 'duplicate_document' || flag.reason === 'near_duplicate_document'
              return (
              <div key={i} className="duplicate-row">
                <div className="duplicate-info">
                  <div>
                    <p className="duplicate-name">{flag.applicant_name}</p>
                    <p className="duplicate-detail">
                      {flag.reason === 'email'
                        ? `Duplicate email: ${flag.applicant_email}`
                        : flag.reason === 'duplicate_document'
                        ? `"${flag.document_name}" is the exact same file already uploaded by ${flag.duplicate_of_name || 'another applicant'}`
                        : flag.reason === 'near_duplicate_document'
                        ? `"${flag.document_name}" looks like a near-identical copy of "${flag.duplicate_of_document_name || flag.document_name}" uploaded by ${flag.duplicate_of_name || 'another applicant'} (similarity distance: ${flag.similarity_distance} - lower means more alike)`
                        : `Same name + birthdate as existing applicant`}
                    </p>
                    <p className="duplicate-date">
                      Flagged: {new Date(flag.flagged_at)
                        .toLocaleDateString('en-PH', {
                          month: 'short', day: 'numeric', year: 'numeric'
                        })}
                    </p>
                    {isDocFlag && (
                      <div className="duplicate-view-actions">
                        <button
                          className="btn-view-flag-doc"
                          disabled={openingDoc === `a-${flag.id}`}
                          onClick={() => handleViewFlagDoc(flag.applicant_id, flag.document_name, `a-${flag.id}`)}>
                          {openingDoc === `a-${flag.id}` ? 'Opening...' : `View ${flag.applicant_name}'s document`}
                        </button>
                        <button
                          className="btn-view-flag-doc"
                          disabled={openingDoc === `b-${flag.id}`}
                          onClick={() => handleViewFlagDoc(flag.duplicate_of_id, flag.duplicate_of_document_name || flag.document_name, `b-${flag.id}`)}>
                          {openingDoc === `b-${flag.id}` ? 'Opening...' : `View ${flag.duplicate_of_name || 'other applicant'}'s document`}
                        </button>
                      </div>
                    )}
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
              )
            })}
          </div>
        </div>
      )}
      {/* Recent Applications */}
      <div className="dash-card">
        <div className="card-header">
          <h3>Recent Applications</h3>
          <a href="/admin/applications" className="view-all">View All</a>
        </div>

        {/* Desktop: table */}
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
                <td colSpan="6" style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '20px' }}>
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

        {/* Mobile: card list */}
        <div className="recent-cards">
          {recentApps.length === 0 ? (
            <p className="chart-sub">No recent applications</p>
          ) : (
            recentApps.map((app, i) => (
              <div key={i} className="recent-card">
                <div>
                  <p className="recent-card-name">{app.full_name}</p>
                  <p className="recent-card-detail">{app.course}</p>
                  <p className="recent-card-detail">{app.gpa} GWA</p>
                </div>
                <span className={`badge ${statusClass[displayStatus(app.application_status, app.ml_status)] || 'badge-yellow'}`}>
                  {displayStatus(app.application_status, app.ml_status) || 'Pending'}
                </span>
              </div>
            ))
          )}
        </div>
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
