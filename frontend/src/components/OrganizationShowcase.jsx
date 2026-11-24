import { useState } from 'react'
import { parseServerDate } from '../dateUtils'

function formatDeadline(value) {
  return parseServerDate(value).toLocaleDateString('en-PH', { month: 'short', day: 'numeric', year: 'numeric' })
}

function locationOf(org) {
  return [org.municipality, org.province].filter(Boolean).join(', ')
}

function ScholarshipCard({ org, defaultOpen }) {
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState('')

  const copyJoinCode = async () => {
    setCopyError('')
    try {
      await navigator.clipboard.writeText(org.join_code)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopyError('Could not copy. Select the code and copy it manually.')
    }
  }

  return (
    <li>
      <details className="lp-org-card" open={defaultOpen}>
        <summary>
          <div className="lp-org-card-top">
            <div className="lp-org-name-block">
              <h3>{org.name}</h3>
              {org.municipality && <p>{locationOf(org)}</p>}
            </div>
            <span className={`lp-org-status${org.is_open ? ' is-open' : ''}`}>
              {org.is_open ? 'Applications Open' : 'Closed'}
            </span>
          </div>
          <p className="lp-org-program">{org.program_name || 'No scholarship program yet'}</p>
        </summary>

        {org.program_name && (
          <div className="lp-org-facts">
            {org.slots != null && <span><strong>{org.slots}</strong> {org.slots === 1 ? 'slot' : 'slots'}</span>}
            {org.deadline && (
              <span>{org.is_open ? 'Apply until' : 'Closed'} <strong>{formatDeadline(org.deadline)}</strong></span>
            )}
          </div>
        )}

        <p className="lp-org-quals-title">Qualifications</p>
        {org.qualifications?.length > 0 ? (
          <ul className="lp-org-quals">
            {org.qualifications.map((q, i) => <li key={i}>{q}</li>)}
          </ul>
        ) : (
          <p className="lp-org-program">Ask this LGU&apos;s scholarship office for the qualifications.</p>
        )}

        <div className="lp-org-code-row">
          <div>
            <span>Organization code</span>
            <strong>{org.join_code}</strong>
          </div>
          <button type="button" onClick={copyJoinCode}>{copied ? 'Copied!' : 'Copy code'}</button>
        </div>
        {copyError && <p className="lp-org-copy-error" role="status">{copyError}</p>}
      </details>
    </li>
  )
}

function OrganizationShowcase({ organizations, loading, error, onRetry }) {
  const [location, setLocation] = useState('')
  const locations = [...new Set(organizations.map(locationOf).filter(Boolean))].sort()
  // Open programs first; the server already sorts by name.
  const sorted = organizations.filter(o => !location || locationOf(o) === location).sort((a, b) => Number(b.is_open) - Number(a.is_open))

  return (
    <section className="lp-org-showcase" aria-label="Available scholarships">
      <div className="lp-org-showcase-heading">
        <div>
          <p className="lp-org-eyebrow">Scholarship Programs</p>
          <h2>Available scholarships</h2>
        </div>
        {locations.length > 1 && (
          <select className="lp-org-filter" value={location} aria-label="Filter by location"
            onChange={e => setLocation(e.target.value)}>
            <option value="">All locations</option>
            {locations.map(l => <option key={l} value={l}>{l}</option>)}
          </select>
        )}
      </div>

      {loading ? (
        <p className="lp-org-message">Loading scholarships…</p>
      ) : error ? (
        <div className="lp-org-message">
          <span>{error}</span>
          <button type="button" onClick={onRetry}>Retry</button>
        </div>
      ) : sorted.length === 0 ? (
        <p className="lp-org-message">No scholarships are listed yet.</p>
      ) : (
        <ul className="lp-org-list">
          {sorted.map((org, i) => <ScholarshipCard key={org.id} org={org} defaultOpen={i === 0} />)}
        </ul>
      )}
      <p className="lp-org-hint">Select a scholarship for details. Use its code when creating a student account.</p>
    </section>
  )
}

export default OrganizationShowcase
