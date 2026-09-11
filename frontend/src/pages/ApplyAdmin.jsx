import { useState, useCallback, useEffect } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { API_BASE_URL, setSession } from '../api'
import { GraduationCapIcon } from '../components/NavIcons'
import adminBg from '../assets/admin-bg.jpg'

// Two ways to land here:
// - No token in the URL: the public, self-service "apply for admin access"
//   flow - fill in the full form (including your own email), then verify a
//   one-time code sent to that email before the request is actually
//   submitted for review.
// - A token in the URL: an existing admin already invited you directly and
//   chose your role/permissions - this is just the "set your password"
//   step, no review needed.
const css = `
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Playfair+Display:wght@700&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --brand:       #3d6fa3;
    --brand-light: #6fa0d4;
    --brand-dark:  #2c5580;
    --danger:      #E53E3E;
    --text-primary:   #1A1A2E;
    --text-secondary: #4b5563;
    --border:      #E5E7EB;
    --bg-card:     #FFFFFF;
    --bg-input:    #F9FAFB;
    --radius:      12px;
    --shadow-lg:   0 10px 40px rgba(61,111,163,.18);
    --transition:  .2s cubic-bezier(.4,0,.2,1);
  }

  body { font-family: 'DM Sans', sans-serif; }

  .lp-page {
    display: flex;
    min-height: 100vh;
    background: #eaf0f7 url(${adminBg}) center/cover no-repeat;
  }

  .lp-left {
    flex: 0 0 420px;
    background: linear-gradient(145deg, rgba(22,35,61,.72) 0%, rgba(61,111,163,.72) 50%, rgba(95,143,196,.68) 100%);
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 40px;
    position: relative;
    overflow: hidden;
  }

  .lp-left::before {
    content: '';
    position: absolute;
    inset: 0;
    background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.04'%3E%3Ccircle cx='30' cy='30' r='28'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E") repeat;
  }

  .lp-blob {
    position: absolute;
    border-radius: 50%;
    background: rgba(255,255,255,.07);
    animation: float 8s ease-in-out infinite;
  }
  .lp-blob.b1 { width:260px; height:260px; bottom:-60px; left:-60px; animation-delay:0s; }
  .lp-blob.b2 { width:180px; height:180px; top:40px;    right:-40px; animation-delay:3s; }
  .lp-blob.b3 { width:100px; height:100px; top:50%;     left:20%;    animation-delay:5s; }

  @keyframes float {
    0%,100% { transform: translateY(0) scale(1); }
    50%      { transform: translateY(-20px) scale(1.04); }
  }

  .lp-brand { position: relative; z-index: 1; text-align: center; }

  .lp-logo-ring {
    width: 80px; height: 80px;
    border-radius: 24px;
    background: rgba(255,255,255,.15);
    backdrop-filter: blur(12px);
    border: 1.5px solid rgba(255,255,255,.25);
    display: flex; align-items: center; justify-content: center;
    margin: 0 auto 20px;
    color: #fff;
    box-shadow: 0 8px 32px rgba(0,0,0,.2);
  }

  .lp-name {
    font-family: 'Playfair Display', serif;
    font-size: 36px;
    color: #fff;
    letter-spacing: -0.5px;
    margin-bottom: 8px;
  }

  .lp-tagline {
    font-size: 13px;
    color: rgba(255,255,255,.7);
    line-height: 1.6;
    max-width: 260px;
    margin: 0 auto 40px;
  }

  .lp-quote {
    background: rgba(255,255,255,.1);
    border: 1px solid rgba(255,255,255,.18);
    border-radius: 14px;
    padding: 20px 24px;
    color: rgba(255,255,255,.9);
    font-size: 14px;
    line-height: 1.65;
    font-style: italic;
    max-width: 320px;
    text-align: center;
    position: relative; z-index: 1;
  }

  .lp-right {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px 24px;
    overflow-y: auto;
  }

  .lp-card {
    background: rgba(255,255,255,.86);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,.5);
    border-radius: 20px;
    padding: 40px 44px;
    width: 100%;
    max-width: 460px;
    box-shadow: var(--shadow-lg);
    animation: slideUp .4s ease;
  }

  @keyframes slideUp {
    from { opacity:0; transform: translateY(18px); }
    to   { opacity:1; transform: translateY(0); }
  }

  .lp-mobile-logo {
    display: none;
    align-items: center;
    gap: 10px;
    font-family: 'Playfair Display', serif;
    font-size: 22px;
    color: var(--brand);
    margin-bottom: 24px;
  }

  .lp-title {
    font-family: 'Playfair Display', serif;
    font-size: 26px;
    color: var(--text-primary);
    margin-bottom: 4px;
  }

  .lp-sub {
    font-size: 14px;
    color: var(--text-secondary);
    margin-bottom: 24px;
  }

  .lp-alert {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13.5px;
    font-weight: 500;
    margin-bottom: 16px;
    animation: shake .35s ease;
  }

  .lp-alert.error { background: #FEF2F2; color: var(--danger); border: 1px solid #FECACA; }

  @keyframes shake {
    0%,100% { transform: translateX(0); }
    20%,60% { transform: translateX(-4px); }
    40%,80% { transform: translateX(4px); }
  }

  select.lp-input { cursor: pointer; }

  .lp-field { margin-bottom: 16px; }

  .lp-field label {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 6px;
    letter-spacing: .02em;
  }

  .lp-input {
    width: 100%;
    padding: 11px 16px;
    border: 1.5px solid var(--border);
    border-radius: var(--radius);
    background: var(--bg-input);
    font-family: 'DM Sans', sans-serif;
    font-size: 14px;
    color: var(--text-primary);
    transition: border-color var(--transition), box-shadow var(--transition);
    outline: none;
  }

  .lp-input::placeholder { color: #4b5563; }

  .lp-input:focus {
    border-color: var(--brand);
    box-shadow: 0 0 0 3px rgba(61,111,163,.12);
    background: #fff;
  }

  .lp-link {
    background: none; border: none;
    font-family: 'DM Sans', sans-serif;
    font-size: 13px;
    color: var(--brand);
    cursor: pointer;
    font-weight: 500;
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .lp-btn {
    width: 100%;
    padding: 13px;
    border: none;
    border-radius: var(--radius);
    background: linear-gradient(135deg, var(--brand) 0%, var(--brand-light) 100%);
    color: #fff;
    font-family: 'DM Sans', sans-serif;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity var(--transition), transform var(--transition), box-shadow var(--transition);
    letter-spacing: .02em;
    box-shadow: 0 4px 14px rgba(61,111,163,.35);
    display: flex; align-items: center; justify-content: center; gap: 8px;
  }

  .lp-btn:hover:not(:disabled) {
    opacity: .92;
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(61,111,163,.4);
  }

  .lp-btn:active:not(:disabled) { transform: translateY(0); }
  .lp-btn:disabled { opacity: .65; cursor: not-allowed; transform: none; }

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
  @keyframes spin { to { transform: rotate(360deg); } }

  .lp-success-box {
    text-align: center;
    padding: 20px 0;
  }

  .lp-success-box h2 {
    font-family: 'Playfair Display', serif;
    font-size: 24px;
    color: var(--text-primary);
    margin-bottom: 8px;
  }

  .lp-success-box p {
    font-size: 14px;
    color: var(--text-secondary);
    margin-bottom: 28px;
  }

  @media (max-width: 768px) {
    .lp-left { display: none; }
    .lp-mobile-logo { display: flex; }
    .lp-card { padding: 28px 24px; box-shadow: none; border-radius: 16px; }
    .lp-right { padding: 24px 16px; background: rgba(234,240,247,.55); align-items: flex-start; padding-top: 40px; }
  }
`

