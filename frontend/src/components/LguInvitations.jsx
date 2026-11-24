import { useState, useEffect, useCallback } from 'react'
import { apiFetch, connectionErrorMessage } from '../api'

const EMPTY_FORM = { lgu_type: 'Municipality', municipality: '', province: '', full_name: '', email: '' }
const URL_BASE = '/api/organizations/invitations'

// System Owner only: the LGUs on EcoScholar, and inviting new ones.
function LguInvitations() {
  const [data, setData] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const load = useCallback(() => (
    apiFetch(URL_BASE)
      .then(async res => {
        const body = await res.json()
        if (res.ok) setData(body)
        else setError(body.error || 'Could not load the LGUs')
      })
      .catch(() => setError(connectionErrorMessage()))
  ), [])

  useEffect(() => { load() }, [load])

  const send = async (path, options) => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const res = await apiFetch(URL_BASE + path, options)
      const body = await res.json().catch(() => ({}))
      if (!res.ok) { setError(body.error || 'Something went wrong'); return false }
      setMessage(body.message)
      await load()
      return true
    } catch {
      setError(connectionErrorMessage())
      return false
    } finally {
      setBusy(false)
    }
  }

  const invite = async e => {
    e.preventDefault()
    const ok = await send('', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    if (ok) { setForm(EMPTY_FORM); setShowForm(false) }
  }

  const cancel = org => {
    if (window.confirm(`Cancel the invitation for ${org.name}?`)) send(`/${org.id}`, { method: 'DELETE' })
  }

  const field = key => ({ value: form[key], required: true, onChange: e => setForm(p => ({ ...p, [key]: e.target.value })) })

  return (
    <div className="settings-card" style={{ marginBottom: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
        <h4 className="card-label" style={{ marginBottom: 0 }}>LGUs on EcoScholar</h4>
        {!showForm && <button className="btn-primary" onClick={() => setShowForm(true)} disabled={!data}>+ Invite an LGU</button>}
      </div>
      <p className="info-sub" style={{ marginBottom: '14px' }}>
        Each LGU has one account, identified by its municipality or city and province. You can
        invite LGUs, but you can&apos;t see their applicants.
      </p>
      {error && <div className="security-error" style={{ marginBottom: '12px' }}>{error}</div>}
      {message && <p className="info-sub" role="status" style={{ color: '#16a34a', marginBottom: '12px' }}>{message}</p>}

      {showForm && (
        <form onSubmit={invite} style={{ marginBottom: '18px' }}>
          <div className="password-fields">
            <div className="password-field">
              <label htmlFor="lgu-type">Type</label>
              <select id="lgu-type" className="settings-select" {...field('lgu_type')}>
                {data.lgu_types.map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div className="password-field">
              <label htmlFor="lgu-municipality">Municipality or city</label>
              <input id="lgu-municipality" maxLength={60} placeholder="e.g. Nagcarlan" {...field('municipality')} />
            </div>
            <div className="password-field">
              <label htmlFor="lgu-province">Province</label>
              <select id="lgu-province" className="settings-select" {...field('province')}>
                <option value="">Choose a province</option>
                {data.provinces.map(p => <option key={p}>{p}</option>)}
              </select>
            </div>
            <div className="password-field">
              <label htmlFor="lgu-name">LGU official&apos;s full name</label>
              <input id="lgu-name" maxLength={100} {...field('full_name')} />
            </div>
            <div className="password-field">
              <label htmlFor="lgu-email">LGU official&apos;s email</label>
              <input id="lgu-email" type="email" {...field('email')} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: '10px', marginTop: '12px' }}>
            <button className="btn-primary" type="submit" disabled={busy}>{busy ? 'Sending...' : 'Send Invitation'}</button>
            <button className="btn-change" type="button" onClick={() => { setShowForm(false); setError('') }}>Cancel</button>
          </div>
        </form>
      )}

      {data?.organizations.map(org => (
        <div key={org.id} className="team-row" style={{ padding: '10px 0', borderBottom: '1px solid #F0F0F0' }}>
          <div className="team-row-info">
            <span className="info-value">
              {org.name}
              {org.status === 'invited' && (
                <span className="badge" style={{ marginLeft: '8px', background: '#FEF3C7', color: '#92400E' }}>Invited</span>
              )}
            </span>
            <span className="info-sub" style={{ display: 'block' }}>
              {[[org.municipality, org.province].filter(Boolean).join(', '), org.invited_email].filter(Boolean).join(' · ')}
            </span>
          </div>
          {org.status === 'invited' && (
            <div className="team-row-actions">
              <button className="btn-change" disabled={busy} onClick={() => send(`/${org.id}/resend`, { method: 'POST' })}>Resend</button>
              <button className="btn-danger-outline" disabled={busy} onClick={() => cancel(org)}>Cancel Invitation</button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default LguInvitations
