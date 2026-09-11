import { useState, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { API_BASE_URL } from '../api'

// For a team member an existing admin invited directly (Settings > Team > Add
// Admin, or Resend Invite) - they got an emailed 6-digit code, not a link.
// Entering it here only proves the email is theirs; choosing a password
// happens next on /apply-admin, the same page the public "Apply as Admin"
// flow uses to finish creating an account.
const css = `
  .rp-page {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #eaf0f7;
    font-family: 'DM Sans', sans-serif;
    padding: 20px;
  }
  .rp-card {
    width: 100%;
    max-width: 400px;
    background: #FFFFFF;
    border-radius: 16px;
    padding: 40px 36px;
    box-shadow: 0 10px 40px rgba(61,111,163,.18);
  }
  .rp-title { font-size: 22px; font-weight: 700; color: #1A1A2E; margin-bottom: 8px; }
  .rp-sub { font-size: 14px; color: #4b5563; margin-bottom: 24px; line-height: 1.5; }
  .rp-field { margin-bottom: 16px; }
  .rp-field label { display: block; font-size: 13px; font-weight: 600; color: #1A1A2E; margin-bottom: 6px; }
  .rp-input {
    width: 100%;
    padding: 12px 14px;
    border: 1.5px solid #E5E7EB;
    border-radius: 10px;
    font-size: 14px;
    background: #F9FAFB;
    outline: none;
  }
  .rp-input:focus { border-color: #3d6fa3; }
  .rp-alert {
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13px;
    margin-bottom: 16px;
  }
  .rp-alert.error { background: #FEE2E2; color: #B91C1C; }
  .rp-btn {
    width: 100%;
    padding: 13px;
    background: #3d6fa3;
    color: #fff;
    border: none;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  }
  .rp-btn:disabled { opacity: .6; cursor: default; }
  .rp-btn:hover:not(:disabled) { background: #2c5580; }
  .rp-link { display: block; text-align: center; margin-top: 18px; font-size: 13px; color: #3d6fa3; text-decoration: none; font-weight: 600; background: none; border: none; cursor: pointer; }
`

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
      const res = await fetch(`${API_BASE_URL}/api/admins/verify-setup-code`, {
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
      setError('Cannot connect to server. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [email, code, navigate])

  const handleResend = useCallback(async () => {
    setResendMessage('')
    if (!email.trim()) { setError('Enter your email first'); return }
    setResendLoading(true)
    try {
      await fetch(`${API_BASE_URL}/api/admins/resend-setup-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase() })
      })
      setResendMessage('If that email has a pending invite, a new code has been sent.')
    } catch {
      setResendMessage('Cannot connect to server. Please try again.')
    } finally {
      setResendLoading(false)
    }
  }, [email])

  const handleKeyDown = (e) => { if (e.key === 'Enter') handleSubmit() }

  return (
    <div className="rp-page">
      <style>{css}</style>
      <div className="rp-card">
        <p className="rp-title">Activate Your Invite</p>
        <p className="rp-sub">Enter the code sent to your email to continue setting up your account.</p>

        {error && <div className="rp-alert error">{error}</div>}

        <div className="rp-field">
          <label>Email</label>
          <input
            className="rp-input"
            type="email"
            placeholder="you@lgu.gov.ph"
            value={email}
            onChange={e => { setEmail(e.target.value); setError('') }}
            onKeyDown={handleKeyDown}
            autoFocus
          />
        </div>

        <div className="rp-field">
          <label>Verification Code</label>
          <input
            className="rp-input"
            type="text"
            inputMode="numeric"
            maxLength={6}
            placeholder="123456"
            value={code}
            onChange={e => { setCode(e.target.value.replace(/\D/g, '')); setError('') }}
            onKeyDown={handleKeyDown}
          />
        </div>

        <button className="rp-btn" onClick={handleSubmit} disabled={loading}>
          {loading ? 'Verifying…' : 'Continue'}
        </button>

        <button className="rp-link" type="button" onClick={handleResend} disabled={resendLoading}>
          {resendLoading ? 'Sending…' : "Didn't get a code? Resend"}
        </button>
        {resendMessage && <p style={{ textAlign: 'center', fontSize: '12.5px', color: '#4b5563', marginTop: '4px' }}>{resendMessage}</p>}

        <Link className="rp-link" to="/login">Back to login</Link>
      </div>
    </div>
  )
}

export default AdminSetup
