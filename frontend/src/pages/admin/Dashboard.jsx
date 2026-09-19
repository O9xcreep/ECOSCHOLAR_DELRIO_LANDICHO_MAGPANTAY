import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell
} from 'recharts'
import jsPDF from 'jspdf'
import autoTable from 'jspdf-autotable'
import { apiFetch, displayStatus, getUser, connectionErrorMessage } from '../../api'
import Reveal from '../../components/Reveal'
import StatTile from '../../components/StatTile'
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
  const navigate = useNavigate()
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
  const [historyLog, setHistoryLog] = useState([])
  const [openingDoc, setOpeningDoc] = useState('')

  // ── Analytics (formerly the standalone Reports page) ──
  const [allApplicants, setAllApplicants] = useState([])
  const [cycles, setCycles] = useState([])
  const [selectedCycle, setSelectedCycle] = useState('all')
  const [submittedPeriod, setSubmittedPeriod] = useState('monthly') // 'monthly' | 'yearly'
  const [decidedPeriod, setDecidedPeriod] = useState('monthly') // 'monthly' | 'yearly'
  const [bannerDismissed, setBannerDismissed] = useState(false)
  const [cyclesLoaded, setCyclesLoaded] = useState(false)

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
      alert(connectionErrorMessage())
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
    .then(data => { setCycles(data.cycles || []); setCyclesLoaded(true) })
    .catch(() => {})
}, [])

  const statCircles = [
    { label: 'Total', value: stats.total, color: '#3d6fa3' },
    { label: 'Review', value: stats.under_review, color: '#b5790a' },
    { label: 'Approved', value: stats.approved, color: '#0f9d64' },
    { label: 'Rejected', value: stats.rejected, color: '#c23b3b' },
  ]

  // The live cycle (closed_at unset) with a deadline that's already passed but
  // hasn't been manually reset yet - is_open comes straight from the backend
  // (is_cycle_open()) via GET /api/program-cycles's serialize_cycle().
  const liveCycle = cycles.find(c => c.is_current)
  const programEnded = !!(liveCycle && liveCycle.deadline && !liveCycle.is_open)
  const bannerStorageKey = liveCycle ? `program-ended-banner-dismissed-${liveCycle.id}` : null

  // No program has ever been set up for this org yet - program_cycles docs are
  // only ever created by the Settings "Set Up Scholarship Program" action, so an
  // empty list (once loaded) reliably means this org hasn't done that yet.
  const noProgramYet = cyclesLoaded && cycles.length === 0

  useEffect(() => {
    if (bannerStorageKey) {
      setBannerDismissed(sessionStorage.getItem(bannerStorageKey) === '1')
    }
  }, [bannerStorageKey])

  const dismissBanner = () => {
    if (bannerStorageKey) sessionStorage.setItem(bannerStorageKey, '1')
    setBannerDismissed(true)
  }

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

  // Groups a list into monthly/yearly buckets by a given date field - shared by
  // both time-series charts below (Applications submitted, Scholars approved
  // and rejected) so the bucketing/labeling logic only lives in one place.
  const bucketByPeriod = (items, period, dateField) => {
    // Numeric sort key (year, or year*12+month) so buckets sort chronologically -
    // a plain string sort would put "2025-10" before "2025-9".
    const buckets = {}
    for (const item of items) {
      const raw = item[dateField]
      if (!raw) continue
      const d = new Date(raw)
      if (isNaN(d)) continue
      const key = period === 'yearly' ? d.getFullYear() : d.getFullYear() * 12 + d.getMonth()
      if (!buckets[key]) buckets[key] = []
      buckets[key].push(item)
    }
    return Object.keys(buckets).map(Number).sort((a, b) => a - b).map(key => ({
      label: period === 'yearly' ? String(key) : `${MONTH_NAMES[key % 12]} '${String(Math.floor(key / 12)).slice(2)}`,
      items: buckets[key],
    }))
  }

  const submittedData = useMemo(() => (
    bucketByPeriod(filtered, submittedPeriod, 'submitted_at')
      .map(b => ({ label: b.label, count: b.items.length }))
  ), [filtered, submittedPeriod])

  const decidedApplicants = useMemo(
    () => filtered.filter(a => a.application_status === 'Approved' || a.application_status === 'Rejected'),
    [filtered]
  )

  // Keyed by reviewed_at (when the decision was made), not submitted_at - this
  // chart is about when applicants were approved/rejected, not when they applied.
  const decidedData = useMemo(() => (
    bucketByPeriod(decidedApplicants, decidedPeriod, 'reviewed_at')
      .map(b => ({
        label: b.label,
        Approved: b.items.filter(a => a.application_status === 'Approved').length,
        Rejected: b.items.filter(a => a.application_status === 'Rejected').length,
      }))
  ), [decidedApplicants, decidedPeriod])

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
        ['Approved', String(decidedApplicants.filter(a => a.application_status === 'Approved').length)],
        ['Rejected', String(decidedApplicants.filter(a => a.application_status === 'Rejected').length)],
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
    <div className="dashboard page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>

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

      {programEnded && !bannerDismissed && (
        <div className="dash-error-banner program-ended-banner">
          <span>
            This program's deadline ({new Date(liveCycle.deadline).toLocaleDateString('en-PH', {
              month: 'long', day: 'numeric', year: 'numeric'
            })}) has passed. Export the final ranking, then reset to start a new program.
          </span>
          <div className="program-ended-banner-actions">
            <button className="btn-export" onClick={() => navigate('/admin/ranking')}>Export Ranking PDF</button>
            <button className="btn-export" onClick={() => navigate('/admin/settings')}>Reset & Start New Program</button>
            <button className="btn-dismiss-banner" onClick={dismissBanner}>Dismiss</button>
          </div>
        </div>
      )}

      {noProgramYet && (
        <div className="dash-error-banner no-program-banner">
          <span>
            No scholarship program has been set up yet. Set one up so students can start applying.
          </span>
          <div className="program-ended-banner-actions">
            <button className="btn-export" onClick={() => navigate('/admin/settings')}>Set Up Scholarship Program</button>
          </div>
        </div>
      )}

      {/* Stats */}
      {loading ? (
        <div className="loading">Loading stats...</div>
      ) : (
        <div className="stat-circles">
          {statCircles.map((stat, i) => (
            <StatTile key={stat.label} value={stat.value} label={stat.label} color={stat.color} index={i} />
          ))}
        </div>
      )}

      {/* ── ANALYTICS (formerly the standalone Reports page) ── */}
      <div className="analytics-header">
        <h3>Analytics</h3>
        <div className="analytics-controls">
          {cycles.length > 0 && (
            <select
              className="cycle-select"
              value={selectedCycle}
              onChange={e => setSelectedCycle(e.target.value)}>
              <option value="all">All programs</option>
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

      <Reveal className="charts-row">
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

        {/* Scholars Approved and Rejected */}
        <div className="dash-card">
          <div className="card-header">
            <h3>Scholars Approved and Rejected</h3>
            <div className="period-toggle">
              <button
                className={decidedPeriod === 'monthly' ? 'active' : ''}
                onClick={() => setDecidedPeriod('monthly')}>Monthly</button>
              <button
                className={decidedPeriod === 'yearly' ? 'active' : ''}
                onClick={() => setDecidedPeriod('yearly')}>Yearly</button>
            </div>
          </div>
          <p className="chart-sub-label">Final decisions only - excludes applications still in review</p>
          {decidedData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={decidedData}>
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Legend />
                <Bar dataKey="Approved" fill="#10b981" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Rejected" fill="#ef4444" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="chart-sub">No decided applications yet.</p>}
        </div>
      </Reveal>

      {/* Applications Submitted Over Time */}
      <Reveal className="dash-card">
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
      </Reveal>

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
              const isMetadataFlag = flag.reason === 'suspicious_metadata'
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
                        : isMetadataFlag
                        ? (flag.details || []).join(' ') || `"${flag.document_name}" has suspicious file metadata`
                        : `Same name + birthdate as existing applicant`}
                    </p>
                    <p className="duplicate-date">
                      Flagged: {new Date(flag.flagged_at)
                        .toLocaleDateString('en-PH', {
                          month: 'short', day: 'numeric', year: 'numeric'
                        })}
                    </p>
                    {(isDocFlag || isMetadataFlag) && (
                      <div className="duplicate-view-actions">
                        <button
                          className="btn-view-flag-doc"
                          disabled={openingDoc === `a-${flag.id}`}
                          onClick={() => handleViewFlagDoc(flag.applicant_id, flag.document_name, `a-${flag.id}`)}>
                          {openingDoc === `a-${flag.id}` ? 'Opening...' : `View ${flag.applicant_name}'s document`}
                        </button>
                        {isDocFlag && (
                          <button
                            className="btn-view-flag-doc"
                            disabled={openingDoc === `b-${flag.id}`}
                            onClick={() => handleViewFlagDoc(flag.duplicate_of_id, flag.duplicate_of_document_name || flag.document_name, `b-${flag.id}`)}>
                            {openingDoc === `b-${flag.id}` ? 'Opening...' : `View ${flag.duplicate_of_name || 'other applicant'}'s document`}
                          </button>
                        )}
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
