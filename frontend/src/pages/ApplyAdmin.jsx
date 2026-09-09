import { useState, useCallback, useEffect } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { API_BASE_URL, setSession } from '../api'
import { GraduationCapIcon } from '../components/NavIcons'

// Reached only after verifying a one-time code sent to the applicant's email
// (see the "Apply for admin access" modal on the login page) - the token in
// the URL proves that verification already happened, it isn't itself a secret
// link mailed out.
const css = `
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Playfair+Display:wght@700&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --brand:       #3d6fa3;
    --brand-light: #6fa0d4;
    --brand-dark:  #2c5580;
    --danger:      #E53E3E;
    --text-primary:   #1A1A2E;
    --text-secondary: #6B7280;
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
    background: #eaf0f7;
  }

  .lp-left {
    flex: 0 0 420px;
    background: linear-gradient(145deg, var(--brand-dark) 0%, var(--brand) 50%, #5f8fc4 100%);
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

  .lp-input::placeholder { color: #9CA3AF; }

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
    .lp-right { padding: 24px 16px; background: #eaf0f7; align-items: flex-start; padding-top: 40px; }
  }
`

// Municipalities currently served - keep in sync with the list in Login.jsx.
const ADDRESS_CITIES = [
  { city: 'Liliw', province: 'Laguna' },
  { city: 'Tiaong', province: 'Quezon' },
]

const EMPTY_ADMIN_REQUEST = {
  fullName: '', password: '', confirmPassword: '', office: '', municipality: '', contactNumber: '', message: '',
}