// Municipalities currently served - keep in sync with the list in Login.jsx.
const ADDRESS_CITIES = [
  { city: 'Liliw', province: 'Laguna' },
  { city: 'Tiaong', province: 'Quezon' },
]

const EMPTY_ADMIN_REQUEST = {
  orgMode: 'join', joinCode: '', orgName: '',
  fullName: '', email: '', password: '', confirmPassword: '',
  municipality: '', contactNumber: '', message: '',
}

function ApplyAdmin() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') || ''

  if (token) return <InviteSetup token={token} />
  return <ApplyForm />
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

// ── APPLY MODE: public self-service request. Choose join-vs-create first,
// fill in the complete form (including your own email), then verify a
// one-time code sent to that email as the final step before the request is
// actually submitted for review. ──
function ApplyForm() {
  // 'form' | 'otp' | 'success'
  const [step, setStep] = useState('form')

  const [data, setData] = useState(EMPTY_ADMIN_REQUEST)
  const [proofFile, setProofFile] = useState(null)
  const [formError, setFormError] = useState('')
  const [sendingCode, setSendingCode] = useState(false)

  const [joinCodeOrgName, setJoinCodeOrgName] = useState('')
  const [joinCodeChecking, setJoinCodeChecking] = useState(false)
  const [joinCodeError, setJoinCodeError] = useState('')

  const [otpCode, setOtpCode] = useState('')
  const [otpError, setOtpError] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [resendMessage, setResendMessage] = useState('')
  const [resendLoading, setResendLoading] = useState(false)

  const handleJoinCodeBlur = useCallback(async () => {
    const code = data.joinCode.trim().toUpperCase()
    setJoinCodeOrgName('')
    setJoinCodeError('')
    if (!code) return

    setJoinCodeChecking(true)
    try {
      const res = await fetch(`${API_BASE_URL}/api/organizations/lookup?code=${encodeURIComponent(code)}`)
      const result = await res.json()
      if (!res.ok) {
        setJoinCodeError(result.error || 'This join code could not be verified. Confirm it with your LGU and try again.')
        return
      }
      setJoinCodeOrgName(result.organization.name)
    } catch {
      setJoinCodeError('Unable to reach the server. Please try again.')
    } finally {
      setJoinCodeChecking(false)
    }
  }, [data.joinCode])

  const validateForm = () => {
    const { fullName, email, password, confirmPassword, municipality, contactNumber } = data
    if (!fullName.trim())      return 'Full name is required'
    if (!email.trim())         return 'Email address is required'
    if (!/\S+@\S+\.\S+/.test(email)) return 'Enter a valid email address'
    if (!password)             return 'Password is required'
    if (password.length < 8)   return 'Password must be at least 8 characters'
    if (password !== confirmPassword) return 'Passwords do not match'
    if (!municipality)         return 'Municipality is required'
    if (!contactNumber.trim()) return 'Contact number is required'
    if (!/^09\d{9}$/.test(contactNumber.replace(/\s/g, ''))) return 'Enter a valid Philippine mobile number'
    if (data.orgMode === 'create') {
      if (!data.orgName.trim()) return 'Organization name is required'
    } else if (!data.joinCode.trim()) {
      return 'A valid LGU join code is required'
    }
    if (!proofFile) return 'A valid identification or proof-of-employment document is required'
    return ''
  }

  const handleSendCode = useCallback(async () => {
    setFormError('')
    const validationError = validateForm()
    if (validationError) { setFormError(validationError); return }

    setSendingCode(true)
    try {
      await fetch(`${API_BASE_URL}/api/admin-requests/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: data.email.trim().toLowerCase() })
      })
      setStep('otp')
    } catch {
      setFormError('Unable to reach the server. Please try again.')
    } finally {
      setSendingCode(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, proofFile])

  const handleResendCode = useCallback(async () => {
    setResendMessage('')
    setResendLoading(true)
    try {
      await fetch(`${API_BASE_URL}/api/admin-requests/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: data.email.trim().toLowerCase() })
      })
      setResendMessage('A new verification code has been sent to your email.')
    } catch {
      setResendMessage('Unable to reach the server. Please try again.')
    } finally {
      setResendLoading(false)
    }
  }, [data.email])

  const handleVerifyAndSubmit = useCallback(async () => {
    setOtpError('')
    if (!otpCode.trim()) { setOtpError('Enter the verification code sent to your email'); return }

    setVerifying(true)
    try {
      const verifyRes = await fetch(`${API_BASE_URL}/api/admin-requests/verify-start-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: data.email.trim().toLowerCase(), code: otpCode.trim() })
      })
      const verifyResult = await verifyRes.json()
      if (!verifyRes.ok) {
        setOtpError(verifyResult.error || 'Verification failed. Please try again.')
        return
      }

      const formData = new FormData()
      formData.append('token', verifyResult.token)
      formData.append('full_name', data.fullName.trim())
      formData.append('password', data.password)
      formData.append('municipality', data.municipality)
      formData.append('contact_number', data.contactNumber.trim())
      formData.append('message', data.message.trim())
      formData.append('file', proofFile)
      formData.append('org_mode', data.orgMode)
      if (data.orgMode === 'create') {
        formData.append('org_name', data.orgName.trim())
      } else {
        formData.append('join_code', data.joinCode.trim().toUpperCase())
      }

      const submitRes = await fetch(`${API_BASE_URL}/api/admin-requests`, { method: 'POST', body: formData })
      const submitResult = await submitRes.json()
      if (!submitRes.ok) {
        setOtpError(submitResult.error || 'Unable to submit your request. Please try again.')
        return
      }

      setStep('success')
    } catch {
      setOtpError('Unable to reach the server. Please try again.')
    } finally {
      setVerifying(false)
    }
  }, [otpCode, data, proofFile])

  const handleFormKeyDown = (e) => { if (e.key === 'Enter') handleSendCode() }
  const handleOtpKeyDown = (e) => { if (e.key === 'Enter') handleVerifyAndSubmit() }

  if (step === 'success') {
    return (
      <ApplyAdminShell>
        <div className="lp-success-box">
          <h2>Request Submitted</h2>
          <p>
            Thank you — an existing administrator will review your details.
            Once approved, you can sign in at <strong>{data.email}</strong> with
            the password you set.
          </p>
          <Link className="lp-btn" to="/login" style={{ textDecoration: 'none', display: 'flex' }}>
            Return to Sign In
          </Link>
        </div>
      </ApplyAdminShell>
    )
  }

  if (step === 'otp') {
    return (
      <ApplyAdminShell>
        <h2 className="lp-title">Verify Your Email</h2>
        <p className="lp-sub">
          Enter the verification code sent to <strong>{data.email}</strong> to submit your request.
        </p>

        {otpError && <div className="lp-alert error">{otpError}</div>}

        <div className="lp-field">
          <label>Verification Code</label>
          <input
            className="lp-input"
            type="text"
            inputMode="numeric"
            maxLength={6}
            placeholder="Enter verification code"
            value={otpCode}
            onChange={e => { setOtpCode(e.target.value.replace(/\D/g, '')); setOtpError('') }}
            onKeyDown={handleOtpKeyDown}
            autoFocus
          />
        </div>

        <button className="lp-btn" onClick={handleVerifyAndSubmit} disabled={verifying}>
          {verifying ? <><span className="spinner" /> Submitting…</> : 'Verify and Submit Request'}
        </button>

        <p style={{ marginTop: '16px', textAlign: 'center', fontSize: '13.5px', color: 'var(--text-secondary)' }}>
          Did not receive a code?{' '}
          <button className="lp-link" type="button" onClick={handleResendCode} disabled={resendLoading}>
            {resendLoading ? 'Sending…' : 'Resend code'}
          </button>
        </p>
        {resendMessage && <p style={{ textAlign: 'center', fontSize: '13px', color: 'var(--text-secondary)' }}>{resendMessage}</p>}

        <button className="lp-btn lp-btn-secondary" type="button" onClick={() => setStep('form')} disabled={verifying}>
          Return to the form
        </button>
      </ApplyAdminShell>
    )
  }

  return (
    <ApplyAdminShell>
      <h2 className="lp-title">Apply as Admin</h2>
      <p className="lp-sub">Complete the form below to request administrator access.</p>

      {formError && <div className="lp-alert error">{formError}</div>}

      <div className="lp-field">
        <label>Your LGU</label>
        <div style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
          <button
            type="button"
            className="lp-btn"
            style={{
              flex: 1, background: data.orgMode === 'join' ? undefined : '#F3F4F6',
              color: data.orgMode === 'join' ? undefined : 'var(--text-secondary)',
              boxShadow: data.orgMode === 'join' ? undefined : 'none',
            }}
            onClick={() => { setData(p => ({ ...p, orgMode: 'join' })); setFormError('') }}
          >
            Join an Existing Organization
          </button>
          <button
            type="button"
            className="lp-btn"
            style={{
              flex: 1, background: data.orgMode === 'create' ? undefined : '#F3F4F6',
              color: data.orgMode === 'create' ? undefined : 'var(--text-secondary)',
              boxShadow: data.orgMode === 'create' ? undefined : 'none',
            }}
            onClick={() => { setData(p => ({ ...p, orgMode: 'create' })); setFormError('') }}
          >
            Create a New Organization
          </button>
        </div>

        {data.orgMode === 'join' ? (
          <>
            <input
              className="lp-input"
              type="text"
              placeholder="Enter your LGU join code"
              value={data.joinCode}
              onChange={e => { setData(p => ({ ...p, joinCode: e.target.value })); setFormError(''); setJoinCodeOrgName(''); setJoinCodeError('') }}
              onBlur={handleJoinCodeBlur}
              onKeyDown={handleFormKeyDown}
            />
            {joinCodeChecking && <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>Checking code…</p>}
            {!joinCodeChecking && joinCodeOrgName && (
              <p style={{ fontSize: '12px', color: '#16a34a', marginTop: '4px' }}>Joining {joinCodeOrgName}</p>
            )}
            {!joinCodeChecking && joinCodeError && (
              <p style={{ fontSize: '12px', color: 'var(--danger)', marginTop: '4px' }}>{joinCodeError}</p>
            )}
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>Request this code from your LGU's administrator.</p>
          </>
        ) : (
          <>
            <input
              className="lp-input"
              type="text"
              placeholder="Enter your organization's official name"
              value={data.orgName}
              onChange={e => { setData(p => ({ ...p, orgName: e.target.value })); setFormError('') }}
              onKeyDown={handleFormKeyDown}
            />
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
              A new organization has no existing team to review this request, so it will instead be reviewed by the platform's Super Admin. Once approved, you will receive a join code to share with your team.
            </p>
          </>
        )}
      </div>

      <div className="lp-field">
        <label>Full Name</label>
        <input
          className="lp-input"
          type="text"
          placeholder="Enter your full name"
          value={data.fullName}
          autoComplete="name"
          onChange={e => { setData(p => ({ ...p, fullName: e.target.value })); setFormError('') }}
          onKeyDown={handleFormKeyDown}
        />
      </div>

      <div className="lp-field">
        <label>Email Address</label>
        <input
          className="lp-input"
          type="email"
          placeholder="Enter your official email address"
          value={data.email}
          autoComplete="email"
          onChange={e => { setData(p => ({ ...p, email: e.target.value })); setFormError('') }}
          onKeyDown={handleFormKeyDown}
        />
      </div>

      <div className="lp-field">
        <label>Password</label>
        <input
          className="lp-input"
          type="password"
          placeholder="Enter a password with at least 8 characters"
          value={data.password}
          autoComplete="new-password"
          onChange={e => { setData(p => ({ ...p, password: e.target.value })); setFormError('') }}
          onKeyDown={handleFormKeyDown}
        />
      </div>

      <div className="lp-field">
        <label>Confirm Password</label>
        <input
          className="lp-input"
          type="password"
          placeholder="Re-enter your password"
          value={data.confirmPassword}
          autoComplete="new-password"
          onChange={e => { setData(p => ({ ...p, confirmPassword: e.target.value })); setFormError('') }}
          onKeyDown={handleFormKeyDown}
        />
        {data.confirmPassword && data.confirmPassword !== data.password && (
          <p style={{ fontSize: '12px', color: 'var(--danger)', marginTop: '4px' }}>Passwords do not match</p>
        )}
      </div>

      <div className="lp-field">
        <label>Municipality</label>
        <select
          className="lp-input"
          value={data.municipality}
          onChange={e => { setData(p => ({ ...p, municipality: e.target.value })); setFormError('') }}>
          <option value="">Select your city or municipality</option>
          {ADDRESS_CITIES.map(c => (
            <option key={c.city} value={c.city}>{c.city}, {c.province}</option>
          ))}
        </select>
      </div>

      <div className="lp-field">
        <label>Contact Number</label>
        <input
          className="lp-input"
          type="text"
          placeholder="Enter your contact number"
          value={data.contactNumber}
          onChange={e => { setData(p => ({ ...p, contactNumber: e.target.value })); setFormError('') }}
          onKeyDown={handleFormKeyDown}
        />
      </div>

      <div className="lp-field">
        <label>Reason for Request <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}>(optional)</span></label>
        <textarea
          className="lp-input"
          rows={3}
          placeholder="State the reason for your admin access request"
          value={data.message}
          onChange={e => { setData(p => ({ ...p, message: e.target.value })); setFormError('') }}
        />
      </div>

      <div className="lp-field">
        <label>Valid ID or Proof of Employment</label>
        <p style={{ fontSize: '12.5px', color: 'var(--text-secondary)', margin: '-2px 0 8px' }}>
          Submit an appointment letter, employee identification, or contract of service (COS) - PDF, JPG, or PNG, up to 5MB.
          This document will be reviewed by an administrator before your request is approved.
        </p>
        <input
          className="lp-input"
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
          onChange={e => { setProofFile(e.target.files[0] || null); setFormError('') }}
        />
        {proofFile && (
          <p style={{ fontSize: '12.5px', color: 'var(--brand)', marginTop: '6px' }}>
            Selected file: {proofFile.name}
          </p>
        )}
      </div>

      <button className="lp-btn" onClick={handleSendCode} disabled={sendingCode}>
        {sendingCode ? <><span className="spinner" /> Sending Code…</> : 'Send Verification Code'}
      </button>

      <p style={{ marginTop: '16px', textAlign: 'center', fontSize: '13.5px', color: 'var(--text-secondary)' }}>
        Already have an account?{' '}
        <Link className="lp-link" to="/login">Sign in here</Link>
      </p>
    </ApplyAdminShell>
  )
}

function ApplyAdminShell({ children }) {
  return (
    <>
      <style>{css}</style>
      <div className="lp-page">

        <div className="lp-left">
          <div className="lp-blob b1" />
          <div className="lp-blob b2" />
          <div className="lp-blob b3" />
          <div className="lp-brand">
            <div className="lp-logo-ring">
              <GraduationCapIcon width={40} height={40} />
            </div>
            <h1 className="lp-name">EcoScholar</h1>
            <p className="lp-tagline">
              Centralized Scholarship Allocation System
            </p>
          </div>
          <div className="lp-quote">
            "Empowering students through fair and transparent scholarship distribution."
          </div>
        </div>

        <div className="lp-right">
          <div className="lp-card">
            <div className="lp-mobile-logo">
              <GraduationCapIcon width={24} height={24} />
              <span>EcoScholar</span>
            </div>
            {children}
          </div>
        </div>

      </div>
    </>
  )
}

export default ApplyAdmin
