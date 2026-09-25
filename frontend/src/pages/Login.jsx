import { useState, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { API_BASE_URL, setSession, fetchWithTimeout, connectionErrorMessage } from '../api'
import AuthShell from '../components/AuthShell'
import { INCOME_RANGES } from '../incomeRanges'


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

// These three lists must match the eligibility model's encoding exactly
// (see backend/schema/ml_model.md) - keep in sync with ApplicationForm.jsx.
const EDUCATION_LEVELS = ['None', 'Elementary', 'High School', 'Vocational', 'College', 'Postgraduate']
const OCCUPATION_CATEGORIES = [
  'Unemployed', 'Informal/Vendor', 'Laborer/Driver', 'Skilled Trade',
  'Office/Clerical', 'Professional', 'Deceased/Not Applicable'
]
const HOUSING_SITUATIONS = ['Owned', 'Rented', 'Living with relatives', 'Informal settler']
const RELIGIONS = [
  'Roman Catholic', 'Iglesia ni Cristo', 'Islam', 'Born Again Christian',
  'Seventh Day Adventist', 'Jesus Miracle Crusade', 'Others'
]

// Municipalities currently served. Add another { city, province } entry here to make
// it selectable in the registration address dropdown - nothing else needs to change.
const ADDRESS_CITIES = [
  { city: 'Liliw', province: 'Laguna' },
  { city: 'Tiaong', province: 'Quezon' },
]

const EMPTY_REG_DATA = {
  join_code: '',
  lastName: '', firstName: '', middleName: '', email: '', password: '', confirm_password: '',
  dob: '', gender: '', religion: '', citizenship: 'Filipino', contactNumber: '',
  street: '', city: '',
  fatherName: '', fatherOccupation: '', fatherEducation: '',
  motherName: '', motherOccupation: '', motherEducation: '',
  monthlyIncome: '', familySize: '', numSiblings: '', numSiblingsStudying: '',
  housingSituation: '', hasOtherScholarship: '', otherScholarshipDetails: '',
}

// ── VALIDATE STEP 2 OF REGISTRATION (personal info) ──
function validateRegPersonalInfo(d) {
  const errors = {}
  if (!d.dob) errors.dob = 'Date of birth is required'
  if (!d.gender) errors.gender = 'Gender is required'
  if (!d.religion) errors.religion = 'Religion is required'
  if (!d.citizenship.trim()) errors.citizenship = 'Citizenship is required'
  if (!d.contactNumber.trim()) errors.contactNumber = 'Contact number is required'
  else if (!/^09\d{9}$/.test(d.contactNumber.replace(/\s/g, '')))
    errors.contactNumber = 'Enter a valid PH number (e.g. 09123456789)'
  if (!d.street.trim()) errors.street = 'Street/Barangay is required'
  if (!d.city) errors.city = 'City/Municipality is required'
  if (!d.fatherName.trim()) errors.fatherName = "Father's name is required"
  if (!d.fatherOccupation) errors.fatherOccupation = "Father's occupation is required"
  if (!d.fatherEducation) errors.fatherEducation = "Father's education level is required"
  if (!d.motherName.trim()) errors.motherName = "Mother's name is required"
  if (!d.motherOccupation) errors.motherOccupation = "Mother's occupation is required"
  if (!d.motherEducation) errors.motherEducation = "Mother's education level is required"
  if (!d.monthlyIncome) errors.monthlyIncome = 'Monthly household income is required'
  if (!d.familySize) errors.familySize = 'Family size is required'
  else if (d.familySize < 1 || d.familySize > 20) errors.familySize = 'Enter a valid family size (1-20)'
  if (d.numSiblings === '') errors.numSiblings = 'Number of siblings is required'
  else if (d.numSiblings < 0 || d.numSiblings > 20) errors.numSiblings = 'Enter a valid number (0-20)'
  if (d.numSiblingsStudying === '') errors.numSiblingsStudying = 'This field is required'
  else if (d.numSiblingsStudying < 0 || Number(d.numSiblingsStudying) > Number(d.numSiblings || 0))
    errors.numSiblingsStudying = 'Cannot exceed total number of siblings'
  if (!d.housingSituation) errors.housingSituation = 'Housing situation is required'
  if (!d.hasOtherScholarship) errors.hasOtherScholarship = 'Please indicate if you have other scholarships'
  if (d.hasOtherScholarship === 'yes' && !d.otherScholarshipDetails.trim())
    errors.otherScholarshipDetails = 'Please provide details about your other scholarships'
  return errors
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
  const [regFieldErrors, setRegFieldErrors] = useState({})
  const [showRegPw, setShowRegPw] = useState(false)
  const [showConfirmPw, setShowConfirmPw] = useState(false)
  const [regError, setRegError] = useState('')
  const [regLoading, setRegLoading] = useState(false)
  const [privacyConsent, setPrivacyConsent] = useState(false)
  const [joinCodeOrgName, setJoinCodeOrgName] = useState('')
  const [joinCodeChecking, setJoinCodeChecking] = useState(false)
  const [joinCodeError, setJoinCodeError] = useState('')

  // ── REGISTER: EMAIL VERIFICATION (step 3) ──
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
  setRegFieldErrors({})
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

  // ── REGISTER STEP 1 -> STEP 2 ──
  const handleRegNext = useCallback(() => {
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
    if (!privacyConsent)                      {setRegError('You must agree to the Data Privacy Act to create an account');return}

    setRegStep(2)
  }, [regData, privacyConsent])

  // ── REGISTER SUBMIT (STEP 2) ──
  const handleRegister = useCallback(async () => {
    setRegError('')
    const fieldErrors = validateRegPersonalInfo(regData)
    if (Object.keys(fieldErrors).length > 0) {
      setRegFieldErrors(fieldErrors)
      setRegError('Please fill in all required fields')
      return
    }
    setRegFieldErrors({})

    const selectedCity = ADDRESS_CITIES.find(c => c.city === regData.city)
    const address = `${regData.street.trim()}, ${regData.city}, ${selectedCity ? selectedCity.province : ''}`
    const middleInitial = regData.middleName.trim() ? `${regData.middleName.trim().charAt(0)}. ` : ''
    const full_name = `${regData.firstName.trim()} ${middleInitial}${regData.lastName.trim()}`.replace(/\s+/g, ' ').trim()

    setRegLoading(true)
    try {
      const res = await fetchWithTimeout(`${API_BASE_URL}/api/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name,
          email: regData.email.trim().toLowerCase(),
          password: regData.password,
          join_code: regData.join_code.trim().toUpperCase(),
          dob: regData.dob,
          gender: regData.gender,
          religion: regData.religion,
          citizenship: regData.citizenship.trim(),
          contactNumber: regData.contactNumber.trim(),
          address,
          fatherName: regData.fatherName.trim(),
          fatherOccupation: regData.fatherOccupation,
          fatherEducation: regData.fatherEducation,
          motherName: regData.motherName.trim(),
          motherOccupation: regData.motherOccupation,
          motherEducation: regData.motherEducation,
          monthlyIncome: regData.monthlyIncome,
          familySize: regData.familySize,
          numSiblings: regData.numSiblings,
          numSiblingsStudying: regData.numSiblingsStudying,
          housingSituation: regData.housingSituation,
          hasOtherScholarship: regData.hasOtherScholarship,
          otherScholarshipDetails: regData.otherScholarshipDetails,
        })
      })
      const data = await res.json()

      if (!res.ok) {
        setRegError(data.error || 'Registration failed. Please try again.')
        return
      }

      setRegStep(3)
    } catch {
      setRegError(connectionErrorMessage())
    } finally {
      setRegLoading(false)
    }
  }, [regData])

  // ── REGISTER: VERIFY EMAIL OTP (STEP 3) ──
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
    else if (regStep === 1) handleRegNext()
    else handleRegister()
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
  const wideForm = tab === 'register' && regStep === 2

  return (
    <AuthShell
      wide={wideForm}
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
          {regStep === 3 ? (
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
          ) : regStep === 1 ? (
            <>
              <h2 className="lp-title">Create Account</h2>
              <p className="lp-sub">Register as a student to apply for scholarships</p>
              {tabsEl}
              <p className="lp-step-indicator">Step 1 of 2 — Account</p>

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
              <button className="lp-btn" onClick={handleRegNext}>
                Next: Personal Information
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
          ) : (
            <>
              <h2 className="lp-title">Create Account</h2>
              <p className="lp-sub">
                This information is reused to pre-fill your scholarship application later, so you won't need to type it twice.
              </p>
              {tabsEl}
              <p className="lp-step-indicator">Step 2 of 2 — Personal Information</p>

              {regError && <div className="lp-alert error">{regError}</div>}

              <p className="lp-section-title">Personal Info</p>
              <div className="lp-form-grid-2">
                <div className="lp-field">
                  <label>Gender</label>
                  <select
                    className={`lp-input${regFieldErrors.gender ? ' input-err' : ''}`}
                    value={regData.gender}
                    onChange={e => { setRegData(p => ({ ...p, gender: e.target.value })); setRegError('') }}>
                    <option value="">Select gender</option>
                    <option value="Male">Male</option>
                    <option value="Female">Female</option>
                  </select>
                  {regFieldErrors.gender && <p className="lp-field-err">{regFieldErrors.gender}</p>}
                </div>

                <div className="lp-field">
                  <label>Date of Birth</label>
                  <input
                    className={`lp-input${regFieldErrors.dob ? ' input-err' : ''}`}
                    type="date"
                    value={regData.dob}
                    onChange={e => { setRegData(p => ({ ...p, dob: e.target.value })); setRegError('') }} />
                  {regFieldErrors.dob && <p className="lp-field-err">{regFieldErrors.dob}</p>}
                </div>

                <div className="lp-field">
                  <label>Religion</label>
                  <select
                    className={`lp-input${regFieldErrors.religion ? ' input-err' : ''}`}
                    value={regData.religion}
                    onChange={e => { setRegData(p => ({ ...p, religion: e.target.value })); setRegError('') }}>
                    <option value="">Select religion</option>
                    {RELIGIONS.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                  {regFieldErrors.religion && <p className="lp-field-err">{regFieldErrors.religion}</p>}
                </div>

                <div className="lp-field">
                  <label>Citizenship</label>
                  <input
                    className={`lp-input${regFieldErrors.citizenship ? ' input-err' : ''}`}
                    type="text" placeholder="Filipino"
                    value={regData.citizenship}
                    onChange={e => { setRegData(p => ({ ...p, citizenship: e.target.value })); setRegError('') }} />
                  {regFieldErrors.citizenship && <p className="lp-field-err">{regFieldErrors.citizenship}</p>}
                </div>

                <div className="lp-field">
                  <label>Contact Number</label>
                  <input
                    className={`lp-input${regFieldErrors.contactNumber ? ' input-err' : ''}`}
                    type="text" placeholder="Enter your contact number"
                    value={regData.contactNumber}
                    onChange={e => { setRegData(p => ({ ...p, contactNumber: e.target.value })); setRegError('') }} />
                  {regFieldErrors.contactNumber && <p className="lp-field-err">{regFieldErrors.contactNumber}</p>}
                </div>
              </div>

              <p className="lp-section-title">Address</p>
              <div className="lp-form-grid-2">
                <div className="lp-field">
                  <label>Street / Barangay</label>
                  <input
                    className={`lp-input${regFieldErrors.street ? ' input-err' : ''}`}
                    type="text" placeholder="e.g. Purok 3, Brgy. San Isidro"
                    value={regData.street}
                    onChange={e => { setRegData(p => ({ ...p, street: e.target.value })); setRegError('') }} />
                  {regFieldErrors.street && <p className="lp-field-err">{regFieldErrors.street}</p>}
                </div>

                <div className="lp-field">
                  <label>City / Municipality</label>
                  <select
                    className={`lp-input${regFieldErrors.city ? ' input-err' : ''}`}
                    value={regData.city}
                    onChange={e => { setRegData(p => ({ ...p, city: e.target.value })); setRegError('') }}>
                    <option value="">Select city / municipality</option>
                    {ADDRESS_CITIES.map(c => (
                      <option key={c.city} value={c.city}>{c.city}, {c.province}</option>
                    ))}
                  </select>
                  {regFieldErrors.city && <p className="lp-field-err">{regFieldErrors.city}</p>}
                </div>
              </div>

              <p className="lp-section-title">Parental Details</p>

              <p className="lp-subsection-title">Father's Information</p>
              <div className="lp-form-grid-2">
                <div className="lp-field">
                  <label>Father's Name</label>
                  <input
                    className={`lp-input${regFieldErrors.fatherName ? ' input-err' : ''}`}
                    type="text" placeholder="First M. Last"
                    value={regData.fatherName}
                    onChange={e => { setRegData(p => ({ ...p, fatherName: e.target.value })); setRegError('') }} />
                  {regFieldErrors.fatherName && <p className="lp-field-err">{regFieldErrors.fatherName}</p>}
                </div>

                <div className="lp-field">
                  <label>Father's Occupation</label>
                  <select
                    className={`lp-input${regFieldErrors.fatherOccupation ? ' input-err' : ''}`}
                    value={regData.fatherOccupation}
                    onChange={e => { setRegData(p => ({ ...p, fatherOccupation: e.target.value })); setRegError('') }}>
                    <option value="">Select occupation</option>
                    {OCCUPATION_CATEGORIES.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                  {regFieldErrors.fatherOccupation && <p className="lp-field-err">{regFieldErrors.fatherOccupation}</p>}
                </div>

                <div className="lp-field">
                  <label>Father's Education Level</label>
                  <select
                    className={`lp-input${regFieldErrors.fatherEducation ? ' input-err' : ''}`}
                    value={regData.fatherEducation}
                    onChange={e => { setRegData(p => ({ ...p, fatherEducation: e.target.value })); setRegError('') }}>
                    <option value="">Select education level</option>
                    {EDUCATION_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
                  </select>
                  {regFieldErrors.fatherEducation && <p className="lp-field-err">{regFieldErrors.fatherEducation}</p>}
                </div>
              </div>

              <p className="lp-subsection-title">Mother's Information</p>
              <div className="lp-form-grid-2">
                <div className="lp-field">
                  <label>Mother's Name</label>
                  <input
                    className={`lp-input${regFieldErrors.motherName ? ' input-err' : ''}`}
                    type="text" placeholder="First M. Last"
                    value={regData.motherName}
                    onChange={e => { setRegData(p => ({ ...p, motherName: e.target.value })); setRegError('') }} />
                  {regFieldErrors.motherName && <p className="lp-field-err">{regFieldErrors.motherName}</p>}
                </div>

                <div className="lp-field">
                  <label>Mother's Occupation</label>
                  <select
                    className={`lp-input${regFieldErrors.motherOccupation ? ' input-err' : ''}`}
                    value={regData.motherOccupation}
                    onChange={e => { setRegData(p => ({ ...p, motherOccupation: e.target.value })); setRegError('') }}>
                    <option value="">Select occupation</option>
                    {OCCUPATION_CATEGORIES.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                  {regFieldErrors.motherOccupation && <p className="lp-field-err">{regFieldErrors.motherOccupation}</p>}
                </div>

                <div className="lp-field">
                  <label>Mother's Education Level</label>
                  <select
                    className={`lp-input${regFieldErrors.motherEducation ? ' input-err' : ''}`}
                    value={regData.motherEducation}
                    onChange={e => { setRegData(p => ({ ...p, motherEducation: e.target.value })); setRegError('') }}>
                    <option value="">Select education level</option>
                    {EDUCATION_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
                  </select>
                  {regFieldErrors.motherEducation && <p className="lp-field-err">{regFieldErrors.motherEducation}</p>}
                </div>
              </div>

              <p className="lp-subsection-title">Household</p>
              <div className="lp-form-grid-2">
                <div className="lp-field">
                  <label>Monthly Household Income</label>
                  <select
                    className={`lp-input${regFieldErrors.monthlyIncome ? ' input-err' : ''}`}
                    value={regData.monthlyIncome}
                    onChange={e => { setRegData(p => ({ ...p, monthlyIncome: e.target.value })); setRegError('') }}>
                    <option value="">Select income range</option>
                    {INCOME_RANGES.map(r => <option key={r.label} value={r.value}>{r.label}</option>)}
                  </select>
                  {regFieldErrors.monthlyIncome && <p className="lp-field-err">{regFieldErrors.monthlyIncome}</p>}
                </div>

                <div className="lp-field">
                  <label>Housing Situation</label>
                  <select
                    className={`lp-input${regFieldErrors.housingSituation ? ' input-err' : ''}`}
                    value={regData.housingSituation}
                    onChange={e => { setRegData(p => ({ ...p, housingSituation: e.target.value })); setRegError('') }}>
                    <option value="">Select housing situation</option>
                    {HOUSING_SITUATIONS.map(h => <option key={h} value={h}>{h}</option>)}
                  </select>
                  {regFieldErrors.housingSituation && <p className="lp-field-err">{regFieldErrors.housingSituation}</p>}
                </div>

                <div className="lp-field">
                  <label>Family Size</label>
                  <input
                    className={`lp-input${regFieldErrors.familySize ? ' input-err' : ''}`}
                    type="number" placeholder="e.g. 5" min="1" max="20"
                    value={regData.familySize}
                    onChange={e => { setRegData(p => ({ ...p, familySize: e.target.value })); setRegError('') }} />
                  {regFieldErrors.familySize && <p className="lp-field-err">{regFieldErrors.familySize}</p>}
                </div>

                <div className="lp-field">
                  <label>Number of Siblings</label>
                  <input
                    className={`lp-input${regFieldErrors.numSiblings ? ' input-err' : ''}`}
                    type="number" placeholder="e.g. 2" min="0" max="20"
                    value={regData.numSiblings}
                    onChange={e => { setRegData(p => ({ ...p, numSiblings: e.target.value })); setRegError('') }} />
                  {regFieldErrors.numSiblings && <p className="lp-field-err">{regFieldErrors.numSiblings}</p>}
                </div>

                <div className="lp-field">
                  <label>Siblings Currently Studying</label>
                  <input
                    className={`lp-input${regFieldErrors.numSiblingsStudying ? ' input-err' : ''}`}
                    type="number" placeholder="e.g. 1" min="0" max="20"
                    value={regData.numSiblingsStudying}
                    onChange={e => { setRegData(p => ({ ...p, numSiblingsStudying: e.target.value })); setRegError('') }} />
                  {regFieldErrors.numSiblingsStudying && <p className="lp-field-err">{regFieldErrors.numSiblingsStudying}</p>}
                </div>
              </div>

              <p className="lp-section-title">Scholarship Information</p>
              <div className="lp-field">
                <label>Are you currently receiving any scholarship from barangay, city, or provincial level?</label>
                <div className="lp-radio-group">
                  <label className="lp-radio-option">
                    <input
                      type="radio" name="hasOtherScholarship" value="no"
                      checked={regData.hasOtherScholarship === 'no'}
                      onChange={e => { setRegData(p => ({ ...p, hasOtherScholarship: e.target.value })); setRegError('') }} />
                    <span>No — I am not receiving any other scholarship</span>
                  </label>
                  <label className="lp-radio-option">
                    <input
                      type="radio" name="hasOtherScholarship" value="yes"
                      checked={regData.hasOtherScholarship === 'yes'}
                      onChange={e => { setRegData(p => ({ ...p, hasOtherScholarship: e.target.value })); setRegError('') }} />
                    <span>Yes — I am currently receiving another scholarship</span>
                  </label>
                </div>
                {regFieldErrors.hasOtherScholarship && <p className="lp-field-err">{regFieldErrors.hasOtherScholarship}</p>}
              </div>

              {regData.hasOtherScholarship === 'yes' && (
                <div className="lp-field">
                  <label>Please specify which scholarship you are receiving</label>
                  <input
                    className={`lp-input${regFieldErrors.otherScholarshipDetails ? ' input-err' : ''}`}
                    type="text" placeholder="e.g. Barangay San Jose Scholarship, CHED Scholarship, etc."
                    value={regData.otherScholarshipDetails}
                    onChange={e => { setRegData(p => ({ ...p, otherScholarshipDetails: e.target.value })); setRegError('') }} />
                  {regFieldErrors.otherScholarshipDetails && <p className="lp-field-err">{regFieldErrors.otherScholarshipDetails}</p>}
                </div>
              )}

              <div className="lp-step-btns">
                <button className="lp-btn-back" type="button" onClick={() => setRegStep(1)}>Back</button>
                <button className="lp-btn" onClick={handleRegister} disabled={regLoading}>
                  {regLoading ? <><span className="spinner" /> Creating Account…</> : 'Create Account'}
                </button>
              </div>
            </>
          )}
        </>
      )}

    </AuthShell>
  )
}

export default Login
