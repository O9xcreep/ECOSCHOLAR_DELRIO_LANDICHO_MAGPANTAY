import { useState, useEffect } from 'react'
import { apiFetch, connectionErrorMessage } from '../../api'
import pageBg from '../../assets/bg1.jpg'
import './ActivityLog.css'

const CATEGORY_LABELS = {
  auth: 'Sign-in',
  account: 'Account',
  staff: 'Team',
  settings: 'Settings',
  application: 'Application',
  document: 'Document',
}

const ROLE_LABELS = {
  admin: 'Super Admin',
  lgu_admin: 'Admin',
  lgu_member: 'LGU Member',
  student: 'Student',
}

const PAGE_SIZE = 25

// Stored in UTC ("YYYY-MM-DD HH:MM:SS"); shown in the viewer's local time.
function formatWhen(utc) {
  if (!utc) return ''
  const d = new Date(utc.replace(' ', 'T') + 'Z')
  return d.toLocaleString('en-PH', {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

function ActivityLog() {
  const [page, setPage] = useState(1)
  const [category, setCategory] = useState('')
  const [outcome, setOutcome] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')

  const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) })
  if (category) params.set('category', category)
  if (outcome) params.set('outcome', outcome)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  if (appliedSearch) params.set('q', appliedSearch)
  const query = params.toString()

  // The response for whichever query was last fetched; still loading while
  // it belongs to an older query than the current filters.
  const [result, setResult] = useState({ query: null, logs: [], total: 0, error: '' })
  const loading = result.query !== query
  const { logs, total, error } = result

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      let next
      try {
        const res = await apiFetch(`/api/activity-logs?${query}`)
        const data = await res.json()
        next = res.ok
          ? { query, logs: data.logs || [], total: data.total || 0, error: '' }
          : { query, logs: [], total: 0, error: data.error || 'Could not load the activity log' }
      } catch {
        next = { query, logs: [], total: 0, error: connectionErrorMessage() }
      }
      if (!cancelled) setResult(next)
    })()
    return () => { cancelled = true }
  }, [query])

  // Any filter change goes back to the first page.
  const onFilter = setter => e => { setter(e.target.value); setPage(1) }

  const submitSearch = e => {
    e.preventDefault()
    setAppliedSearch(search.trim())
    setPage(1)
  }

  const clearFilters = () => {
    setCategory(''); setOutcome(''); setDateFrom(''); setDateTo('')
    setSearch(''); setAppliedSearch(''); setPage(1)
  }

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const hasFilters = category || outcome || dateFrom || dateTo || appliedSearch

  return (
    <div className="activity-page page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>

      <div className="page-hero">
        <h2 className="page-title">Activity Log</h2>
        <p className="page-sub">
          Every sign-in, account change, team and settings change, and document upload or view in your LGU.
        </p>
      </div>

      <div className="activity-card">
        <form className="activity-filters" onSubmit={submitSearch}>
          <input
            className="activity-input activity-search"
            type="search"
            placeholder="Search name, email, action, or applicant"
            value={search}
            onChange={e => setSearch(e.target.value)}
            aria-label="Search the activity log"
          />
          <select className="activity-input" value={category} onChange={onFilter(setCategory)} aria-label="Category">
            <option value="">All categories</option>
            {Object.entries(CATEGORY_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select className="activity-input" value={outcome} onChange={onFilter(setOutcome)} aria-label="Result">
            <option value="">All results</option>
            <option value="success">Succeeded</option>
            <option value="failure">Failed or blocked</option>
          </select>
          <label className="activity-date">
            From
            <input className="activity-input" type="date" value={dateFrom} onChange={onFilter(setDateFrom)} />
          </label>
          <label className="activity-date">
            To
            <input className="activity-input" type="date" value={dateTo} onChange={onFilter(setDateTo)} />
          </label>
          <button type="submit" className="activity-btn">Search</button>
          {hasFilters && (
            <button type="button" className="activity-btn activity-btn-ghost" onClick={clearFilters}>Clear</button>
          )}
        </form>

        {error && <p className="activity-error">{error}</p>}

        <div className="table-scroll">
          <table className="activity-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Action</th>
                <th>Details</th>
                <th>IP address</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="activity-empty">Loading…</td></tr>
              ) : logs.length === 0 ? (
                <tr><td colSpan={5} className="activity-empty">
                  {hasFilters ? 'No activity matches these filters.' : 'No activity recorded yet.'}
                </td></tr>
              ) : logs.map(log => (
                <tr key={log.id} className={log.outcome === 'failure' ? 'activity-row-failure' : ''}>
                  <td className="activity-when">{formatWhen(log.created_at)}</td>
                  <td>
                    <p className="activity-who">{log.actor_name || log.actor_email || 'Unknown'}</p>
                    <p className="activity-sub">
                      {[ROLE_LABELS[log.actor_role], log.actor_name ? log.actor_email : null].filter(Boolean).join(' · ')}
                    </p>
                  </td>
                  <td>
                    <div className="activity-action">
                      <span className={`activity-tag activity-tag-${log.category}`}>
                        {CATEGORY_LABELS[log.category] || log.category}
                      </span>
                      {log.outcome === 'failure' && <span className="activity-tag activity-tag-failure">Failed</span>}
                    </div>
                    <p className="activity-action-text">{log.action}</p>
                  </td>
                  <td className="activity-details">
                    {log.target_label && <p className="activity-target">{log.target_label}</p>}
                    {log.details && <p className="activity-sub">{log.details}</p>}
                  </td>
                  <td className="activity-ip" title={log.user_agent || ''}>{log.ip_address || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="activity-pager">
          <span>{total} {total === 1 ? 'entry' : 'entries'}</span>
          <div className="activity-pager-buttons">
            <button className="activity-btn activity-btn-ghost" disabled={page <= 1 || loading}
              onClick={() => setPage(p => p - 1)}>Previous</button>
            <span>Page {page} of {pages}</span>
            <button className="activity-btn activity-btn-ghost" disabled={page >= pages || loading}
              onClick={() => setPage(p => p + 1)}>Next</button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ActivityLog
