import { useState, useCallback } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { API_BASE_URL, fetchWithTimeout, connectionErrorMessage } from '../api'
import AuthShell from '../components/AuthShell'


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
      const res = await fetchWithTimeout(`${API_BASE_URL}/api/reset-password`, {
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
      setError(connectionErrorMessage())
    }
    setLoading(false)
  }, [token, newPassword, confirmPassword])

  return (
    <AuthShell>
        {!token ? (
          <>
            <h2 className="lp-title">Invalid link</h2>
            <p className="lp-sub">This password reset link is missing its token. Request a new one from the login page.</p>
            <Link className="lp-link lp-center-link" to="/login">Back to login</Link>
          </>
        ) : success ? (
          <>
            <h2 className="lp-title">Password reset</h2>
            <p className="lp-sub">Your password has been changed. You can now log in with your new password.</p>
            <button className="lp-btn" onClick={() => navigate('/login')}>Go to login</button>
          </>
        ) : (
          <>
            <h2 className="lp-title">Set a new password</h2>
            <p className="lp-sub">Choose a new password for your account. This link expires 30 minutes after it was sent.</p>

            {error && <div className="lp-alert error">{error}</div>}

            <div className="lp-field">
              <label>New password</label>
              <input
                className="lp-input"
                type="password"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                autoFocus
              />
            </div>
            <div className="lp-field">
              <label>Confirm new password</label>
              <input
                className="lp-input"
                type="password"
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              />
            </div>

            <button className="lp-btn" onClick={handleSubmit} disabled={loading}>
              {loading ? 'Resetting…' : 'Reset password'}
            </button>
            <Link className="lp-link lp-center-link" to="/login">Back to login</Link>
          </>
        )}
    </AuthShell>
  )
}

export default ResetPassword
