import { useState, useEffect, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell
} from 'recharts'
import jsPDF from 'jspdf'
import autoTable from 'jspdf-autotable'
import { apiFetch } from '../../api'
import './reports.css'

const STATUS_COLORS = {
  'Approved': '#10b981',
  'Rejected': '#ef4444',
  'Newly Submitted': '#2563eb',
  'Pending Verification': '#f59e0b',
  'Not Yet Reviewed': '#0891b2',
  'Incomplete': '#ef4444',
}

// Applicants who applied before the current eligibility model store GWA on the
// old Philippine 1.00 (highest) - 5.00 (lowest) scale; applicants since then use
// the 75-99 percentage scale the model expects. Both need to land in the same
// chart, so legacy values are approximated to percentage here for display only
// (this never feeds the eligibility model - see schema/ml_model.md).
const OLD_SCALE_TO_PERCENT = [
  [1.00, 98], [1.25, 95], [1.50, 92], [1.75, 89], [2.00, 86],
  [2.25, 83], [2.50, 80], [2.75, 77], [3.00, 75],
]

function normalizeGwaToPercent(gpa) {
  if (isNaN(gpa)) return null
  if (gpa > 5) return gpa // already on the percentage scale
  let closest = OLD_SCALE_TO_PERCENT[0]
  for (const pair of OLD_SCALE_TO_PERCENT) {
    if (Math.abs(pair[0] - gpa) < Math.abs(closest[0] - gpa)) closest = pair
  }
  return closest[1]
}

