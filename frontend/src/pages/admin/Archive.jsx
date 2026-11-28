import { useState, useEffect } from 'react'
import { apiFetch, displayStatus, connectionErrorMessage } from '../../api'
import { parseServerDate } from '../../dateUtils'
import pageBg from '../../assets/bg1.jpg'
import './ActivityLog.css'
import { DictationField } from '../../components/MicButton'
import { dictationToSearch } from '../../dictation'

const PAGE_SIZE = 25

function formatDate(utc) {
  if (!utc) return '—'
  return parseServerDate(utc).toLocaleDateString('en-PH', { month: 'short', day: 'numeric', year: 'numeric' })
}

// Read-only view of past programs. Starting a new program archives the previous one.
function Archive() {
  const [cycles, setCycles] = useState(null)
  const [cyclesError, setCyclesError] = useState('')
  const [cycleId, setCycleId] = useState('')
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [result, setResult] = useState({ query: null, applicants: [], total: 0, pages: 1, error: '' })

  useEffect(() => {
    apiFetch('/api/program-cycles')
      .then(async res => {
        const data = await res.json()
        if (!res.ok) throw new Error(data.error)
        const past = (data.cycles || []).filter(c => c.id && !c.is_current)
        setCycles(past)
        setCycleId(past[0]?.id || '')
      })
      .catch(err => { setCycles([]); setCyclesError(err.message || connectionErrorMessage()) })
  }, [])

  const params = new URLSearchParams({ cycle: cycleId, page: String(page), limit: String(PAGE_SIZE), sort: 'full_name' })
  if (appliedSearch) params.set('q', appliedSearch)
  const query = cycleId ? params.toString() : ''
  const loading = cycles === null || (query && result.query !== query)

  useEffect(() => {
    if (!query) return undefined
    let cancelled = false
    ;(async () => {
      let next = { query, applicants: [], total: 0, pages: 1, error: '' }
      try {
        const res = await apiFetch(`/api/applicants?${query}`)
        const data = await res.json()
        next = res.ok
          ? { ...next, applicants: data.applicants, total: data.total, pages: data.pages }
          : { ...next, error: data.error || 'Could not load the archive' }
      } catch {
        next.error = connectionErrorMessage()
      }
      if (!cancelled) setResult(next)
    })()
    return () => { cancelled = true }
  }, [query])

  const cycle = cycles?.find(c => c.id === cycleId)
  const error = cyclesError || result.error

  return (
    <div className="activity-page page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>
      <div className="page-hero">
        <h2 className="page-title">Archive</h2>
        <p className="page-sub">Past scholarship programs and their applicants. Records here are view-only.</p>
      </div>

      <div className="activity-card">
        {cycles?.length > 0 && (
          <form className="activity-filters" onSubmit={e => { e.preventDefault(); setAppliedSearch(search.trim()); setPage(1) }}>
            <select className="activity-input" value={cycleId} aria-label="Program"
              onChange={e => { setCycleId(e.target.value); setPage(1) }}>
              {cycles.map(c => <option key={c.id} value={c.id}>{c.label} ({c.applicant_count})</option>)}
            </select>
            <DictationField compact className="activity-search" label="the archive search"
              onText={t => { const q = dictationToSearch(t); setSearch(q); setAppliedSearch(q); setPage(1) }}>
              <input className="activity-input" type="search" placeholder="Search name or course"
                aria-label="Search archived applicants" value={search} onChange={e => setSearch(e.target.value)} />
            </DictationField>
            <button type="submit" className="activity-btn">Search</button>
          </form>
        )}

        {cycle && (
          <p className="activity-sub" style={{ padding: '10px 20px' }}>
            Started {formatDate(cycle.started_at)} · Deadline {formatDate(cycle.deadline)} · Archived {formatDate(cycle.closed_at)}
          </p>
        )}
        {error && <p className="activity-error">{error}</p>}

        <div className="table-scroll">
          <table className="activity-table">
            <thead>
              <tr><th>Applicant</th><th>School</th><th>Course</th><th>GWA</th><th>Score</th><th>Status</th><th>Submitted</th></tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} className="activity-empty">Loading…</td></tr>
              ) : !cycleId ? (
                <tr><td colSpan={7} className="activity-empty">
                  Nothing archived yet. A program moves here when you start the next one in Settings.
                </td></tr>
              ) : result.applicants.length === 0 ? (
                <tr><td colSpan={7} className="activity-empty">No applicants found.</td></tr>
              ) : result.applicants.map(a => (
                <tr key={a.id}>
                  <td><p className="activity-who">{a.full_name}</p><p className="activity-sub">{a.email}</p></td>
                  <td>{a.school || '—'}</td>
                  <td>{a.course || '—'}</td>
                  <td>{a.gpa ?? '—'}</td>
                  <td>{a.ml_status === 'Pending' ? '—' : a.ml_score}</td>
                  <td>
                    {displayStatus(a.application_status, a.ml_status)}
                    {a.rejection_reasons?.length > 0 && <p className="activity-sub">{a.rejection_reasons.join('; ')}</p>}
                  </td>
                  <td className="activity-when">{formatDate(a.submitted_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {cycleId && (
          <div className="activity-pager">
            <span>{result.total} {result.total === 1 ? 'applicant' : 'applicants'}</span>
            <div className="activity-pager-buttons">
              <button className="activity-btn activity-btn-ghost" disabled={page <= 1 || loading} onClick={() => setPage(p => p - 1)}>Previous</button>
              <span>Page {page} of {result.pages}</span>
              <button className="activity-btn activity-btn-ghost" disabled={page >= result.pages || loading} onClick={() => setPage(p => p + 1)}>Next</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default Archive
