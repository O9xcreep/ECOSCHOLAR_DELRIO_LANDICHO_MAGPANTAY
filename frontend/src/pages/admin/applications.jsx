import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../../api'
import './Applications.css'
import ApplicantModal from '../../components/ApplicantModal'

const PAGE_STATUSES = [
  'Newly Submitted',
  'Pending Verification',
  'Not Yet Reviewed',
  'Incomplete'
]

const TABS = [
  { label: 'All', key: 'All', value: PAGE_STATUSES.join(',') },
  { label: 'Newly Submitted', key: 'Newly Submitted', value: 'Newly Submitted' },
  { label: 'Pending Verification', key: 'Pending Verification', value: 'Pending Verification' },
  { label: 'Not Yet Reviewed', key: 'Not Yet Reviewed', value: 'Not Yet Reviewed' },
  { label: 'Incomplete', key: 'Incomplete', value: 'Incomplete' },
]

const statusClass = {
  'Newly Submitted': 'badge-blue',
  'Pending Verification': 'badge-yellow',
  'Not Yet Reviewed': 'badge-purple',
  'Incomplete': 'badge-red',
}

const avatarColors = [
  '#7c3aed','#2563eb','#059669','#dc2626',
  '#d97706','#0891b2','#be185d','#7c3aed',
  '#2563eb','#059669'
]

function getInitials(name) {
  if (!name) return '?'
  return name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
}

const SORT_OPTIONS = [
  { label: 'Newest first', value: '' },
  { label: 'Submitted date (oldest first)', value: 'submitted_at' },
  { label: 'GWA (highest first)', value: '-gpa' },
  { label: 'GWA (lowest first)', value: 'gpa' },
  { label: 'Name (A-Z)', value: 'full_name' },
]

const PAGE_SIZE = 20

