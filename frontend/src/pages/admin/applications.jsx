import { useState, useEffect, useCallback } from 'react'
import { apiFetch, displayStatus } from '../../api'
import './Applications.css'
import ApplicantModal from '../../components/ApplicantModal'

// Still being worked through the review pipeline - these are the ones bulk
// actions and the per-row Verify button apply to. Approved/Rejected/Withdrawn
// are already decided, so they only ever get a View action.
const REVIEWABLE_STATUSES = ['Newly Submitted', 'Pending Verification', 'Incomplete']
const WAITLISTED_STATUS = 'Waitlisted'
const DECIDED_STATUSES = ['Approved', 'Rejected', 'Withdrawn']
// Waitlisted is listed explicitly (not folded into DECIDED_STATUSES) - it's
// really "Rejected" plus a model-Eligible flag (see backend's
// compute_admin_status), not a separate stored value, but from the admin's
// perspective it isn't a closed decision either: it can still be
// auto-promoted to Approved later if a slot opens up (recompute_approvals).
// Mixing it into "Decided" would put it next to applicants who are truly,
// finally rejected - the "All" tab needs it listed here too, or splitting
// Rejected out on the backend would silently undercount its own total.
const ALL_STATUSES = [...REVIEWABLE_STATUSES, WAITLISTED_STATUS, ...DECIDED_STATUSES]

// Three visual groups in the tab bar, top to bottom: still-in-progress,
// waitlisted (eligible but bumped by the slot limit - not final), and
// already-decided - mirrors how the "All" view itself reads, as three
// separate sections rather than one date-sorted list where a five-minute-old
// submission and a five-month-old decision sit side by side.
const TAB_GROUPS = [
  {
    label: 'Needs Attention',
    tabs: [
      { label: 'Newly Submitted', key: 'Newly Submitted', value: 'Newly Submitted' },
      { label: 'Pending Verification', key: 'Pending Verification', value: 'Pending Verification' },
      { label: 'Incomplete', key: 'Incomplete', value: 'Incomplete' },
    ],
  },
  {
    label: 'Waitlisted',
    tabs: [
      { label: 'Waitlisted', key: 'Waitlisted', value: 'Waitlisted' },
    ],
  },
  {
    label: 'Decided',
    tabs: [
      { label: 'Approved', key: 'Approved', value: 'Approved' },
      { label: 'Rejected', key: 'Rejected', value: 'Rejected' },
      { label: 'Withdrawn', key: 'Withdrawn', value: 'Withdrawn' },
    ],
  },
]
const TABS = [
  { label: 'All', key: 'All', value: ALL_STATUSES.join(',') },
  ...TAB_GROUPS.flatMap(g => g.tabs),
]

const statusClass = {
  'Newly Submitted': 'badge-blue',
  'Pending Verification': 'badge-yellow',
  'Incomplete': 'badge-red',
  'Approved': 'badge-green',
  'Rejected': 'badge-red',
  'Waitlisted': 'badge-yellow',
  'Withdrawn': 'badge-gray',
}

const avatarColors = [
  '#3d6fa3','#2563eb','#059669','#dc2626',
  '#d97706','#0891b2','#be185d','#3d6fa3',
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
  { label: 'ML score (highest first)', value: '-ml_score' },
  { label: 'Name (A-Z)', value: 'full_name' },
]

const PAGE_SIZE = 20

