import { useState, useCallback, useEffect } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { API_BASE_URL, setSession } from '../api'
import AuthShell from '../components/AuthShell'

// Two ways to land here:
// - No token in the URL: the public, self-service LGU organization/account request
//   flow - fill in the full form (including your own email), then verify a
//   one-time code sent to that email before the request is actually
//   submitted for review.
// - A token in the URL: an existing admin already invited you directly and
//   chose your role/permissions - this is just the "set your password"
//   step, no review needed.
const css = `
  /* Page-specific additions on top of components/AuthShell.css. */
  .lp-file-upload {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 9px 10px;
    border: 1.5px dashed var(--border);
    border-radius: var(--radius);
    background: var(--bg-input);
    cursor: pointer;
    transition: border-color var(--transition), background var(--transition);
  }

  .lp-file-upload:hover { border-color: var(--brand-light); background: #fff; }

  .lp-file-upload:has(.lp-file-upload-input:focus-visible) {
    border-color: var(--brand);
    box-shadow: 0 0 0 3px rgba(217,119,6,.15);
    background: #fff;
  }

  .lp-file-upload-input {
    position: absolute;
    width: 1px; height: 1px;
    padding: 0; margin: -1px;
    overflow: hidden;
    clip: rect(0,0,0,0);
    white-space: nowrap;
    border: 0;
  }

  .lp-file-upload-icon {
    flex-shrink: 0;
    width: 30px; height: 30px;
    border-radius: 8px;
    background: rgba(217,119,6,.12);
    color: var(--brand);
    display: flex; align-items: center; justify-content: center;
  }

  .lp-file-upload-text {
    flex: 1;
    min-width: 0;
    font-size: 13.5px;
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .lp-file-upload-text.has-file { color: var(--text-primary); font-weight: 500; }

  .lp-file-upload-btn {
    flex-shrink: 0;
    padding: 7px 14px;
    border-radius: 8px;
    background: var(--brand);
    color: #fff;
    font-size: 12.5px;
    font-weight: 600;
    letter-spacing: .02em;
  }

  .lp-btn-secondary {
    background: none;
    color: var(--text-secondary);
    box-shadow: none;
    text-decoration: underline;
    text-underline-offset: 2px;
    font-weight: 500;
    margin-top: 10px;
  }

  .lp-btn-secondary:hover:not(:disabled) { opacity: .8; transform: none; box-shadow: none; }

  .spinner {
    width: 16px; height: 16px;
    border: 2.5px solid rgba(255,255,255,.4);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin .7s linear infinite;
  }

`

function ApplyAdmin() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''

  if (token) return <InviteSetup token={token} />
  return <InvitationOnly />
}

// ── INVITE MODE: an existing admin already created the account and chose its
// role/permissions - this only ever needs a password to activate it. ──
function InviteSetup({ token }) {
  const navigate = useNavigate()

  // 'checking' | 'invalid' | 'ready'
  const [status, setStatus] = useState('checking')
  const [statusError, setStatusError] = useState('')
  const [verifiedEmail, setVerifiedEmail] = useState('')
  const [inviteInfo, setInviteInfo] = useState(null)

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/admin-requests/verify-token?token=${encodeURIComponent(token)}`)
      .then(async res => {
        const result = await res.json()
        if (!res.ok || result.mode !== 'invite') {
          setStatus('invalid')
          setStatusError(result.error || 'This invitation link is no longer valid.')
          return
        }
        setVerifiedEmail(result.email)
        setInviteInfo({ fullName: result.full_name, municipality: result.municipality, role: result.role })
        setStatus('ready')
      })
      .catch(() => { setStatus('invalid'); setStatusError('Unable to reach the server. Please try again.') })
  }, [token])

  const handleSubmit = useCallback(async () => {
    setError('')
    if (!password)            { setError('Password is required'); return }
    if (password.length < 8)  { setError('Password must be at least 8 characters'); return }
    if (password !== confirmPassword) { setError('Passwords do not match'); return }

    setLoading(true)
    try {
      const res = await fetch(`${API_BASE_URL}/api/admins/complete-invite-setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: password })
      })
      const result = await res.json()
      if (!res.ok) {
        setError(result.error || 'Unable to activate your account. Please try again.')
        return
      }
      setSession(result.user, result.token)
      navigate(result.user.role === 'student' ? '/student/dashboard' : '/admin/dashboard')
    } catch {
      setError('Unable to reach the server. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [password, confirmPassword, token, navigate])

  const handleKeyDown = (e) => { if (e.key === 'Enter') handleSubmit() }

  return (
    <ApplyAdminShell>
      {status === 'checking' ? (
        <div className="lp-success-box">
          <h2>Verifying your invitation…</h2>
        </div>
      ) : status === 'invalid' ? (
        <div className="lp-success-box">
          <h2>Invitation No Longer Valid</h2>
          <p>{statusError} Please ask whoever invited you to send a new invitation.</p>
          <Link className="lp-btn" to="/login" style={{ textDecoration: 'none', display: 'flex' }}>
            Return to Sign In
          </Link>
        </div>
      ) : (
        <>
          <h2 className="lp-title">Activate Your Account</h2>
          <p className="lp-sub">
            Welcome, <strong>{inviteInfo?.fullName}</strong>
            {inviteInfo?.municipality ? ` — ${inviteInfo.municipality}. ` : '. '}
            Set a password for <strong>{verifiedEmail}</strong> to finish setting up your account.
          </p>

          {error && <div className="lp-alert error">{error}</div>}

          <div className="lp-field">
            <label>Password</label>
            <input
              className="lp-input"
              type="password"
              placeholder="Enter a password with at least 8 characters"
              value={password}
              autoComplete="new-password"
              onChange={e => { setPassword(e.target.value); setError('') }}
              onKeyDown={handleKeyDown}
              autoFocus
            />
          </div>

          <div className="lp-field">
            <label>Confirm Password</label>
            <input
              className="lp-input"
              type="password"
              placeholder="Re-enter your password"
              value={confirmPassword}
              autoComplete="new-password"
              onChange={e => { setConfirmPassword(e.target.value); setError('') }}
              onKeyDown={handleKeyDown}
            />
            {confirmPassword && confirmPassword !== password && (
              <p style={{ fontSize: '12px', color: 'var(--danger)', marginTop: '4px' }}>Passwords do not match</p>
            )}
          </div>

          <button className="lp-btn" onClick={handleSubmit} disabled={loading}>
            {loading ? <><span className="spinner" /> Activating…</> : 'Activate Account'}
          </button>
        </>
      )}
    </ApplyAdminShell>
  )
}

// LGU accounts are by invitation: without one there is nothing to fill in here.
function InvitationOnly() {
  return (
    <ApplyAdminShell>
      <div className="lp-success-box">
        <h2>By Invitation Only</h2>
        <p>
          LGUs join EcoScholar by invitation from the System Owner. If you received an invitation
          email, use your code to set up your account.
        </p>
        <Link className="lp-btn" to="/admin-setup" style={{ textDecoration: 'none', display: 'flex' }}>
          I Have an Invitation
        </Link>
        <p style={{ marginTop: '16px' }}><Link className="lp-link" to="/login">Return to Sign In</Link></p>
      </div>
    </ApplyAdminShell>
  )
}

function ApplyAdminShell({ children }) {
  return (
    <>
      <style>{css}</style>
      <AuthShell>{children}</AuthShell>
    </>
  )
}

export default ApplyAdmin
