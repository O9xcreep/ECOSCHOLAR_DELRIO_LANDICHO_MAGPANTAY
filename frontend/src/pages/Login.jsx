import { useState, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { GoogleLogin } from '@react-oauth/google'
import { API_BASE_URL, setSession, fetchWithTimeout, connectionErrorMessage } from '../api'
import AuthShell from '../components/AuthShell'


/* ── SVG Icons ── */
const EyeIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
    <circle cx="12" cy="12" r="3"/>
  </svg>
)
const EyeOffIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/>
    <path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/>
    <line x1="1" y1="1" x2="23" y2="23"/>
  </svg>
)

const ArrowRightIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <line x1="5" y1="12" x2="19" y2="12"/>
    <polyline points="12 5 19 12 12 19"/>
  </svg>
)

/* ── Password Strength ── */
function getStrength(pw) {
  let score = 0
  if (pw.length >= 6) score++
  if (pw.length >= 10) score++
  if (/[A-Z]/.test(pw) && /[0-9]/.test(pw)) score++
  return score // 0 = none, 1 = weak, 2 = fair, 3 = strong
}

const EMPTY_REG_DATA = {
  join_code: '',
  lastName: '', firstName: '', middleName: '', email: '', password: '', confirm_password: '',
}

function PasswordStrength({ password }) {
  if (!password) return null
  const score = getStrength(password)
  const labels = ['', 'Weak', 'Fair', 'Strong']
  const cls = ['', 'weak', 'fair', 'strong']
  return (
    <div className="pw-strength">
      <div className="pw-bars">
        {[1, 2, 3].map(i => (
          <div key={i} className={`pw-bar ${score >= i ? cls[score] : ''}`} />
        ))}
      </div>
      <span className="pw-label">{score > 0 ? labels[score] : ''}</span>
    </div>
  )
}