// One applications table + its own pagination. `reviewable` decides whether
// rows get a select checkbox + Verify button (Needs Attention) or just View
// (Decided) - within any single section every row shares that same nature,
// so this never has to branch per-row the way one shared "All" table used to.
function ApplicationsTableCard({
  title, apps, total, page, pages, loading, loadError, onRetry,
  reviewable, selected, onToggleSelect, onToggleAll, onView, onVerify,
  onPrevPage, onNextPage,
}) {
  const ids = apps.map(a => a.id)
  const allSelected = reviewable && ids.length > 0 && ids.every(id => selected.includes(id))

  return (
    <div className="table-card">
      {title && (
        <div className="table-card-header">
          <h3>{title}</h3>
          <span className="table-card-count">{total}</span>
        </div>
      )}
      {loading ? (
        <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>
          Loading applications...
        </div>
      ) : loadError ? (
        <div style={{ padding: '40px', textAlign: 'center', color: '#991b1b' }}>
          <p style={{ marginBottom: '14px' }}>Couldn't load applications. Check your connection and try again.</p>
          <button className="btn-retry" onClick={onRetry}>Retry</button>
        </div>
      ) : (
        <div className="table-scroll">
        <table className="app-table">
          <thead>
            <tr>
              {reviewable && (
                <th>
                  <input type="checkbox" checked={allSelected} onChange={() => onToggleAll(ids)} />
                </th>
              )}
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
            {apps.length === 0 ? (
              <tr>
                <td colSpan={reviewable ? 8 : 7} className="empty-row">
                  No applicants found.
                </td>
              </tr>
            ) : (
              apps.map((app, i) => {
                const displayed = reviewable ? app.application_status : displayStatus(app.application_status, app.ml_status)
                return (
                <tr key={app.id}
                  className={selected.includes(app.id) ? 'selected-row' : ''}>
                  {reviewable && (
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.includes(app.id)}
                        onChange={() => onToggleSelect(app.id)}
                      />
                    </td>
                  )}
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
                    <span className={`badge ${statusClass[displayed] || 'badge-yellow'}`}>
                      {displayed || 'Pending'}
                    </span>
                  </td>
                  <td>
                    <div className="action-btns">
                      <button
                        className="action-btn view"
                        title="View"
                        onClick={() => onView(app)}>
                        View
                      </button>
                      {reviewable && (
                        <button
                          className="action-btn approve"
                          title="Verify documents & let the model decide eligibility"
                          onClick={() => onVerify(app)}>
                          Verify
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
                )
              })
            )}
          </tbody>
        </table>
        </div>
      )}

      {/* Pagination */}
      <div className="pagination">
        <p className="pagination-info">
          Showing {apps.length} of {total} applications
        </p>
        <div className="pagination-btns">
          <button className="page-btn" onClick={onPrevPage} disabled={page <= 1}>Prev</button>
          <button className="page-btn active">{page}</button>
          <button className="page-btn" onClick={onNextPage} disabled={page >= pages}>Next</button>
        </div>
      </div>
    </div>
  )
}

function Applications() {
  const [activeTab, setActiveTab] = useState('All')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('')
  const [selected, setSelected] = useState([])
  const [selectedApplicant, setSelectedApplicant] = useState(null)
  const [tabCounts, setTabCounts] = useState({})
  const [bulkVerifying, setBulkVerifying] = useState(false)

  // ── Single-tab view (any tab except "All") ──
  const [applications, setApplications] = useState([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)

  // ── "All" view: split into independently paginated sections instead of
  // one date-sorted table mixing still-pending, waitlisted, and already-
  // decided rows together ──
  const [needsApps, setNeedsApps] = useState([])
  const [needsTotal, setNeedsTotal] = useState(0)
  const [needsPages, setNeedsPages] = useState(1)
  const [needsPage, setNeedsPage] = useState(1)
  const [needsLoading, setNeedsLoading] = useState(true)
  const [needsError, setNeedsError] = useState(false)

  const [waitlistedApps, setWaitlistedApps] = useState([])
  const [waitlistedTotal, setWaitlistedTotal] = useState(0)
  const [waitlistedPages, setWaitlistedPages] = useState(1)
  const [waitlistedPage, setWaitlistedPage] = useState(1)
  const [waitlistedLoading, setWaitlistedLoading] = useState(true)
  const [waitlistedError, setWaitlistedError] = useState(false)

  const [decidedApps, setDecidedApps] = useState([])
  const [decidedTotal, setDecidedTotal] = useState(0)
  const [decidedPages, setDecidedPages] = useState(1)
  const [decidedPage, setDecidedPage] = useState(1)
  const [decidedLoading, setDecidedLoading] = useState(true)
  const [decidedError, setDecidedError] = useState(false)

  const activeStatus = TABS.find(t => t.key === activeTab)?.value || ALL_STATUSES.join(',')

  const fetchSection = useCallback(async (statusList, pageNum, setApps, setTot, setPgs, setLoad, setErr) => {
    setLoad(true)
    try {
      const params = new URLSearchParams({ page: String(pageNum), limit: String(PAGE_SIZE), status: statusList.join(','), cycle: 'current' })
      if (search.trim()) params.set('q', search.trim())
      if (sort) params.set('sort', sort)
      const res = await apiFetch(`/api/applicants?${params.toString()}`)
      if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
      const data = await res.json()
      setApps(data.applicants || [])
      setTot(data.total || 0)
      setPgs(data.pages || 1)
      setErr(false)
    } catch (err) {
      console.error('Error:', err)
      setErr(true)
    } finally {
      setLoad(false)
    }
  }, [search, sort])

  const fetchApplications = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: String(page), limit: String(PAGE_SIZE), status: activeStatus, cycle: 'current' })
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

  const fetchNeeds = useCallback(
    () => fetchSection(REVIEWABLE_STATUSES, needsPage, setNeedsApps, setNeedsTotal, setNeedsPages, setNeedsLoading, setNeedsError),
    [fetchSection, needsPage]
  )
  const fetchWaitlisted = useCallback(
    () => fetchSection([WAITLISTED_STATUS], waitlistedPage, setWaitlistedApps, setWaitlistedTotal, setWaitlistedPages, setWaitlistedLoading, setWaitlistedError),
    [fetchSection, waitlistedPage]
  )
  const fetchDecided = useCallback(
    () => fetchSection(DECIDED_STATUSES, decidedPage, setDecidedApps, setDecidedTotal, setDecidedPages, setDecidedLoading, setDecidedError),
    [fetchSection, decidedPage]
  )

  // Lightweight counts for the tab badges/stat cards - only reads `total`
  // from each response, doesn't fetch full applicant records.
  const fetchTabCounts = useCallback(async () => {
    const entries = await Promise.all(TABS.map(async tab => {
      try {
        const res = await apiFetch(`/api/applicants?page=1&limit=1&cycle=current&status=${encodeURIComponent(tab.value)}`)
        const data = await res.json()
        return [tab.key, data.total || 0]
      } catch {
        return [tab.key, 0]
      }
    }))
    setTabCounts(Object.fromEntries(entries))
  }, [])

  useEffect(() => {
    if (activeTab === 'All') return
    const t = setTimeout(fetchApplications, search ? 300 : 0)
    return () => clearTimeout(t)
  }, [fetchApplications, activeTab])

  useEffect(() => {
    if (activeTab !== 'All') return
    const t = setTimeout(fetchNeeds, search ? 300 : 0)
    return () => clearTimeout(t)
  }, [fetchNeeds, activeTab])

  useEffect(() => {
    if (activeTab !== 'All') return
    const t = setTimeout(fetchWaitlisted, search ? 300 : 0)
    return () => clearTimeout(t)
  }, [fetchWaitlisted, activeTab])

  useEffect(() => {
    if (activeTab !== 'All') return
    const t = setTimeout(fetchDecided, search ? 300 : 0)
    return () => clearTimeout(t)
  }, [fetchDecided, activeTab])

  useEffect(() => { fetchTabCounts() }, [fetchTabCounts])

  useEffect(() => {
    setPage(1); setNeedsPage(1); setWaitlistedPage(1); setDecidedPage(1); setSelected([])
  }, [activeTab, search, sort])

  const refresh = () => {
    fetchTabCounts()
    if (activeTab === 'All') { fetchNeeds(); fetchWaitlisted(); fetchDecided() }
    else fetchApplications()
  }

  const toggleSelect = (id) => {
    setSelected(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    )
  }

  const toggleAllIn = (ids) => {
    const allSelected = ids.length > 0 && ids.every(id => selected.includes(id))
    setSelected(prev => allSelected ? prev.filter(id => !ids.includes(id)) : [...new Set([...prev, ...ids])])
  }

  const handleVerifyOne = async (app) => {
    if (!window.confirm(
      `Confirm ${app.full_name}'s documents are correct and complete. ` +
      `The eligibility model will then decide Approved/Rejected automatically.`
    )) return
    const res = await apiFetch(`/api/applications/${app.id}/verify`, { method: 'PUT' })
    const data = await res.json()
    if (!res.ok) alert(data.error || 'Could not decide eligibility for this applicant')
    refresh()
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

  const reviewableIds = applications.filter(a => REVIEWABLE_STATUSES.includes(a.application_status)).map(a => a.id)

  return (
    <div className="applications-page">

      {/* Stat Cards - only the still-actionable pipeline statuses */}
      <div className="app-stats">
        {TAB_GROUPS[0].tabs.map(tab => (
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
          <button
            className={`tab-btn ${activeTab === 'All' ? 'active' : ''}`}
            onClick={() => setActiveTab('All')}>
            All
            <span className="tab-count">{tabCounts['All'] ?? '—'}</span>
          </button>
          <span className="tab-divider" aria-hidden="true" />
          {TAB_GROUPS.map(group => (
            <span key={group.label} className="tab-group">
              {group.tabs.length > 1 && <span className="tab-group-label">{group.label}</span>}
              {group.tabs.map(tab => (
                <button
                  key={tab.key}
                  className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
                  onClick={() => setActiveTab(tab.key)}>
                  {tab.label}
                  <span className="tab-count">{tabCounts[tab.key] ?? '—'}</span>
                </button>
              ))}
            </span>
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

      {activeTab === 'All' ? (
        <>
          <ApplicationsTableCard
            title="Needs Attention"
            apps={needsApps} total={needsTotal} page={needsPage} pages={needsPages}
            loading={needsLoading} loadError={needsError} onRetry={fetchNeeds}
            reviewable={true}
            selected={selected} onToggleSelect={toggleSelect} onToggleAll={toggleAllIn}
            onView={setSelectedApplicant} onVerify={handleVerifyOne}
            onPrevPage={() => setNeedsPage(p => p - 1)}
            onNextPage={() => setNeedsPage(p => p + 1)}
          />
          <ApplicationsTableCard
            title="Waitlisted"
            apps={waitlistedApps} total={waitlistedTotal} page={waitlistedPage} pages={waitlistedPages}
            loading={waitlistedLoading} loadError={waitlistedError} onRetry={fetchWaitlisted}
            reviewable={false}
            selected={selected} onToggleSelect={toggleSelect} onToggleAll={toggleAllIn}
            onView={setSelectedApplicant} onVerify={handleVerifyOne}
            onPrevPage={() => setWaitlistedPage(p => p - 1)}
            onNextPage={() => setWaitlistedPage(p => p + 1)}
          />
          <ApplicationsTableCard
            title="Decided"
            apps={decidedApps} total={decidedTotal} page={decidedPage} pages={decidedPages}
            loading={decidedLoading} loadError={decidedError} onRetry={fetchDecided}
            reviewable={false}
            selected={selected} onToggleSelect={toggleSelect} onToggleAll={toggleAllIn}
            onView={setSelectedApplicant} onVerify={handleVerifyOne}
            onPrevPage={() => setDecidedPage(p => p - 1)}
            onNextPage={() => setDecidedPage(p => p + 1)}
          />
        </>
      ) : (
        <ApplicationsTableCard
          apps={applications} total={total} page={page} pages={pages}
          loading={loading} loadError={loadError} onRetry={fetchApplications}
          reviewable={REVIEWABLE_STATUSES.includes(activeTab)}
          selected={selected} onToggleSelect={toggleSelect}
          onToggleAll={() => toggleAllIn(reviewableIds)}
          onView={setSelectedApplicant} onVerify={handleVerifyOne}
          onPrevPage={() => setPage(p => p - 1)}
          onNextPage={() => setPage(p => p + 1)}
        />
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

export default Applications
