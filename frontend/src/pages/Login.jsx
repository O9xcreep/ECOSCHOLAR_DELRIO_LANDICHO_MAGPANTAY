import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_BASE_URL, setSession } from '../api'

const css = `
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Playfair+Display:wght@700&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --brand:       #5C35D4;
    --brand-light: #7B5CE5;
    --brand-dark:  #3D1FA8;
    --accent:      #F5A623;
    --danger:      #E53E3E;
    --success:     #38A169;
    --text-primary:   #1A1A2E;
    --text-secondary: #6B7280;
    --border:      #E5E7EB;
    --bg-card:     #FFFFFF;
    --bg-input:    #F9FAFB;
    --radius:      12px;
    --shadow-sm:   0 1px 3px rgba(0,0,0,.08);
    --shadow-md:   0 4px 20px rgba(0,0,0,.10);
    --shadow-lg:   0 10px 40px rgba(92,53,212,.18);
    --transition:  .2s cubic-bezier(.4,0,.2,1);
  }

  body { font-family: 'DM Sans', sans-serif; }

  /* ── PAGE ── */
  .lp-page {
    display: flex;
    min-height: 100vh;
    background: #F3F0FF;
  }

  /* ── LEFT PANEL ── */
  .lp-left {
    flex: 0 0 420px;
    background: linear-gradient(145deg, var(--brand-dark) 0%, var(--brand) 50%, #8B5CF6 100%);
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
    font-size: 38px;
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

  /* ── RIGHT PANEL ── */
  .lp-right {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px 24px;
    overflow-y: auto;
  }

  .lp-card {
    background: var(--bg-card);
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

  /* ── MOBILE LOGO ── */
  .lp-mobile-logo {
    display: none;
    align-items: center;
    gap: 10px;
    font-family: 'Playfair Display', serif;
    font-size: 22px;
    color: var(--brand);
    margin-bottom: 24px;
  }

  /* ── TABS ── */
  .lp-tabs {
    display: flex;
    background: #F3F0FF;
    border-radius: 10px;
    padding: 4px;
    margin-bottom: 28px;
    gap: 4px;
  }

  .lp-tab {
    flex: 1;
    padding: 10px;
    border: none;
    border-radius: 8px;
    background: transparent;
    font-family: 'DM Sans', sans-serif;
    font-size: 14px;
    font-weight: 500;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all var(--transition);
  }

  .lp-tab.active {
    background: #fff;
    color: var(--brand);
    box-shadow: var(--shadow-sm);
    font-weight: 600;
  }

  /* ── HEADINGS ── */
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

  /* ── ALERT ── */
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

  .lp-alert.error   { background: #FEF2F2; color: var(--danger);  border: 1px solid #FECACA; }
  .lp-alert.success { background: #F0FFF4; color: var(--success); border: 1px solid #C6F6D5; }

  @keyframes shake {
    0%,100% { transform: translateX(0); }
    20%,60% { transform: translateX(-4px); }
    40%,80% { transform: translateX(4px); }
  }

  /* ── FIELDS ── */
  .lp-field { margin-bottom: 16px; }

  .lp-field label {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 6px;
    letter-spacing: .02em;
  }

  .lp-input-wrap { position: relative; }

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

  .lp-input::placeholder { color: #9CA3AF; }

  .lp-input:focus {
    border-color: var(--brand);
    box-shadow: 0 0 0 3px rgba(92,53,212,.12);
    background: #fff;
  }

  .lp-input.has-icon { padding-right: 44px; }
  .lp-input.input-err { border-color: var(--danger); }

  .lp-eye {
    position: absolute;
    right: 12px; top: 50%;
    transform: translateY(-50%);
    background: none; border: none;
    cursor: pointer; padding: 4px;
    color: var(--text-secondary);
    display: flex; align-items: center;
    transition: color var(--transition);
  }
  .lp-eye:hover { color: var(--brand); }

  /* ── PASSWORD STRENGTH ── */
  .pw-strength { margin-top: 6px; }
  .pw-bars { display: flex; gap: 4px; margin-bottom: 4px; }
  .pw-bar {
    flex: 1; height: 3px; border-radius: 4px;
    background: var(--border);
    transition: background .3s;
  }
  .pw-bar.weak   { background: #EF4444; }
  .pw-bar.fair   { background: #F59E0B; }
  .pw-bar.strong { background: var(--success); }
  .pw-label { font-size: 11.5px; color: var(--text-secondary); }

  /* ── FORGOT LINK ── */
  .lp-forgot-row {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 20px;
    margin-top: -8px;
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

  /* ── PRIMARY BUTTON ── */
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
    box-shadow: 0 4px 14px rgba(92,53,212,.35);
    display: flex; align-items: center; justify-content: center; gap: 8px;
  }

  .lp-btn:hover:not(:disabled) {
    opacity: .92;
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(92,53,212,.4);
  }

  .lp-btn:active:not(:disabled) { transform: translateY(0); }
  .lp-btn:disabled { opacity: .65; cursor: not-allowed; transform: none; }

  /* ── SPINNER ── */
  .spinner {
    width: 16px; height: 16px;
    border: 2.5px solid rgba(255,255,255,.4);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin .7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── DEMO CREDENTIALS ── */
  .lp-demo {
    margin-top: 24px;
    border-top: 1px solid var(--border);
    padding-top: 20px;
  }

  .lp-demo-title {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .1em;
    color: var(--text-secondary);
    margin-bottom: 12px;
  }

  .lp-demo-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }

  .lp-demo-item {
    border: 1.5px solid var(--border);
    border-radius: 10px;
    padding: 12px 14px;
    cursor: pointer;
    transition: all var(--transition);
    background: var(--bg-input);
  }

  .lp-demo-item:hover {
    border-color: var(--brand);
    background: #F3F0FF;
    transform: translateY(-1px);
    box-shadow: var(--shadow-sm);
  }

  .lp-demo-role {
    display: block;
    font-size: 12px;
    font-weight: 700;
    color: var(--brand);
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: .06em;
  }

  .lp-demo-info {
    display: block;
    font-size: 11.5px;
    color: var(--text-secondary);
    line-height: 1.7;
  }

  /* ── SUCCESS STATE ── */
  .lp-success-box {
    text-align: center;
    padding: 20px 0;
  }

  .lp-success-icon {
    font-size: 52px;
    margin-bottom: 16px;
    display: block;
    animation: popIn .4s cubic-bezier(.175,.885,.32,1.275);
  }

  @keyframes popIn {
    from { transform: scale(0.5); opacity: 0; }
    to   { transform: scale(1);   opacity: 1; }
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

  /* ── MODAL ── */
  .lp-overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,.45);
    backdrop-filter: blur(4px);
    display: flex; align-items: center; justify-content: center;
    z-index: 999;
    animation: fadeIn .2s ease;
  }

  @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }

  .lp-modal {
    background: #fff;
    border-radius: 18px;
    padding: 36px 40px;
    width: 100%;
    max-width: 400px;
    box-shadow: 0 20px 60px rgba(0,0,0,.2);
    animation: slideUp .3s ease;
  }

  .lp-modal h3 {
    font-family: 'Playfair Display', serif;
    font-size: 22px;
    color: var(--text-primary);
    margin-bottom: 8px;
  }

  .lp-modal p {
    font-size: 14px;
    color: var(--text-secondary);
    margin-bottom: 20px;
  }

  .lp-modal-btns { display: flex; gap: 10px; margin-top: 16px; }

  .lp-btn-cancel {
    flex: 1; padding: 11px;
    border: 1.5px solid var(--border);
    border-radius: var(--radius);
    background: #fff;
    font-family: 'DM Sans', sans-serif;
    font-size: 14px; font-weight: 500;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all var(--transition);
  }
  .lp-btn-cancel:hover { border-color: var(--brand); color: var(--brand); }

  .lp-btn-send {
    flex: 1; padding: 11px;
    border: none;
    border-radius: var(--radius);
    background: linear-gradient(135deg, var(--brand), var(--brand-light));
    color: #fff;
    font-family: 'DM Sans', sans-serif;
    font-size: 14px; font-weight: 600;
    cursor: pointer;
    transition: opacity var(--transition);
  }
  .lp-btn-send:hover { opacity: .88; }

  /* ── DIVIDER ── */
  .lp-or {
    display: flex; align-items: center; gap: 12px;
    font-size: 12px; color: var(--text-secondary);
    margin: 20px 0;
  }
  .lp-or::before, .lp-or::after {
    content: ''; flex: 1;
    height: 1px; background: var(--border);
  }

  /* ── RESPONSIVE ── */
  @media (max-width: 768px) {
    .lp-left { display: none; }
    .lp-mobile-logo { display: flex; }
    .lp-card { padding: 28px 24px; box-shadow: none; border-radius: 16px; }
    .lp-right { padding: 24px 16px; background: #F3F0FF; align-items: flex-start; padding-top: 40px; }
  }
`

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

