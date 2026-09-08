import { useState, useCallback } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { API_BASE_URL } from '../api'

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
  .rp-sub { font-size: 14px; color: #6B7280; margin-bottom: 24px; line-height: 1.5; }
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
  .rp-alert.success { background: #DCFCE7; color: #166534; }
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
  .rp-link { display: block; text-align: center; margin-top: 18px; font-size: 13px; color: #3d6fa3; text-decoration: none; font-weight: 600; }
`

function ResetPassword() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''

  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)

  const handleSubmit = useCallback(async () => {
    setError('')
    if (!newPassword || !confirmPassword) { setError('Both fields are required'); return }
    if (newPassword.length < 8) { setError('Password must be at least 8 characters'); return }
    if (newPassword !== confirmPassword) { setError('Passwords do not match'); return }

    setLoading(true)
    try {
      const res = await fetch(`${API_BASE_URL}/api/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: newPassword })
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.error || 'Something went wrong. Please try again.')
      } else {
        setSuccess(true)
      }
    } catch {
      setError('Cannot connect to server. Please try again.')
    }
    setLoading(false)
  }, [token, newPassword, confirmPassword])

  return (
    <div className="rp-page">
      <style>{css}</style>
      <div className="rp-card">
        {!token ? (
          <>
            <p className="rp-title">Invalid link</p>
            <p className="rp-sub">This password reset link is missing its token. Request a new one from the login page.</p>
            <Link className="rp-link" to="/login">Back to login</Link>
          </>
        ) : success ? (
          <>
            <p className="rp-title">Password reset</p>
            <p className="rp-sub">Your password has been changed. You can now log in with your new password.</p>
            <button className="rp-btn" onClick={() => navigate('/login')}>Go to login</button>
          </>
        ) : (
          <>
            <p className="rp-title">Set a new password</p>
            <p className="rp-sub">Choose a new password for your account. This link expires 30 minutes after it was sent.</p>

            {error && <div className="rp-alert error">{error}</div>}

            <div className="rp-field">
              <label>New password</label>
              <input
                className="rp-input"
                type="password"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                autoFocus
              />
            </div>
            <div className="rp-field">
              <label>Confirm new password</label>
              <input
                className="rp-input"
                type="password"
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              />
            </div>

            <button className="rp-btn" onClick={handleSubmit} disabled={loading}>
              {loading ? 'Resetting…' : 'Reset password'}
            </button>
            <Link className="rp-link" to="/login">Back to login</Link>
          </>
        )}
      </div>
    </div>
  )
}

export default ResetPassword
