import { useState, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { API_BASE_URL, fetchWithTimeout, connectionErrorMessage } from '../api'
import AuthShell from '../components/AuthShell'

// For a team member an existing admin invited directly (Settings > Team > Add
// Admin, or Resend Invite) - they got an emailed 6-digit code, not a link.
// Entering it here only proves the email is theirs; choosing a password
// happens next on /apply-admin, the same page the public "Apply as Admin"
// flow uses to finish creating an account.

function AdminSetup() {
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [resendMessage, setResendMessage] = useState('')
  const [resendLoading, setResendLoading] = useState(false)

  const handleSubmit = useCallback(async () => {
    setError('')
    if (!email.trim()) { setError('Email is required'); return }
    if (!code.trim())  { setError('Enter the code from your email'); return }

    setLoading(true)
    try {
      const res = await fetchWithTimeout(`${API_BASE_URL}/api/admins/verify-setup-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), code: code.trim() })
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.error || 'Something went wrong. Please try again.')
        return
      }
      navigate(`/apply-admin?token=${encodeURIComponent(data.token)}`)
    } catch {
      setError(connectionErrorMessage())
    } finally {
      setLoading(false)
    }
  }, [email, code, navigate])

  const handleResend = useCallback(async () => {
    setResendMessage('')
    if (!email.trim()) { setError('Enter your email first'); return }
    setResendLoading(true)
    try {
      await fetchWithTimeout(`${API_BASE_URL}/api/admins/resend-setup-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase() })
      })
      setResendMessage('If that email has a pending invite, a new code has been sent.')
    } catch {
      setResendMessage(connectionErrorMessage())
    } finally {
      setResendLoading(false)
    }
  }, [email])

  const handleKeyDown = (e) => { if (e.key === 'Enter') handleSubmit() }

  return (
    <AuthShell>
        <h2 className="lp-title">Activate Your Invite</h2>
        <p className="lp-sub">Enter the code sent to your email to continue setting up your account.</p>

        {error && <div className="lp-alert error">{error}</div>}

        <div className="lp-field">
          <label>Email</label>
          <input
            className="lp-input"
            type="email"
            placeholder="you@lgu.gov.ph"
            value={email}
            onChange={e => { setEmail(e.target.value); setError('') }}
            onKeyDown={handleKeyDown}
            autoFocus
          />
        </div>

        <div className="lp-field">
          <label>Verification Code</label>
          <input
            className="lp-input"
            type="text"
            inputMode="numeric"
            maxLength={6}
            placeholder="123456"
            value={code}
            onChange={e => { setCode(e.target.value.replace(/\D/g, '')); setError('') }}
            onKeyDown={handleKeyDown}
          />
        </div>

        <button className="lp-btn" onClick={handleSubmit} disabled={loading}>
          {loading ? 'Verifying…' : 'Continue'}
        </button>

        <button className="lp-link lp-center-link" type="button" onClick={handleResend} disabled={resendLoading}>
          {resendLoading ? 'Sending…' : "Didn't get a code? Resend"}
        </button>
        {resendMessage && <p style={{ textAlign: 'center', fontSize: '13px', color: 'var(--text-secondary)', marginTop: '6px' }}>{resendMessage}</p>}

        <Link className="lp-link lp-center-link" to="/login">Back to login</Link>
    </AuthShell>
  )
}

export default AdminSetup
