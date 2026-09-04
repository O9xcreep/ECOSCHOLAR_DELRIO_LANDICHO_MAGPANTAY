import { useState, useEffect, useCallback } from 'react'
import { apiFetch, displayStatus } from '../../api'
import './applicants.css'
import ApplicantModal from '../../components/ApplicantModal'

const STATUS_TABS = [
  { label: 'All', value: 'Approved,Rejected,Withdrawn' },
  { label: 'Approved', value: 'Approved' },
  { label: 'Rejected', value: 'Rejected' },
  { label: 'Withdrawn', value: 'Withdrawn' },
]

const statusClass = {
  'Approved': 'badge-green',
  'Rejected': 'badge-red',
  'Waitlisted': 'badge-yellow',
  'Not Yet Reviewed': 'badge-yellow',
  'Newly Submitted': 'badge-blue',
  'Pending Verification': 'badge-yellow',
  'Incomplete': 'badge-red',
  'Withdrawn': 'badge-gray',
}

const avatarColors = [
  '#7c3aed', '#2563eb', '#059669', '#dc2626',
  '#d97706', '#7c3aed', '#0891b2', '#be185d',
  '#059669', '#dc2626'
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
  { label: 'ML score (highest first)', value: '-ml_score' },
  { label: 'Name (A-Z)', value: 'full_name' },
]

const PAGE_SIZE = 20

function Applicants() {
  const [applicants, setApplicants] = useState([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [activeTab, setActiveTab] = useState('All')
  const [search, setSearch] = useState('')
  const [selectedApplicant, setSelectedApplicant] = useState(null)
  const [tabCounts, setTabCounts] = useState({})
  const [sort, setSort] = useState('')

  const activeStatus = STATUS_TABS.find(t => t.label === activeTab)?.value || 'Approved,Rejected'

  // Lightweight counts for the tab badges - only reads `total` from each
  // response, doesn't fetch full applicant records.
  const fetchTabCounts = useCallback(async () => {
    const entries = await Promise.all(STATUS_TABS.map(async tab => {
      try {
        const res = await apiFetch(`/api/applicants?page=1&limit=1&status=${encodeURIComponent(tab.value)}`)
        const data = await res.json()
        return [tab.label, data.total || 0]
      } catch {
        return [tab.label, 0]
      }
    }))
    setTabCounts(Object.fromEntries(entries))
  }, [])

  const fetchApplicants = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: String(page), limit: String(PAGE_SIZE), status: activeStatus })
      if (search.trim()) params.set('q', search.trim())
      if (sort) params.set('sort', sort)
      const res = await apiFetch(`/api/applicants?${params.toString()}`)
      if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
      const data = await res.json()
      setApplicants(data.applicants || [])
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

  useEffect(() => {
    const t = setTimeout(fetchApplicants, search ? 300 : 0) // debounce search typing only
    return () => clearTimeout(t)
  }, [fetchApplicants])

  useEffect(() => { fetchTabCounts() }, [fetchTabCounts])

  // Any filter change should jump back to page 1
  useEffect(() => { setPage(1) }, [activeTab, search, sort])

  const refresh = () => { fetchApplicants(); fetchTabCounts() }

  return (
    <div className="applicants-page">

      {/* Header */}
      <div className="page-header">
        <h2 className="page-title">Applicants</h2>
        <div className="header-right">
          <select className="sort-select" value={sort} onChange={e => setSort(e.target.value)}>
            {SORT_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <div className="search-box">
            <span className="search-icon"></span>
            <input
              type="text"
              placeholder="Search Applicant..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        {STATUS_TABS.map(tab => (
          <button
            key={tab.label}
            className={`tab-btn ${activeTab === tab.label ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.label)}>
            {tab.label}
            <span className="tab-count">{tabCounts[tab.label] ?? '—'}</span>
          </button>
        ))}
      </div>

      {/* Loading */}
      {loading ? (
        <div className="empty-state">
          <p>Loading applicants...</p>
        </div>
      ) : loadError ? (
        <div className="empty-state error-state">
          <p>Couldn't load applicants. Check your connection and try again.</p>
          <button className="btn-retry" onClick={fetchApplicants}>Retry</button>
        </div>
      ) : applicants.length === 0 ? (
        <div className="empty-state">
          <p>No applicants found.</p>
        </div>
      ) : (
        <>
          <div className="cards-grid">
            {applicants.map((applicant, i) => (
              <div key={applicant.id} className="applicant-card">
                <div className="card-top">
                  <div className="applicant-avatar"
                    style={{ background: avatarColors[i % avatarColors.length] }}>
                    {getInitials(applicant.full_name)}
                  </div>
                  <span className={`badge ${statusClass[displayStatus(applicant.application_status, applicant.ml_status)] || 'badge-yellow'}`}>
                    {displayStatus(applicant.application_status, applicant.ml_status) || 'Pending'}
                  </span>
                </div>
                <div className="card-body">
                  <h4 className="applicant-name">
                    {applicant.full_name}
                    {applicant.city && <span className="applicant-city"> · {applicant.city}</span>}
                  </h4>
                  <p className="applicant-course">{applicant.course}</p>
                  <p className="applicant-gwa">GWA: <strong>{applicant.gpa}</strong></p>
                  <p className="applicant-date">
                    {applicant.submitted_at
                      ? new Date(applicant.submitted_at).toLocaleDateString('en-PH', {
                          month: 'short', day: '2-digit', year: 'numeric'
                        })
                      : 'N/A'}
                  </p>
                </div>
                <div className="card-footer">
                  <button
                    className="btn-view"
                    onClick={() => setSelectedApplicant(applicant)}>
                    View Profile
                  </button>
                </div>
              </div>
            ))}
          </div>

          {pages > 1 && (
            <div className="pagination-bar">
              <button className="btn-page" onClick={() => setPage(p => p - 1)} disabled={page <= 1}>Prev</button>
              <span className="page-info">Page {page} of {pages} ({total} total)</span>
              <button className="btn-page" onClick={() => setPage(p => p + 1)} disabled={page >= pages}>Next</button>
            </div>
          )}
        </>
      )}

      {/* Modal */}
      <ApplicantModal
        applicant={selectedApplicant}
        onClose={() => setSelectedApplicant(null)}
        onStatusChange={refresh}
      />

    </div>
  )
}

export default Applicants