function ApplyAdmin() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') || ''

  // 'checking' | 'invalid' | 'ready'
  const [tokenStatus, setTokenStatus] = useState(() => token ? 'checking' : 'invalid')
  const [tokenError, setTokenError] = useState(() => token ? '' : 'This link is missing its token.')
  const [verifiedEmail, setVerifiedEmail] = useState('')
  // 'apply' (public request, needs review) or 'invite' (an admin already
  // created the account and chose its role/permissions - this just needs a
  // password to activate it, no review step).
  const [mode, setMode] = useState('apply')
  const [inviteInfo, setInviteInfo] = useState(null)

  const [data, setData] = useState(EMPTY_ADMIN_REQUEST)
  const [proofFile, setProofFile] = useState(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!token) return

    fetch(`${API_BASE_URL}/api/admin-requests/verify-token?token=${encodeURIComponent(token)}`)
      .then(async res => {
        const result = await res.json()
        if (!res.ok) { setTokenStatus('invalid'); setTokenError(result.error || 'This link is invalid.'); return }
        setVerifiedEmail(result.email)
        setMode(result.mode === 'invite' ? 'invite' : 'apply')
        if (result.mode === 'invite') {
          setInviteInfo({ fullName: result.full_name, office: result.office, municipality: result.municipality, role: result.role })
        }
        setTokenStatus('ready')
      })
      .catch(() => { setTokenStatus('invalid'); setTokenError('Cannot connect to server. Please try again.') })
  }, [token])

  const handleSubmit = useCallback(async () => {
    setError('')
    const { fullName, password, confirmPassword, office, municipality, contactNumber } = data

    if (!password)             { setError('Password is required'); return }
    if (password.length < 8)  { setError('Password must be at least 8 characters'); return }
    if (password !== confirmPassword) { setError('Passwords do not match'); return }

    if (mode === 'invite') {
      setLoading(true)
      try {
        const res = await fetch(`${API_BASE_URL}/api/admins/complete-invite-setup`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token, new_password: password })
        })
        const result = await res.json()
        if (!res.ok) {
          setError(result.error || 'Failed to activate your account. Please try again.')
          return
        }
        setSession(result.user, result.token)
        navigate(result.user.role === 'student' ? '/student/dashboard' : '/admin/dashboard')
      } catch {
        setError('Cannot connect to server. Please try again.')
      } finally {
        setLoading(false)
      }
      return
    }

    if (!fullName.trim())      { setError('Full name is required'); return }
    if (!office.trim())        { setError('Office / position is required'); return }
    if (!municipality)         { setError('Municipality is required'); return }
    if (!contactNumber.trim()) { setError('Contact number is required'); return }
    else if (!/^09\d{9}$/.test(contactNumber.replace(/\s/g, '')))
      { setError('Enter a valid PH number (e.g. 09123456789)'); return }
    if (!proofFile) { setError('Upload a valid ID or proof-of-employment document'); return }

    setLoading(true)
    try {
      const formData = new FormData()
      formData.append('token', token)
      formData.append('full_name', fullName.trim())
      formData.append('password', password)
      formData.append('office', office.trim())
      formData.append('municipality', municipality)
      formData.append('contact_number', contactNumber.trim())
      formData.append('message', data.message.trim())
      formData.append('file', proofFile)

      const res = await fetch(`${API_BASE_URL}/api/admin-requests`, {
        method: 'POST',
        body: formData
      })
      const result = await res.json()

      if (!res.ok) {
        setError(result.error || 'Failed to submit request. Please try again.')
        return
      }

      setSuccess(true)
    } catch {
      setError('Cannot connect to server. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [data, proofFile, token, mode, navigate])

  const handleKeyDown = (e) => { if (e.key === 'Enter') handleSubmit() }

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

            {tokenStatus === 'checking' ? (
              <div className="lp-success-box">
                <h2>Checking your link…</h2>
              </div>
            ) : tokenStatus === 'invalid' ? (
              <div className="lp-success-box">
                <h2>Session Invalid</h2>
                <p>{tokenError} Go back to the sign-up page and use "Apply for admin access" to verify your email again.</p>
                <Link className="lp-btn" to="/login" style={{ textDecoration: 'none', display: 'flex' }}>
                  Back to Sign In
                </Link>
              </div>
            ) : success ? (
              <div className="lp-success-box">
                <h2>Request Submitted</h2>
                <p>
                  Thanks — an existing EcoScholar admin will verify your details.
                  If approved, you can sign in right away at <strong>{verifiedEmail}</strong> with
                  the password you just set.
                </p>
                <Link className="lp-btn" to="/login" style={{ textDecoration: 'none', display: 'flex' }}>
                  Back to Sign In
                </Link>
              </div>
            ) : mode === 'invite' ? (
              <>
                <h2 className="lp-title">Activate Your Account</h2>
                <p className="lp-sub">
                  Welcome, <strong>{inviteInfo?.fullName}</strong> — {inviteInfo?.office ? `${inviteInfo.office}, ` : ''}
                  {inviteInfo?.municipality ? `${inviteInfo.municipality}. ` : ''}
                  Choose a password for <strong>{verifiedEmail}</strong> to finish setting up your account.
                </p>

                {error && <div className="lp-alert error">{error}</div>}

                <div className="lp-field">
                  <label>Password</label>
                  <input
                    className="lp-input"
                    type="password"
                    placeholder="At least 8 characters"
                    value={data.password}
                    autoComplete="new-password"
                    onChange={e => { setData(p => ({ ...p, password: e.target.value })); setError('') }}
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
                    value={data.confirmPassword}
                    autoComplete="new-password"
                    onChange={e => { setData(p => ({ ...p, confirmPassword: e.target.value })); setError('') }}
                    onKeyDown={handleKeyDown}
                  />
                  {data.confirmPassword && data.confirmPassword !== data.password && (
                    <p style={{ fontSize: '12px', color: 'var(--danger)', marginTop: '4px' }}>Passwords do not match</p>
                  )}
                </div>

                <button className="lp-btn" onClick={handleSubmit} disabled={loading}>
                  {loading ? <><span className="spinner" /> Activating…</> : 'Activate Account'}
                </button>
              </>
            ) : (
              <>
                <h2 className="lp-title">Apply as Admin</h2>
                <p className="lp-sub">Applying as <strong>{verifiedEmail}</strong></p>

                {error && <div className="lp-alert error">{error}</div>}

                <div className="lp-field">
                  <label>Full Name</label>
                  <input
                    className="lp-input"
                    type="text"
                    placeholder="Full name"
                    value={data.fullName}
                    autoComplete="name"
                    onChange={e => { setData(p => ({ ...p, fullName: e.target.value })); setError('') }}
                    onKeyDown={handleKeyDown}
                  />
                </div>

                <div className="lp-field">
                  <label>Password</label>
                  <input
                    className="lp-input"
                    type="password"
                    placeholder="At least 8 characters"
                    value={data.password}
                    autoComplete="new-password"
                    onChange={e => { setData(p => ({ ...p, password: e.target.value })); setError('') }}
                    onKeyDown={handleKeyDown}
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
                    onChange={e => { setData(p => ({ ...p, confirmPassword: e.target.value })); setError('') }}
                    onKeyDown={handleKeyDown}
                  />
                  {data.confirmPassword && data.confirmPassword !== data.password && (
                    <p style={{ fontSize: '12px', color: 'var(--danger)', marginTop: '4px' }}>Passwords do not match</p>
                  )}
                </div>

                <div className="lp-field">
                  <label>Office / Position</label>
                  <input
                    className="lp-input"
                    type="text"
                    placeholder="e.g. Municipal Social Welfare and Development Office"
                    value={data.office}
                    onChange={e => { setData(p => ({ ...p, office: e.target.value })); setError('') }}
                    onKeyDown={handleKeyDown}
                  />
                </div>

                <div className="lp-field">
                  <label>Municipality</label>
                  <select
                    className="lp-input"
                    value={data.municipality}
                    onChange={e => { setData(p => ({ ...p, municipality: e.target.value })); setError('') }}>
                    <option value="">Select city / municipality</option>
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
                    placeholder="09123456789"
                    value={data.contactNumber}
                    onChange={e => { setData(p => ({ ...p, contactNumber: e.target.value })); setError('') }}
                    onKeyDown={handleKeyDown}
                  />
                </div>

                <div className="lp-field">
                  <label>Reason for Request <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}>(optional)</span></label>
                  <textarea
                    className="lp-input"
                    rows={3}
                    placeholder="Briefly describe your role in the scholarship program"
                    value={data.message}
                    onChange={e => { setData(p => ({ ...p, message: e.target.value })); setError('') }}
                  />
                </div>

                <div className="lp-field">
                  <label>Valid ID or Proof of Employment</label>
                  <p style={{ fontSize: '12.5px', color: 'var(--text-secondary)', margin: '-2px 0 8px' }}>
                    An appointment letter, employee ID, or contract of service (COS) - PDF, JPG, or PNG, up to 5MB.
                    A reviewing admin checks this before approving your request.
                  </p>
                  <input
                    className="lp-input"
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png"
                    onChange={e => { setProofFile(e.target.files[0] || null); setError('') }}
                  />
                  {proofFile && (
                    <p style={{ fontSize: '12.5px', color: 'var(--brand)', marginTop: '6px' }}>
                      Selected: {proofFile.name}
                    </p>
                  )}
                </div>

                <button className="lp-btn" onClick={handleSubmit} disabled={loading}>
                  {loading ? <><span className="spinner" /> Submitting…</> : 'Submit Request'}
                </button>

                <p style={{ marginTop: '16px', textAlign: 'center', fontSize: '13.5px', color: 'var(--text-secondary)' }}>
                  Already have an account?{' '}
                  <Link className="lp-link" to="/login">Sign in here</Link>
                </p>
              </>
            )}
          </div>
        </div>

      </div>
    </>
  )
}

export default ApplyAdmin
