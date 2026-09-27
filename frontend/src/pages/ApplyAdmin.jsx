import { useState, useCallback, useEffect } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { GoogleLogin } from '@react-oauth/google'
import { API_BASE_URL, setSession } from '../api'
import AuthShell from '../components/AuthShell'

// Two ways to land here:
// - No token in the URL: the public, self-service "apply for admin access"
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
  const [privacyConsent, setPrivacyConsent] = useState(false)

  // Set once "Continue with Google" verifies the applicant's email - full
  // name/email come from Google (locked, no password needed) and the
  // admin_apply token is already in hand, so submission skips the OTP step.
  const [googleVerified, setGoogleVerified] = useState(false)
  const [googleToken, setGoogleToken] = useState('')

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

  // Whether "Your LGU" (join vs. create - i.e. lgu_member vs. lgu_admin/
  // founding) is filled in enough to know which request is being made,
  // before Google is even offered as an option.
  const orgInfoComplete = data.orgMode === 'create'
    ? !!(data.orgName.trim() && data.municipality)
    : !!data.joinCode.trim()

  const validateForm = () => {
    const { fullName, email, password, confirmPassword, municipality, contactNumber } = data
    if (!fullName.trim())      return 'Full name is required'
    if (!email.trim())         return 'Email address is required'
    if (!/\S+@\S+\.\S+/.test(email)) return 'Enter a valid email address'
    if (!password)             return 'Password is required'
    if (password.length < 8)   return 'Password must be at least 8 characters'
    if (password !== confirmPassword) return 'Passwords do not match'
    if (!contactNumber.trim()) return 'Contact number is required'
    if (!/^09\d{9}$/.test(contactNumber.replace(/\s/g, ''))) return 'Enter a valid Philippine mobile number'
    if (data.orgMode === 'create') {
      if (!data.orgName.trim()) return 'Organization name is required'
      // Only asked once, when founding a brand-new organization - anyone
      // joining an existing one inherits its municipality automatically.
      if (!municipality) return 'Municipality is required'
    } else if (!data.joinCode.trim()) {
      return 'A valid LGU join code is required'
    }
    if (!proofFile) return 'A valid identification or proof-of-employment document is required'
    if (!privacyConsent) return 'You must agree to the Data Privacy Act to submit a request'
    return ''
  }

  // Google already supplied full name + email and needs no password - only
  // the LGU/org choice, contact number, and proof file still matter here.
  const validateFormForGoogle = () => {
    const { contactNumber, municipality } = data
    if (!contactNumber.trim()) return 'Contact number is required'
    if (!/^09\d{9}$/.test(contactNumber.replace(/\s/g, ''))) return 'Enter a valid Philippine mobile number'
    if (data.orgMode === 'create') {
      if (!data.orgName.trim()) return 'Organization name is required'
      if (!municipality) return 'Municipality is required'
    } else if (!data.joinCode.trim()) {
      return 'A valid LGU join code is required'
    }
    if (!proofFile) return 'A valid identification or proof-of-employment document is required'
    if (!privacyConsent) return 'You must agree to the Data Privacy Act to submit a request'
    return ''
  }

  // Shared by both the password+OTP path and the Google path - only the
  // token that proves the email differs between them.
  const submitAdminRequest = useCallback(async (token) => {
    const formData = new FormData()
    formData.append('token', token)
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
    const res = await fetch(`${API_BASE_URL}/api/admin-requests`, { method: 'POST', body: formData })
    const result = await res.json()
    return { ok: res.ok, result }
  }, [data, proofFile])

  // ── CONTINUE WITH GOOGLE ── (verifies the email up front, no OTP needed)
  const handleGoogleStart = useCallback(async (credentialResponse) => {
    setFormError('')
    if (!orgInfoComplete) { setFormError('Choose an LGU (join or create) above first'); return }
    if (!privacyConsent) { setFormError('You must agree to the Data Privacy Act to continue'); return }
    if (!credentialResponse.credential) { setFormError('Google sign-in failed. Please try again.'); return }

    setSendingCode(true)
    try {
      const res = await fetch(`${API_BASE_URL}/api/admin-requests/start-google`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential: credentialResponse.credential })
      })
      const result = await res.json()
      if (!res.ok) {
        setFormError(result.error || 'Could not verify your Google account. Please try again.')
        return
      }
      setData(p => ({ ...p, fullName: result.full_name || p.fullName, email: result.email, password: '', confirmPassword: '' }))
      setGoogleToken(result.token)
      setGoogleVerified(true)
    } catch {
      setFormError('Unable to reach the server. Please try again.')
    } finally {
      setSendingCode(false)
    }
  }, [orgInfoComplete, privacyConsent])

  const handleSubmitWithGoogle = useCallback(async () => {
    setFormError('')
    const validationError = validateFormForGoogle()
    if (validationError) { setFormError(validationError); return }

    setSendingCode(true)
    try {
      const { ok, result } = await submitAdminRequest(googleToken)
      if (!ok) { setFormError(result.error || 'Unable to submit your request. Please try again.'); return }
      setStep('success')
    } catch {
      setFormError('Unable to reach the server. Please try again.')
    } finally {
      setSendingCode(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, proofFile, googleToken, submitAdminRequest])

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

      const { ok, result } = await submitAdminRequest(verifyResult.token)
      if (!ok) {
        setOtpError(result.error || 'Unable to submit your request. Please try again.')
        return
      }

      setStep('success')
    } catch {
      setOtpError('Unable to reach the server. Please try again.')
    } finally {
      setVerifying(false)
    }
  }, [otpCode, data.email, submitAdminRequest])

  const handleFormKeyDown = (e) => { if (e.key === 'Enter') (googleVerified ? handleSubmitWithGoogle() : handleSendCode()) }
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
        <div className="lp-seg">
          <button
            type="button"
            className={`lp-seg-btn${data.orgMode === 'join' ? ' active' : ''}`}
            onClick={() => { setData(p => ({ ...p, orgMode: 'join' })); setFormError('') }}
          >
            Join an Existing Organization
          </button>
          <button
            type="button"
            className={`lp-seg-btn${data.orgMode === 'create' ? ' active' : ''}`}
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
            <select
              className="lp-input"
              style={{ marginTop: '10px' }}
              value={data.municipality}
              onChange={e => { setData(p => ({ ...p, municipality: e.target.value })); setFormError('') }}>
              <option value="">Select your city or municipality</option>
              {ADDRESS_CITIES.map(c => (
                <option key={c.city} value={c.city}>{c.city}, {c.province}</option>
              ))}
            </select>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
              This becomes your new organization's municipality - everyone who later joins it inherits this automatically.
            </p>
          </>
        )}
      </div>

      <div className="lp-field">
        <label style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '10px',
          cursor: 'pointer',
          fontWeight: '400',
          fontSize: '13px',
          color: 'var(--text-secondary)',
          lineHeight: '1.6'
        }}>
          <input
            type="checkbox"
            checked={privacyConsent}
            onChange={e => { setPrivacyConsent(e.target.checked); setFormError('') }}
            style={{ marginTop: '3px', flexShrink: 0, accentColor: 'var(--brand)' }}
          />
          <span>
            I consent to the collection and processing of my personal data
            in accordance with the{' '}
            <strong>Data Privacy Act of 2012 (RA 10173)</strong>.
            My information will only be used for evaluating this request.
          </span>
        </label>
      </div>

      {googleVerified ? (
        <div className="lp-field">
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            Continuing as <strong>{data.fullName}</strong> ({data.email}) via Google.{' '}
            <button className="lp-link" type="button" onClick={() => {
              setGoogleVerified(false); setGoogleToken(''); setFormError('')
              setData(p => ({ ...p, fullName: '', email: '' }))
            }}>
              Use a different method
            </button>
          </p>
        </div>
      ) : orgInfoComplete && privacyConsent ? (
        <>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <GoogleLogin
              onSuccess={handleGoogleStart}
              onError={() => setFormError('Google sign-in failed. Please try again.')}
              text="continue_with"
            />
          </div>
          <div className="lp-or">or fill in the rest yourself</div>
        </>
      ) : (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
            <button type="button" disabled className="lp-btn" style={{ opacity: .5, cursor: 'not-allowed', width: '250px' }}>
              Continue with Google
            </button>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', textAlign: 'center' }}>
              {!orgInfoComplete
                ? (data.orgMode === 'create' ? 'Fill in your organization\'s name and municipality above first' : 'Enter your LGU join code above first')
                : 'Agree to the Data Privacy Act above first'}
            </p>
          </div>
          <div className="lp-or">or fill in the rest yourself</div>
        </>
      )}

      {!googleVerified && (
        <>
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
        </>
      )}

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
        <label htmlFor="proofFile">Valid ID or Proof of Employment</label>
        <p style={{ fontSize: '12.5px', color: 'var(--text-secondary)', margin: '-2px 0 8px' }}>
          Submit an appointment letter, employee identification, or contract of service (COS) - PDF, JPG, or PNG, up to 5MB.
          This document will be reviewed by an administrator before your request is approved.
        </p>
        <label className="lp-file-upload" htmlFor="proofFile">
          <input
            id="proofFile"
            className="lp-file-upload-input"
            type="file"
            accept=".pdf,.jpg,.jpeg,.png"
            onChange={e => { setProofFile(e.target.files[0] || null); setFormError('') }}
          />
          <span className="lp-file-upload-icon" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </span>
          <span className={`lp-file-upload-text${proofFile ? ' has-file' : ''}`}>
            {proofFile ? proofFile.name : 'No file chosen'}
          </span>
          <span className="lp-file-upload-btn">Browse</span>
        </label>
      </div>

      {googleVerified ? (
        <button className="lp-btn" onClick={handleSubmitWithGoogle} disabled={sendingCode}>
          {sendingCode ? <><span className="spinner" /> Submitting…</> : 'Submit Request'}
        </button>
      ) : (
        <button className="lp-btn" onClick={handleSendCode} disabled={sendingCode}>
          {sendingCode ? <><span className="spinner" /> Sending Code…</> : 'Send Verification Code'}
        </button>
      )}

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
      <AuthShell>{children}</AuthShell>
    </>
  )
}

export default ApplyAdmin