/* ── Password Strength ── */
function getStrength(pw) {
  let score = 0
  if (pw.length >= 6) score++
  if (pw.length >= 10) score++
  if (/[A-Z]/.test(pw) && /[0-9]/.test(pw)) score++
  return score // 0 = none, 1 = weak, 2 = fair, 3 = strong
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
  const [regData, setRegData] = useState({ full_name: '', email: '', password: '', confirm_password: '' })
  const [showRegPw, setShowRegPw] = useState(false)
  const [showConfirmPw, setShowConfirmPw] = useState(false)
  const [regError, setRegError] = useState('')
  const [regSuccess, setRegSuccess] = useState(false)
  const [regLoading, setRegLoading] = useState(false)
  const [privacyConsent, setPrivacyConsent] = useState(false)

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
      const res = await fetch(`${API_BASE_URL}/api/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      })
      const data = await res.json()

      if (!res.ok) {
        setLoginError(data.error || 'Invalid email or password')
        return
      }

      setSession(data.user, data.token)
      navigate(data.user.role === 'admin' ? '/admin/dashboard' : '/student/dashboard')
    } catch {
      setLoginError('Cannot connect to server. Please try again.')
    } finally {
      setLoginLoading(false)
    }
  }, [loginData, navigate])

  // ── REGISTER HANDLER ──
  const handleRegister = useCallback(async () => {
    setRegError('')
    const { full_name, email, password, confirm_password } = regData

    if (!full_name.trim())                    { setRegError('Full name is required'); return }
    if (!email.trim())                        { setRegError('Email is required'); return }
    if (!/\S+@\S+\.\S+/.test(email))         { setRegError('Enter a valid email address'); return }
    if (!password)                            { setRegError('Password is required'); return }
    if (password.length < 6)                  { setRegError('Password must be at least 6 characters'); return }
    if (getStrength(password) < 1)            { setRegError('Please choose a stronger password'); return }
    if (password !== confirm_password)        { setRegError('Passwords do not match'); return }
    if (!privacyConsent)                      {setRegError('You must agree to the Data Privacy Act to create an account');return}

    setRegLoading(true)
    try {
      const res = await fetch(`${API_BASE_URL}/api/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: full_name.trim(), email: email.trim().toLowerCase(), password })
      })
      const data = await res.json()

      if (!res.ok) {
        setRegError(data.error || 'Registration failed. Please try again.')
        return
      }

      setRegSuccess(true)
    } catch {
      setRegError('Cannot connect to server. Please try again.')
    } finally {
      setRegLoading(false)
    }
  }, [regData, privacyConsent])

  // ── FORGOT HANDLER ──
  const handleForgot = useCallback(async () => {
    setForgotError('')
    if (!forgotEmail.trim())                  { setForgotError('Email is required'); return }
    if (!/\S+@\S+\.\S+/.test(forgotEmail))   { setForgotError('Enter a valid email address'); return }

    setForgotLoading(true)
    // Simulate API call — replace with real endpoint when available
    await new Promise(r => setTimeout(r, 1200))
    setForgotLoading(false)
    setForgotSent(true)
  }, [forgotEmail])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') tab === 'login' ? handleLogin() : handleRegister()
  }

  return (
    <>
      <style>{css}</style>
      <div className="lp-page">

        {/* ── LEFT ── */}
        <div className="lp-left">
          <div className="lp-blob b1" />
          <div className="lp-blob b2" />
          <div className="lp-blob b3" />
          <div className="lp-brand">
            <h1 className="lp-name">EcoScholar</h1>
            <p className="lp-tagline">
              Centralized Scholarship Allocation &amp; Automated Disbursement System
            </p>
          </div>
          <div className="lp-quote">
            "Empowering students through fair and transparent scholarship distribution."
          </div>
        </div>

        {/* ── RIGHT ── */}
        <div className="lp-right">
          <div className="lp-card">

            {/* Mobile logo */}
            <div className="lp-mobile-logo">
              <span>EcoScholar</span>
            </div>

            {/* Tabs */}
            <div className="lp-tabs">
              <button className={`lp-tab ${tab === 'login' ? 'active' : ''}`} onClick={() => switchTab('login')}>
                Sign In
              </button>
              <button className={`lp-tab ${tab === 'register' ? 'active' : ''}`} onClick={() => switchTab('register')}>
                Create Account
              </button>
            </div>

            {/*  LOGIN FORM  */}
            {tab === 'login' && (
              <>
                <h2 className="lp-title">Welcome back!</h2>
                <p className="lp-sub">Sign in to your account to continue</p>

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
                  {loginLoading ? <><span className="spinner" /> Signing in…</> : 'Sign In'}
                </button>

                <div className="lp-demo">
                  <p className="lp-demo-title">Demo credentials</p>
                  <div className="lp-demo-grid">
                    <div className="lp-demo-item" onClick={() => setLoginData({ email: 'admin@ecoscolar.edu.ph', password: 'admin123' })}>
                      <span className="lp-demo-role">Admin</span>
                      <span className="lp-demo-info">admin@ecoscolar.edu.ph</span>
                      <span className="lp-demo-info">admin123</span>
                    </div>
                    <div className="lp-demo-item" onClick={() => setLoginData({ email: 'student@gmail.com', password: 'student123' })}>
                      <span className="lp-demo-role">Student</span>
                      <span className="lp-demo-info">student@gmail.com</span>
                      <span className="lp-demo-info">student123</span>
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* REGISTER FORM */}
            {tab === 'register' && (
              <>
                {regSuccess ? (
                  <div className="lp-success-box">
                    <h2>Account Created</h2>
                    <p>Your student account has been registered successfully. You can now sign in.</p>
                    <button className="lp-btn" onClick={() => {
                      setTab('login')
                      setRegSuccess(false)
                      setRegData({ full_name: '', email: '', password: '', confirm_password: '' })
                    }}>
                      Go to Sign In
                    </button>
                  </div>
                ) : (
                  <>
                    <h2 className="lp-title">Create Account</h2>
                    <p className="lp-sub">Register as a student to apply for scholarships</p>

                    {regError && <div className="lp-alert error">{regError}</div>}

                    <div className="lp-field">
                      <label>Full Name</label>
                      <input
                        className="lp-input"
                        type="text"
                        placeholder="Enter your full name"
                        value={regData.full_name}
                        autoComplete="name"
                        onChange={e => { setRegData(p => ({ ...p, full_name: e.target.value })); setRegError('') }}
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
                          placeholder="At least 6 characters"
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
                        color: 'var(--color-text-secondary)',
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
                  </>
                )}
              </>
            )}

          </div>
        </div>

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

      </div>
    </>
  )
}

export default Login