const GWA_BUCKETS = [
  { range: '75-79', min: 75, max: 79.999 },
  { range: '80-84', min: 80, max: 84.999 },
  { range: '85-89', min: 85, max: 89.999 },
  { range: '90-94', min: 90, max: 94.999 },
  { range: '95-99', min: 95, max: 99 },
]

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function Reports() {
  const [applicants, setApplicants] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [cycles, setCycles] = useState([])
  const [selectedCycle, setSelectedCycle] = useState('all')

  useEffect(() => {
    apiFetch('/api/applicants')
      .then(res => res.json())
      .then(data => {
        setApplicants(data.applicants || [])
        setLoading(false)
      })
      .catch(() => {
        setError('Could not load report data.')
        setLoading(false)
      })

    apiFetch('/api/program-cycles')
      .then(res => res.json())
      .then(data => setCycles(data.cycles || []))
      .catch(() => {})
  }, [])

  // Every cycle option beyond "All cycles" narrows the already-fetched full list
  // client-side, rather than re-fetching - the report already needs every applicant's
  // full record for its charts regardless of which cycle is selected.
  const filtered = useMemo(() => {
    if (selectedCycle === 'all') return applicants
    if (selectedCycle === 'legacy') return applicants.filter(a => !a.cycle_id)
    return applicants.filter(a => a.cycle_id === selectedCycle)
  }, [applicants, selectedCycle])

  const stats = useMemo(() => {
    const total = filtered.length
    const approved = filtered.filter(a => a.application_status === 'Approved').length
    const rejected = filtered.filter(a => a.application_status === 'Rejected').length
    const underReview = total - approved - rejected
    return [
      { label: 'Total Applicants', value: total, color: 'purple' },
      { label: 'Approved', value: approved, color: 'green' },
      { label: 'Under Review', value: underReview, color: 'yellow' },
      { label: 'Rejected', value: rejected, color: 'red' },
    ]
  }, [filtered])

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

  const gwaPercents = useMemo(() => {
    return filtered
      .map(a => normalizeGwaToPercent(parseFloat(a.gpa)))
      .filter(v => v !== null)
  }, [filtered])

  const gwaDistribution = useMemo(() => {
    return GWA_BUCKETS.map(bucket => ({
      range: bucket.range,
      count: gwaPercents.filter(v => v >= bucket.min && v <= bucket.max).length
    }))
  }, [gwaPercents])

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
        const [, month] = key.split('-')
        return { month: MONTH_NAMES[Number(month)], count }
      })
  }, [filtered])

  const byType = useMemo(() => {
    const groups = {}
    for (const a of filtered) {
      const type = a.application_type || 'General Application'
      if (!groups[type]) groups[type] = { name: type, applicants: 0, approved: 0, rejected: 0, review: 0 }
      groups[type].applicants++
      if (a.application_status === 'Approved') groups[type].approved++
      else if (a.application_status === 'Rejected') groups[type].rejected++
      else groups[type].review++
    }
    return Object.values(groups)
  }, [filtered])

  const total = stats[0].value

  const handleExportPdf = () => {
    const doc = new jsPDF()
    const generatedAt = new Date().toLocaleString('en-PH', { dateStyle: 'medium', timeStyle: 'short' })

    doc.setFontSize(16)
    doc.text('EcoScholar - Applications Report', 14, 18)
    doc.setFontSize(10)
    doc.setTextColor(120)
    doc.text(`Generated ${generatedAt}`, 14, 25)

    autoTable(doc, {
      startY: 32,
      head: [['Metric', 'Value']],
      body: stats.map(s => [s.label, String(s.value)]),
      theme: 'grid',
      headStyles: { fillColor: [124, 58, 237] },
    })

    autoTable(doc, {
      startY: doc.lastAutoTable.finalY + 10,
      head: [['Status', 'Count', 'Share']],
      body: statusBreakdown.map(item => [
        item.name, String(item.value), total ? `${Math.round((item.value / total) * 100)}%` : '0%'
      ]),
      theme: 'grid',
      headStyles: { fillColor: [124, 58, 237] },
    })

    autoTable(doc, {
      startY: doc.lastAutoTable.finalY + 10,
      head: [['Application Type', 'Applicants', 'Approved', 'Rejected', 'Under Review', 'Approval Rate']],
      body: byType.map(row => {
        const rate = row.applicants ? Math.round((row.approved / row.applicants) * 100) : 0
        return [row.name, row.applicants, row.approved, row.rejected, row.review, `${rate}%`]
      }),
      theme: 'grid',
      headStyles: { fillColor: [124, 58, 237] },
    })

    doc.save(`ecoscholar-report-${new Date().toISOString().slice(0, 10)}.pdf`)
  }

  if (loading) return <div className="reports-page"><p className="page-sub">Loading reports…</p></div>
  if (error) return <div className="reports-page"><p className="page-sub">{error}</p></div>

  return (
    <div className="reports-page">

      {/* Header */}
      <div className="reports-header">
        <div>
          <h2 className="page-title">Reports</h2>
          <p className="page-sub">Analytics overview for scholarship applications</p>
        </div>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap', minWidth: 0 }}>
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

      {/* Stat Cards */}
      <div className="reports-stats">
        {stats.map((s, i) => (
          <div key={i} className={`report-stat stat-${s.color}`}>
            <div>
              <h3>{s.value}</h3>
              <p>{s.label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="charts-row">

        {/* Status Breakdown */}
        <div className="chart-card wide">
          <h3>Application status breakdown</h3>
          <p className="chart-sub">Out of {total} total applicants</p>
          <div className="bar-list">
            {statusBreakdown.map((item, i) => (
              <div key={i} className="bar-row">
                <span className="bar-label">{item.name}</span>
                <div className="bar-track">
                  <div
                    className="bar-fill"
                    style={{
                      width: total ? `${(item.value / total) * 100}%` : '0%',
                      background: item.color
                    }}
                  />
                </div>
                <span className="bar-value">{item.value}</span>
              </div>
            ))}
            {statusBreakdown.length === 0 && <p className="chart-sub">No applications yet.</p>}
          </div>
        </div>

        {/* Donut Chart */}
        <div className="chart-card">
          <h3>Status distribution</h3>
          <p className="chart-sub">Share of all applications</p>
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
                    <span>{item.name} ({total ? Math.round((item.value / total) * 100) : 0}%)</span>
                  </div>
                ))}
              </div>
            </>
          ) : <p className="chart-sub">No applications yet.</p>}
        </div>

      </div>

      {/* Charts Row 2 */}
      <div className="charts-row">

        {/* GWA Distribution */}
        <div className="chart-card">
          <h3>GWA distribution</h3>
          <p className="chart-sub">
            Number of applicants per GWA range (percentage scale - older
            applications on the 1.00-5.00 scale are approximated here)
          </p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={gwaDistribution}>
              <XAxis dataKey="range" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="var(--accent)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Monthly Applications */}
        <div className="chart-card">
          <h3>Monthly applications</h3>
          <p className="chart-sub">Applications submitted per month</p>
          {monthlyData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={monthlyData}>
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="#6ee7b7" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="chart-sub">No applications yet.</p>}
        </div>

      </div>

      {/* By Application Type */}
      <div className="table-card">
        <h3>Applicants by application type</h3>
        <p className="chart-sub">Outcome breakdown per application type</p>
        <div className="table-scroll">
        <table className="reports-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Applicants</th>
              <th>Approved</th>
              <th>Rejected</th>
              <th>Under Review</th>
              <th>Approval Rate</th>
            </tr>
          </thead>
          <tbody>
            {byType.map((row, i) => {
              const rate = row.applicants ? Math.round((row.approved / row.applicants) * 100) : 0
              return (
                <tr key={i}>
                  <td><span className="scholarship-name">{row.name}</span></td>
                  <td>{row.applicants}</td>
                  <td><span className="badge badge-green">{row.approved}</span></td>
                  <td><span className="badge badge-red">{row.rejected}</span></td>
                  <td><span className="badge badge-yellow">{row.review}</span></td>
                  <td>
                    <div className="usage-cell">
                      <div className="usage-track">
                        <div
                          className="usage-fill"
                          style={{
                            width: `${rate}%`,
                            background: rate >= 60 ? '#10b981' : rate >= 30 ? '#f59e0b' : '#ef4444'
                          }}
                        />
                      </div>
                      <span className="usage-pct">{rate}%</span>
                    </div>
                  </td>
                </tr>
              )
            })}
            {byType.length === 0 && (
              <tr><td colSpan={6} className="chart-sub">No applications yet.</td></tr>
            )}
          </tbody>
        </table>
        </div>
      </div>

    </div>
  )
}

export default Reports