function Applications() {
  const [applications, setApplications] = useState([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [activeTab, setActiveTab] = useState('All')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState([])
  const [selectedApplicant, setSelectedApplicant] = useState(null)
  const [tabCounts, setTabCounts] = useState({})
  const [bulkVerifying, setBulkVerifying] = useState(false)
  const [sort, setSort] = useState('')

  const activeStatus = TABS.find(t => t.key === activeTab)?.value || PAGE_STATUSES.join(',')

  const fetchApplications = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: String(page), limit: String(PAGE_SIZE), status: activeStatus })
      if (search.trim()) params.set('q', search.trim())
      if (sort) params.set('sort', sort)
      const res = await apiFetch(`/api/applicants?${params.toString()}`)
      if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
      const data = await res.json()
      setApplications(data.applicants || [])
      setTotal(data.total || 0)
      setPages(data.pages || 1)
      setLoadError(false)
    } catch (err) {
      console.error('Error:', err)
      setLoadError(true)
    } finally {
      setLoading(false)
    }
  }, [page, activeStatus, search, sort])

  // Lightweight counts for the tab badges/stat cards - only reads `total`
  // from each response, doesn't fetch full applicant records.
  const fetchTabCounts = useCallback(async () => {
    const entries = await Promise.all(TABS.map(async tab => {
      try {
        const res = await apiFetch(`/api/applicants?page=1&limit=1&status=${encodeURIComponent(tab.value)}`)
        const data = await res.json()
        return [tab.key, data.total || 0]
      } catch {
        return [tab.key, 0]
      }
    }))
    setTabCounts(Object.fromEntries(entries))
  }, [])

  useEffect(() => {
    const t = setTimeout(fetchApplications, search ? 300 : 0)
    return () => clearTimeout(t)
  }, [fetchApplications])

  useEffect(() => { fetchTabCounts() }, [fetchTabCounts])

  useEffect(() => { setPage(1); setSelected([]) }, [activeTab, search, sort])

  const refresh = () => { fetchApplications(); fetchTabCounts() }

  const toggleSelect = (id) => {
    setSelected(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    )
  }

  const toggleAll = () => {
    if (selected.length === applications.length) setSelected([])
    else setSelected(applications.map(a => a.id))
  }

  const handleBulkVerify = async () => {
    if (!window.confirm(
      `Verify documents for ${selected.length} selected applicant(s)? ` +
      `The eligibility model will decide Approved/Rejected automatically for each.`
    )) return
    setBulkVerifying(true)
    try {
      const res = await apiFetch('/api/applications/bulk-verify', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ applicant_ids: selected })
      })
      const data = await res.json()
      if (!res.ok) {
        alert(data.error || 'Bulk verification failed')
      } else {
        const failed = (data.results || []).filter(r => r.error)
        if (failed.length > 0) {
          alert(`${data.succeeded} of ${data.total} verified successfully. ${failed.length} could not be processed (e.g. pre-model submissions).`)
        }
      }
      setSelected([])
      refresh()
    } catch {
      alert('Cannot connect to server. Please try again.')
    } finally {
      setBulkVerifying(false)
    }
  }

  return (
    <div className="applications-page">

      {/* Stat Cards */}
      <div className="app-stats">
        {TABS.slice(1).map(tab => (
          <div key={tab.key}
            className={`app-stat-card stat-${tab.key.replace(/\s/g, '-').toLowerCase()}`}>
            <h3>{tabCounts[tab.key] ?? '—'}</h3>
            <p>{tab.label}</p>
          </div>
        ))}
      </div>

      {/* Header */}
      <div className="page-header">
        <div className="tabs">
          {TABS.map(tab => (
            <button
              key={tab.key}
              className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.key)}>
              {tab.label}
              <span className="tab-count">{tabCounts[tab.key] ?? '—'}</span>
            </button>
          ))}
        </div>
        <div className="header-actions">
          <select className="sort-select" value={sort} onChange={e => setSort(e.target.value)}>
            {SORT_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <div className="search-box">
            <span></span>
            <input
              type="text"
              placeholder="Search applicant..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>
      </div>

      {selected.length > 0 && (
        <div className="bulk-action-bar">
          <span>{selected.length} selected</span>
          <button className="btn-bulk-verify" onClick={handleBulkVerify} disabled={bulkVerifying}>
            {bulkVerifying ? 'Verifying…' : `Verify Selected (${selected.length})`}
          </button>
          <button className="btn-bulk-cancel" onClick={() => setSelected([])}>Clear</button>
        </div>
      )}

      {/* Table */}
      <div className="table-card">
        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>
            Loading applications...
          </div>
        ) : loadError ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#991b1b' }}>
            <p style={{ marginBottom: '14px' }}>Couldn't load applications. Check your connection and try again.</p>
            <button className="btn-retry" onClick={fetchApplications}>Retry</button>
          </div>
        ) : (
          <table className="app-table">
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    checked={selected.length === applications.length && applications.length > 0}
                    onChange={toggleAll}
                  />
                </th>
                <th>APPLICANT</th>
                <th>APPLICATION</th>
                <th>COURSE</th>
                <th>GWA</th>
                <th>SUBMITTED</th>
                <th>STATUS</th>
                <th>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {applications.length === 0 ? (
                <tr>
                  <td colSpan="8" className="empty-row">
                    No applications found.
                  </td>
                </tr>
              ) : (
                applications.map((app, i) => (
                  <tr key={app.id}
                    className={selected.includes(app.id) ? 'selected-row' : ''}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.includes(app.id)}
                        onChange={() => toggleSelect(app.id)}
                      />
                    </td>
                    <td>
                      <div className="applicant-cell">
                        <div className="mini-avatar"
                          style={{ background: avatarColors[i % avatarColors.length] }}>
                          {getInitials(app.full_name)}
                        </div>
                        <div>
                          <p className="cell-name">
                            {app.full_name}
                            {app.has_other_scholarship === 1 && (
                              <span className="scholarship-flag" title={`Also receiving: ${app.other_scholarship_details}`}>
                                Other scholarship
                              </span>
                            )}
                          </p>
                          <p className="cell-email">{app.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="cell-app">
                      {app.application_type || 'General'}
                    </td>
                    <td className="cell-course">{app.course}</td>
                    <td className="cell-gwa">{app.gpa}</td>
                    <td className="cell-date">
                      {app.submitted_at
                        ? new Date(app.submitted_at).toLocaleDateString('en-PH', {
                            month: 'short', day: '2-digit', year: 'numeric'
                          })
                        : 'N/A'}
                    </td>
                    <td>
                      <span className={`badge ${statusClass[app.application_status] || 'badge-yellow'}`}>
                        {app.application_status || 'Pending'}
                      </span>
                    </td>
                    <td>
                      <div className="action-btns">
                        <button
                          className="action-btn view"
                          title="View"
                          onClick={() => setSelectedApplicant(app)}>
                          View
                        </button>
                        <button
                          className="action-btn approve"
                          title="Verify documents & let the model decide eligibility"
                          onClick={async () => {
                            if (!window.confirm(
                              `Confirm ${app.full_name}'s documents are correct and complete. ` +
                              `The eligibility model will then decide Approved/Rejected automatically.`
                            )) return
                            const res = await apiFetch(
                              `/api/applications/${app.id}/verify`,
                              { method: 'PUT' }
                            )
                            const data = await res.json()
                            if (!res.ok) alert(data.error || 'Could not decide eligibility for this applicant')
                            refresh()
                          }}>
                          Verify
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}

        {/* Pagination */}
        <div className="pagination">
          <p className="pagination-info">
            Showing {applications.length} of {total} applications
          </p>
          <div className="pagination-btns">
            <button className="page-btn" onClick={() => setPage(p => p - 1)} disabled={page <= 1}>Prev</button>
            <button className="page-btn active">{page}</button>
            <button className="page-btn" onClick={() => setPage(p => p + 1)} disabled={page >= pages}>Next</button>
          </div>
        </div>
      </div>

      {/* Modal */}
      <ApplicantModal
        applicant={selectedApplicant}
        onClose={() => setSelectedApplicant(null)}
        onStatusChange={refresh}
      />

    </div>
  )
}

export default Applications