function Login() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('login')

  // ── LOGIN ──
  const [loginData, setLoginData] = useState({ email: '', password: '' })
  const [showPw, setShowPw] = useState(false)
  const [loginError, setLoginError] = useState('')
  const [loginLoading, setLoginLoading] = useState(false)

  // ── REGISTER ──
  const [regStep, setRegStep] = useState(1)
  const [regData, setRegData] = useState(EMPTY_REG_DATA)
  const [showRegPw, setShowRegPw] = useState(false)
  const [showConfirmPw, setShowConfirmPw] = useState(false)
  const [regError, setRegError] = useState('')
  const [regLoading, setRegLoading] = useState(false)
  const [privacyConsent, setPrivacyConsent] = useState(false)
  const [joinCodeOrgName, setJoinCodeOrgName] = useState('')
  const [joinCodeChecking, setJoinCodeChecking] = useState(false)
  const [joinCodeError, setJoinCodeError] = useState('')

  // ── REGISTER: EMAIL VERIFICATION (step 2) ──
  const [regOtpCode, setRegOtpCode] = useState('')
  const [regOtpError, setRegOtpError] = useState('')
  const [regOtpLoading, setRegOtpLoading] = useState(false)
  const [regResendMessage, setRegResendMessage] = useState('')
  const [regResendLoading, setRegResendLoading] = useState(false)

  // ── FORGOT ──
  const [showForgot, setShowForgot] = useState(false)
  const [forgotEmail, setForgotEmail] = useState('')
  const [forgotError, setForgotError] = useState('')
  const [forgotSent, setForgotSent] = useState(false)
  const [forgotLoading, setForgotLoading] = useState(false)


 const switchTab = (t) => {
  setTab(t)
  setLoginError('')
  setRegError('')
  setPrivacyConsent(false)
  setRegStep(1)
  setRegOtpCode('')
  setRegOtpError('')
  setRegResendMessage('')
}

  // ── LOGIN HANDLER ──
  const handleLogin = useCallback(async () => {
    setLoginError('')
    const email = loginData.email.trim()
    const password = loginData.password

    if (!email)    { setLoginError('Email is required'); return }
    if (!/\S+@\S+\.\S+/.test(email)) { setLoginError('Enter a valid email address'); return }
    if (!password) { setLoginError('Password is required'); return }

    setLoginLoading(true)
    try {
      const res = await fetchWithTimeout(`${API_BASE_URL}/api/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      })

      let data
      try {
        data = await res.json()
      } catch {
        // The server answered, but not with JSON (e.g. a 502 page while Render restarts).
        setLoginError('The server had a problem. Please try again in a minute.')
        return
      }

      if (!res.ok) {
        if (data.needs_verification) {
          // Registered but never finished the emailed-code step - pick it back
          // up here with a fresh code instead of leaving them stuck.
          setRegData(p => ({ ...p, email: data.email || email }))
          setRegOtpCode('')
          setRegOtpError('')
          setRegResendMessage("Your email isn't verified yet, so we sent a new code.")
          setTab('register')
          setRegStep(2)
          fetchWithTimeout(`${API_BASE_URL}/api/register/resend-otp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: (data.email || email).toLowerCase() })
          }).catch(() => setRegResendMessage(connectionErrorMessage()))
          return
        }
        setLoginError(data.error || 'Invalid email or password')
        return
      }

      setSession(data.user, data.token)
      navigate(data.user.role === 'student' ? '/student/dashboard' : '/admin/dashboard')
    } catch {
      setLoginError(connectionErrorMessage())
    } finally {
      setLoginLoading(false)
    }
  }, [loginData, navigate])

  // ── LOGIN WITH GOOGLE ── (only ever signs in an existing account)
  const handleGoogleLoginSuccess = useCallback(async (credentialResponse) => {
    setLoginError('')
    if (!credentialResponse.credential) { setLoginError('Google sign-in failed. Please try again.'); return }

    setLoginLoading(true)
    try {
      const res = await fetchWithTimeout(`${API_BASE_URL}/api/login/google`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential: credentialResponse.credential })
      })
      const data = await res.json()

      if (!res.ok) {
        setLoginError(data.needs_registration
          ? 'No account found for this Google account. Create one below.'
          : (data.error || 'Could not sign in with Google.'))
        return
      }

      setSession(data.user, data.token)
      navigate(data.user.role === 'student' ? '/student/dashboard' : '/admin/dashboard')
    } catch {
      setLoginError(connectionErrorMessage())
    } finally {
      setLoginLoading(false)
    }
  }, [navigate])

  // ── REGISTER: LOOK UP LGU JOIN CODE ──
  const handleJoinCodeBlur = useCallback(async () => {
    const code = regData.join_code.trim().toUpperCase()
    setJoinCodeOrgName('')
    setJoinCodeError('')
    if (!code) return

    setJoinCodeChecking(true)
    try {
      const res = await fetchWithTimeout(`${API_BASE_URL}/api/organizations/lookup?code=${encodeURIComponent(code)}`)
      const data = await res.json()
      if (!res.ok) {
        setJoinCodeError(data.error || "That join code isn't valid. Check it with your LGU and try again.")
        return
      }
      setJoinCodeOrgName(data.organization.name)
    } catch {
      setJoinCodeError(connectionErrorMessage())
    } finally {
      setJoinCodeChecking(false)
    }
  }, [regData.join_code])

  // ── REGISTER SUBMIT (account info -> emailed OTP) ──
  // Personal/financial/academic info used to be collected here too, purely to
  // prefill the scholarship application later - it's now collected once, on
  // the application form itself, so this only ever needs enough to create
  // the account and send it a verification code.
  const handleRegister = useCallback(async () => {
    setRegError('')
    const { lastName, firstName, email, password, confirm_password, join_code } = regData

    if (!join_code.trim())                    { setRegError('An LGU join code is required'); return }
    if (!lastName.trim())                     { setRegError('Last name is required'); return }
    if (!firstName.trim())                    { setRegError('First name is required'); return }
    if (!email.trim())                        { setRegError('Email is required'); return }
    if (!/\S+@\S+\.\S+/.test(email))         { setRegError('Enter a valid email address'); return }
    if (!password)                            { setRegError('Password is required'); return }
    if (password.length < 8)                  { setRegError('Password must be at least 8 characters'); return }
    if (getStrength(password) < 1)            { setRegError('Please choose a stronger password'); return }
    if (password !== confirm_password)        { setRegError('Passwords do not match'); return }
    if (!privacyConsent)                      { setRegError('You must agree to the Data Privacy Act to create an account'); return }

    const middleInitial = regData.middleName.trim() ? `${regData.middleName.trim().charAt(0)}. ` : ''
    const full_name = `${firstName.trim()} ${middleInitial}${lastName.trim()}`.replace(/\s+/g, ' ').trim()

    setRegLoading(true)
    try {
      const res = await fetchWithTimeout(`${API_BASE_URL}/api/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name,
          email: email.trim().toLowerCase(),
          password,
          join_code: join_code.trim().toUpperCase(),
        })
      })
      const data = await res.json()

      if (!res.ok) {
        setRegError(data.error || 'Registration failed. Please try again.')
        return
      }

      setRegStep(2)
    } catch {
      setRegError(connectionErrorMessage())
    } finally {
      setRegLoading(false)
    }
  }, [regData, privacyConsent])

  // ── REGISTER WITH GOOGLE ── (skips password + the emailed OTP entirely,
  // since Google already proved the email is real)
  const handleGoogleRegisterSuccess = useCallback(async (credentialResponse) => {
    setRegError('')
    if (!regData.join_code.trim())    { setRegError('An LGU join code is required'); return }
    if (!privacyConsent)              { setRegError('You must agree to the Data Privacy Act to create an account'); return }
    if (!credentialResponse.credential) { setRegError('Google sign-up failed. Please try again.'); return }

    setRegLoading(true)
    try {
      const res = await fetchWithTimeout(`${API_BASE_URL}/api/register/google`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          credential: credentialResponse.credential,
          join_code: regData.join_code.trim().toUpperCase(),
        })
      })
      const data = await res.json()

      if (!res.ok) {
        setRegError(data.error || 'Could not sign up with Google. Please try again.')
        return
      }

      setSession(data.user, data.token)
      navigate(data.user.role === 'student' ? '/student/dashboard' : '/admin/dashboard')
    } catch {
      setRegError(connectionErrorMessage())
    } finally {
      setRegLoading(false)
    }
  }, [regData.join_code, privacyConsent, navigate])

  // ── REGISTER: VERIFY EMAIL OTP (STEP 2) ──
  const handleVerifyRegOtp = useCallback(async () => {
    setRegOtpError('')
    if (!regOtpCode.trim()) { setRegOtpError('Enter the code from your email'); return }

    setRegOtpLoading(true)
    try {
      const res = await fetchWithTimeout(`${API_BASE_URL}/api/register/verify-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: regData.email.trim().toLowerCase(), code: regOtpCode.trim() })
      })
      const data = await res.json()

      if (!res.ok) {
        setRegOtpError(data.error || 'Verification failed. Please try again.')
        return
      }

      setSession(data.user, data.token)
      navigate('/student/dashboard')
    } catch {
      setRegOtpError(connectionErrorMessage())
    } finally {
      setRegOtpLoading(false)
    }
  }, [regData.email, regOtpCode, navigate])

  const handleResendRegOtp = useCallback(async () => {
    setRegResendMessage('')
    setRegResendLoading(true)
    try {
      await fetchWithTimeout(`${API_BASE_URL}/api/register/resend-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: regData.email.trim().toLowerCase() })
      })
      setRegResendMessage('A new code has been sent to your email.')
    } catch {
      setRegResendMessage(connectionErrorMessage())
    } finally {
      setRegResendLoading(false)
    }
  }, [regData.email])

  // ── FORGOT HANDLER ──
  const handleForgot = useCallback(async () => {
    setForgotError('')
    if (!forgotEmail.trim())                  { setForgotError('Email is required'); return }
    if (!/\S+@\S+\.\S+/.test(forgotEmail))   { setForgotError('Enter a valid email address'); return }

    setForgotLoading(true)
    try {
      await fetchWithTimeout(`${API_BASE_URL}/api/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: forgotEmail.trim().toLowerCase() })
      })
      // The API always responds the same way regardless of whether the email
      // exists, so there's nothing to branch on here - just show the sent state.
      setForgotSent(true)
    } catch {
      setForgotError(connectionErrorMessage())
    }
    setForgotLoading(false)
  }, [forgotEmail])

  const handleKeyDown = (e) => {
    if (e.key !== 'Enter') return
    if (tab === 'login') handleLogin()
    else if (regStep === 1) handleRegister()
    else handleVerifyRegOtp()
  }

  // Sits under each form's heading, as in the design.
  const tabsEl = (
    <div className="lp-tabs">
      <button className={`lp-tab ${tab === 'login' ? 'active' : ''}`} onClick={() => switchTab('login')}>
        Sign In
      </button>
      <button className={`lp-tab ${tab === 'register' ? 'active' : ''}`} onClick={() => switchTab('register')}>
        Create Account
      </button>
    </div>
  )

  return (
    <AuthShell
      after={<>
      {/* FORGOT PASSWORD MODAL */}
      {showForgot && (
        <div className="lp-overlay" onClick={() => { setShowForgot(false); setForgotSent(false); setForgotEmail(''); setForgotError('') }}>
          <div className="lp-modal" onClick={e => e.stopPropagation()}>
            {!forgotSent ? (
              <>
                <h3>Reset Password</h3>
                <p>Enter your registered email and we'll send you a reset link.</p>

                {forgotError && <div className="lp-alert error" style={{ marginBottom: '14px' }}>{forgotError}</div>}

                <div className="lp-field">
                  <label>Email Address</label>
                  <input
                    className="lp-input"
                    type="email"
                    placeholder="Enter your email"
                    value={forgotEmail}
                    onChange={e => { setForgotEmail(e.target.value); setForgotError('') }}
                    onKeyDown={e => e.key === 'Enter' && handleForgot()}
                    autoFocus
                  />
                </div>

                <div className="lp-modal-btns">
                  <button className="lp-btn-cancel" onClick={() => { setShowForgot(false); setForgotEmail(''); setForgotError('') }}>
                    Cancel
                  </button>
                  <button className="lp-btn-send" onClick={handleForgot} disabled={forgotLoading}>
                    {forgotLoading ? 'Sending…' : 'Send Reset Link'}
                  </button>
                </div>
              </>
            ) : (
              <div style={{ textAlign: 'center' }}>
                <h3 style={{ marginBottom: '8px' }}>Email Sent</h3>
                <p>Check your inbox at <strong>{forgotEmail}</strong> for the password reset link.</p>
                <button className="lp-btn" style={{ marginTop: '8px' }} onClick={() => { setShowForgot(false); setForgotSent(false); setForgotEmail('') }}>
                  Done
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      </>}
    >
      {/*  LOGIN FORM  */}
      {tab === 'login' && (
        <>
          <h2 className="lp-title">Welcome back!</h2>
          <p className="lp-sub">Sign in to your account to continue</p>
          {tabsEl}

          {loginError && (
            <div className="lp-alert error">{loginError}</div>
          )}

          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <GoogleLogin
              onSuccess={handleGoogleLoginSuccess}
              onError={() => setLoginError('Google sign-in failed. Please try again.')}
              text="signin_with"
            />
          </div>
          <div className="lp-or">or</div>

          <div className="lp-field">
            <label>Email Address</label>
            <input
              className={`lp-input${loginError && !loginData.email ? ' input-err' : ''}`}
              type="email"
              placeholder="Enter your email"
              value={loginData.email}
              autoComplete="email"
              onChange={e => { setLoginData(p => ({ ...p, email: e.target.value })); setLoginError('') }}
              onKeyDown={handleKeyDown}
            />
          </div>

          <div className="lp-field">
            <label>Password</label>
            <div className="lp-input-wrap">
              <input
                className={`lp-input has-icon${loginError && !loginData.password ? ' input-err' : ''}`}
                type={showPw ? 'text' : 'password'}
                placeholder="Enter your password"
                value={loginData.password}
                autoComplete="current-password"
                onChange={e => { setLoginData(p => ({ ...p, password: e.target.value })); setLoginError('') }}
                onKeyDown={handleKeyDown}
              />
              <button className="lp-eye" type="button" onClick={() => setShowPw(v => !v)} aria-label="Toggle password">
                {showPw ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
          </div>

          <div className="lp-forgot-row">
            <button className="lp-link" type="button" onClick={() => setShowForgot(true)}>
              Forgot password?
            </button>
          </div>

          <button className="lp-btn" onClick={handleLogin} disabled={loginLoading}>
            {loginLoading ? <><span className="spinner" /> Signing in…</> : <>Sign In <ArrowRightIcon /></>}
          </button>
        </>
      )}

      {/* REGISTER FORM */}
      {tab === 'register' && (
        <>
          {regStep === 2 ? (
            <>
              <h2 className="lp-title">Verify Your Email</h2>
              <p className="lp-sub">
                We sent a 6-digit code to <strong>{regData.email}</strong>. Enter it below to finish creating your account.
              </p>
              {tabsEl}

              {regOtpError && <div className="lp-alert error">{regOtpError}</div>}

              <div className="lp-field">
                <label>Verification Code</label>
                <input
                  className="lp-input"
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  placeholder="Enter verification code"
                  value={regOtpCode}
                  onChange={e => { setRegOtpCode(e.target.value.replace(/\D/g, '')); setRegOtpError('') }}
                  onKeyDown={e => e.key === 'Enter' && handleVerifyRegOtp()}
                  autoFocus
                />
              </div>

              <button className="lp-btn" onClick={handleVerifyRegOtp} disabled={regOtpLoading}>
                {regOtpLoading ? <><span className="spinner" /> Verifying…</> : 'Verify & Continue'}
              </button>

              <p style={{ marginTop: '16px', textAlign: 'center', fontSize: '13.5px', color: 'var(--text-secondary)' }}>
                Didn't get it?{' '}
                <button className="lp-link" type="button" onClick={handleResendRegOtp} disabled={regResendLoading}>
                  {regResendLoading ? 'Sending…' : 'Resend code'}
                </button>
              </p>
              {regResendMessage && <p style={{ textAlign: 'center', fontSize: '13px', color: 'var(--text-secondary)' }}>{regResendMessage}</p>}
            </>
          ) : (
            <>
              <h2 className="lp-title">Create Account</h2>
              <p className="lp-sub">Register as a student to apply for scholarships</p>
              {tabsEl}

              {regError && <div className="lp-alert error">{regError}</div>}

              <div className="lp-field">
                <label>LGU Join Code</label>
                <input
                  className="lp-input"
                  type="text"
                  placeholder="Enter your LGU join code"
                  value={regData.join_code}
                  onChange={e => { setRegData(p => ({ ...p, join_code: e.target.value })); setRegError(''); setJoinCodeOrgName(''); setJoinCodeError('') }}
                  onBlur={handleJoinCodeBlur}
                  onKeyDown={handleKeyDown}
                />
                {joinCodeChecking && <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>Checking code…</p>}
                {!joinCodeChecking && joinCodeOrgName && (
                  <p style={{ fontSize: '12px', color: 'var(--success, #16a34a)', marginTop: '4px' }}>Joining {joinCodeOrgName}</p>
                )}
                {!joinCodeChecking && joinCodeError && (
                  <p style={{ fontSize: '12px', color: 'var(--danger)', marginTop: '4px' }}>{joinCodeError}</p>
                )}
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>Ask your LGU's admin for this code.</p>
              </div>

              {regData.join_code.trim() ? (
                <div style={{ display: 'flex', justifyContent: 'center' }}>
                  <GoogleLogin
                    onSuccess={handleGoogleRegisterSuccess}
                    onError={() => setRegError('Google sign-up failed. Please try again.')}
                    text="signup_with"
                  />
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                  <button type="button" disabled className="lp-btn" style={{ opacity: .5, cursor: 'not-allowed', width: '250px' }}>
                    Continue with Google
                  </button>
                  <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Enter your LGU join code above first</p>
                </div>
              )}
              <div className="lp-or">or fill in the rest yourself</div>

              <div className="lp-form-grid-2">
                <div className="lp-field">
                  <label>Last Name</label>
                  <input
                    className="lp-input"
                    type="text"
                    placeholder="Last Name"
                    value={regData.lastName}
                    autoComplete="family-name"
                    onChange={e => { setRegData(p => ({ ...p, lastName: e.target.value })); setRegError('') }}
                    onKeyDown={handleKeyDown}
                  />
                </div>

                <div className="lp-field">
                  <label>First Name</label>
                  <input
                    className="lp-input"
                    type="text"
                    placeholder="First Name"
                    value={regData.firstName}
                    autoComplete="given-name"
                    onChange={e => { setRegData(p => ({ ...p, firstName: e.target.value })); setRegError('') }}
                    onKeyDown={handleKeyDown}
                  />
                </div>
              </div>

              <div className="lp-field">
                <label>Middle Initial <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}>(optional)</span></label>
                <input
                  className="lp-input"
                  type="text"
                  placeholder="Middle Initial"
                  maxLength={1}
                  value={regData.middleName}
                  autoComplete="additional-name"
                  onChange={e => { setRegData(p => ({ ...p, middleName: e.target.value })); setRegError('') }}
                  onKeyDown={handleKeyDown}
                />
              </div>

              <div className="lp-field">
                <label>Email Address</label>
                <input
                  className="lp-input"
                  type="email"
                  placeholder="Enter your email"
                  value={regData.email}
                  autoComplete="email"
                  onChange={e => { setRegData(p => ({ ...p, email: e.target.value })); setRegError('') }}
                  onKeyDown={handleKeyDown}
                />
              </div>

              <div className="lp-field">
                <label>Password</label>
                <div className="lp-input-wrap">
                  <input
                    className="lp-input has-icon"
                    type={showRegPw ? 'text' : 'password'}
                    placeholder="At least 8 characters"
                    value={regData.password}
                    autoComplete="new-password"
                    onChange={e => { setRegData(p => ({ ...p, password: e.target.value })); setRegError('') }}
                    onKeyDown={handleKeyDown}
                  />
                  <button className="lp-eye" type="button" onClick={() => setShowRegPw(v => !v)} aria-label="Toggle password">
                    {showRegPw ? <EyeOffIcon /> : <EyeIcon />}
                  </button>
                </div>
                <PasswordStrength password={regData.password} />
              </div>

              <div className="lp-field">
                <label>Confirm Password</label>
                <div className="lp-input-wrap">
                  <input
                    className={`lp-input has-icon${regData.confirm_password && regData.confirm_password !== regData.password ? ' input-err' : ''}`}
                    type={showConfirmPw ? 'text' : 'password'}
                    placeholder="Re-enter your password"
                    value={regData.confirm_password}
                    autoComplete="new-password"
                    onChange={e => { setRegData(p => ({ ...p, confirm_password: e.target.value })); setRegError('') }}
                    onKeyDown={handleKeyDown}
                  />
                  <button className="lp-eye" type="button" onClick={() => setShowConfirmPw(v => !v)} aria-label="Toggle confirm password">
                    {showConfirmPw ? <EyeOffIcon /> : <EyeIcon />}
                  </button>
                </div>
                {regData.confirm_password && regData.confirm_password !== regData.password && (
                  <p style={{ fontSize: '12px', color: 'var(--danger)', marginTop: '4px' }}>Passwords do not match</p>
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
                    onChange={e => { setPrivacyConsent(e.target.checked); setRegError('') }}
                    style={{ marginTop: '3px', flexShrink: 0, accentColor: 'var(--brand)' }}
                  />
                  <span>
                    I consent to the collection and processing of my personal data
                    in accordance with the{' '}
                    <strong>Data Privacy Act of 2012 (RA 10173)</strong>.
                    My information will only be used for scholarship evaluation purposes.
                  </span>
                </label>
              </div>
              <button className="lp-btn" onClick={handleRegister} disabled={regLoading}>
                {regLoading ? <><span className="spinner" /> Creating Account…</> : 'Create Account'}
              </button>

              <p style={{ marginTop: '16px', textAlign: 'center', fontSize: '13.5px', color: 'var(--text-secondary)' }}>
                Already have an account?{' '}
                <button className="lp-link" type="button" onClick={() => switchTab('login')}>Sign in here</button>
              </p>
              <p style={{ marginTop: '8px', textAlign: 'center', fontSize: '12.5px', color: 'var(--text-secondary)' }}>
                LGU official?{' '}
                <Link className="lp-link" to="/apply-admin">Apply for admin access</Link>
              </p>
            </>
          )}
        </>
      )}
    </AuthShell>
  )
}

export default Login
