import { useEffect, useMemo, useState } from 'react'

function OrganizationShowcase({ organizations, loading, error, onRetry }) {
  const [activeIndex, setActiveIndex] = useState(0)
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState('')

  const activeOrganization = organizations[activeIndex]
  const count = organizations.length
  const reducedMotion = useMemo(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
    [],
  )

  useEffect(() => {
    if (count < 2 || hovered || focused || reducedMotion) return undefined
    const timer = window.setInterval(() => {
      setActiveIndex(index => (index + 1) % count)
    }, 5000)
    return () => window.clearInterval(timer)
  }, [count, focused, hovered, reducedMotion])

  const copyJoinCode = async () => {
    if (!activeOrganization?.join_code) return
    setCopyError('')
    try {
      await navigator.clipboard.writeText(activeOrganization.join_code)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopyError('Could not copy. Select the code and copy it manually.')
    }
  }

  const changeOrganization = direction => {
    setActiveIndex(index => (index + direction + count) % count)
  }

  const handleBlur = event => {
    if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false)
  }

  return (
    <section
      className="lp-org-showcase"
      aria-label="Scholarship organizations"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocusCapture={() => setFocused(true)}
      onBlurCapture={handleBlur}
    >
      <div className="lp-org-showcase-heading">
        <div>
          <p className="lp-org-eyebrow">Scholarship Programs</p>
          <h2>Find your LGU</h2>
        </div>
        {count > 1 && (
          <div className="lp-org-controls">
            <span aria-live="polite">{String(activeIndex + 1).padStart(2, '0')} / {String(count).padStart(2, '0')}</span>
            <button type="button" onClick={() => changeOrganization(-1)} aria-label="Previous organization">‹</button>
            <button type="button" onClick={() => changeOrganization(1)} aria-label="Next organization">›</button>
          </div>
        )}
      </div>

      {loading ? (
        <p className="lp-org-message">Loading organizations…</p>
      ) : error ? (
        <div className="lp-org-message">
          <span>{error}</span>
          <button type="button" onClick={onRetry}>Retry</button>
        </div>
      ) : count === 0 ? (
        <p className="lp-org-message">No organizations are listed yet.</p>
      ) : (
        <div className="lp-org-card" key={activeOrganization.id}>
          <div className="lp-org-card-top">
            <div className="lp-org-name-block">
              <h3>{activeOrganization.name}</h3>
              {activeOrganization.municipality && <p>{activeOrganization.municipality}</p>}
            </div>
            <span className={`lp-org-status${activeOrganization.is_open ? ' is-open' : ''}`}>
              {activeOrganization.is_open ? 'Applications Open' : 'Not accepting'}
            </span>
          </div>
          <p className="lp-org-program">
            {activeOrganization.is_open
              ? activeOrganization.program_name || 'Scholarship applications are open'
              : activeOrganization.program_name
                ? `${activeOrganization.program_name} is closed`
                : 'No scholarship program is currently open'}
          </p>
          <div className="lp-org-code-row">
            <div>
              <span>Organization code</span>
              <strong>{activeOrganization.join_code}</strong>
            </div>
            <button type="button" onClick={copyJoinCode}>
              {copied ? 'Copied!' : 'Copy code'}
            </button>
          </div>
          {copyError && <p className="lp-org-copy-error" role="status">{copyError}</p>}
        </div>
      )}
      <p className="lp-org-hint">Use the code when creating a student account.</p>
    </section>
  )
}

export default OrganizationShowcase
