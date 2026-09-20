import { useState, useEffect } from 'react'
import { apiFetch, setSession, connectionErrorMessage } from '../api'
import './DisbandedOrganizationPrompt.css'

// Shown in place of the student pages while a student belongs to no organization,
// which happens when the LGU they were in is deleted by its Admin. Joining another
// one with a join code is the only way forward, so the code field is the whole page.
function DisbandedOrganizationPrompt({ disbandedName }) {
  const [joinCode, setJoinCode] = useState('')
  const [orgName, setOrgName] = useState('')
  const [codeError, setCodeError] = useState('')
  const [checking, setChecking] = useState(false)
  const [joining, setJoining] = useState(false)
  const [joinError, setJoinError] = useState('')

  // The half-finished application saved in this browser belongs to the old
  // organization too, so the next one starts from a blank form.
  useEffect(() => {
    try {
      localStorage.removeItem('applicationDraft')
    } catch {
      // storage unavailable - nothing to clear
    }
  }, [])

  const handleCodeBlur = async () => {
    const code = joinCode.trim().toUpperCase()
    setOrgName('')
    setCodeError('')
    if (!code) return
    setChecking(true)
    try {
      const res = await apiFetch(`/api/organizations/lookup?code=${encodeURIComponent(code)}`)
      const data = await res.json()
      if (!res.ok) { setCodeError(data.error || "That join code isn't valid. Check it with your LGU and try again."); return }
      setOrgName(data.organization.name)
    } catch {
      setCodeError(connectionErrorMessage())
    } finally {
      setChecking(false)
    }
  }

  const handleJoin = async () => {
    setJoinError('')
    if (!joinCode.trim()) { setJoinError('Enter a join code'); return }
    setJoining(true)
    try {
      const res = await apiFetch('/api/organizations/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ join_code: joinCode.trim().toUpperCase() })
      })
      const data = await res.json()
      if (!res.ok) { setJoinError(data.error || 'Failed to join organization'); return }
      setSession(data.user, data.token)
      // Full reload - nothing re-reads "current org" reactively after mount.
      window.location.href = '/student/dashboard'
    } catch {
      setJoinError(connectionErrorMessage())
    } finally {
      setJoining(false)
    }
  }

  return (
    <div className="dop-wrap">
      <div className="dop-card">
        <h2 className="dop-title">
          {disbandedName ? 'Your organization has been disbanded' : 'Join an organization'}
        </h2>
        {disbandedName ? (
          <p className="dop-text">
            <strong>{disbandedName}</strong> has been disbanded by its administrator. Your application,
            documents and saved information for it have been cleared, so you'll be starting fresh.
          </p>
        ) : (
          <p className="dop-text">You're not part of an organization yet.</p>
        )}
        <p className="dop-text">
          To keep using EcoScholar, join another organization with its join code. Ask that LGU's admin for it.
        </p>

        {joinError && <div className="dop-error">{joinError}</div>}

        <label className="dop-label" htmlFor="dop-join-code">LGU Join Code</label>
        <div className="dop-row">
          <input
            id="dop-join-code"
            className="dop-input"
            placeholder="e.g. ABCD1234"
            value={joinCode}
            onChange={e => { setJoinCode(e.target.value); setOrgName(''); setCodeError(''); setJoinError('') }}
            onBlur={handleCodeBlur}
            onKeyDown={e => e.key === 'Enter' && handleJoin()}
            autoFocus
          />
          <button className="dop-btn" onClick={handleJoin} disabled={joining}>
            {joining ? 'Joining...' : 'Join'}
          </button>
        </div>
        {checking && <p className="dop-hint">Checking...</p>}
        {orgName && <p className="dop-hint dop-ok">Joining {orgName}</p>}
        {codeError && <p className="dop-hint dop-bad">{codeError}</p>}
      </div>
    </div>
  )
}

export default DisbandedOrganizationPrompt
