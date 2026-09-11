import { useState, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { API_BASE_URL, setSession } from '../api'
import { GraduationCapIcon } from '../components/NavIcons'
import studentBg from '../assets/student-bg.jpg'

const css = `
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Playfair+Display:wght@700&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --brand:       #3d6fa3;
    --brand-light: #6fa0d4;
    --brand-dark:  #2c5580;
    --danger:      #E53E3E;
    --success:     #38A169;
    --text-primary:   #1A1A2E;
    --text-secondary: #4b5563;
    --border:      #E5E7EB;
    --bg-card:     #FFFFFF;
    --bg-input:    #F9FAFB;
    --radius:      12px;
    --shadow-sm:   0 1px 3px rgba(0,0,0,.08);
    --shadow-md:   0 4px 20px rgba(0,0,0,.10);
    --shadow-lg:   0 10px 40px rgba(61,111,163,.18);
    --transition:  .2s cubic-bezier(.4,0,.2,1);
  }

  body { font-family: 'DM Sans', sans-serif; }

  /* ── PAGE ── */
  .lp-page {
    display: flex;
    min-height: 100vh;
    background: #eaf0f7 url(${studentBg}) center/cover no-repeat;
  }

  /* ── LEFT PANEL ── */
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
    font-size: 38px;
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
    transition: max-width .2s ease;
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
    background: #eaf0f7;
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
  .lp-card-wide { max-width: 760px; }

  .lp-form-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0 20px; }
  @media (max-width: 640px) { .lp-form-grid-2 { grid-template-columns: 1fr; } }

  .lp-section-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--brand);
    text-transform: uppercase;
    letter-spacing: .04em;
    margin: 22px 0 12px;
  }
  .lp-section-title:first-of-type { margin-top: 4px; }

  .lp-subsection-title {
    font-size: 12.5px;
    font-weight: 600;
    color: var(--text-secondary);
    margin: 14px 0 8px;
  }
  .lp-subsection-title:first-of-type { margin-top: 0; }

  .lp-step-indicator {
    font-size: 12.5px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 4px;
  }

  select.lp-input { cursor: pointer; }

  .lp-radio-group { display: flex; flex-direction: column; gap: 8px; }
  .lp-radio-option {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 13.5px;
    color: var(--text-primary);
    cursor: pointer;
  }
  .lp-radio-option input { margin-top: 3px; accent-color: var(--brand); flex-shrink: 0; }

  .lp-field-err { font-size: 12px; color: var(--danger); margin-top: 4px; }

  .lp-step-btns { display: flex; gap: 12px; margin-top: 4px; }
  .lp-step-btns .lp-btn { width: auto; flex: 1; }
  .lp-btn-back {
    flex: 0 0 auto;
    padding: 13px 22px;
    border-radius: var(--radius);
    border: 1.5px solid var(--border);
    background: #fff;
    color: var(--text-primary);
    font-weight: 600;
    font-size: 14.5px;
    cursor: pointer;
    transition: background var(--transition);
  }
  .lp-btn-back:hover { background: var(--bg-input); }

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

  .lp-input::placeholder { color: #4b5563; }

  .lp-input:focus {
    border-color: var(--brand);
    box-shadow: 0 0 0 3px rgba(61,111,163,.12);
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

  /* ── SPINNER ── */
  .spinner {
    width: 16px; height: 16px;
    border: 2.5px solid rgba(255,255,255,.4);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin .7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

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
    .lp-right { padding: 24px 16px; background: rgba(234,240,247,.55); align-items: flex-start; padding-top: 40px; }
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
  else if (d.monthlyIncome < 0) errors.monthlyIncome = 'Enter a valid amount'
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
      navigate(data.user.role === 'student' ? '/student/dashboard' : '/admin/dashboard')
    } catch {
      setLoginError('Cannot connect to server. Please try again.')
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
      const res = await fetch(`${API_BASE_URL}/api/organizations/lookup?code=${encodeURIComponent(code)}`)
      const data = await res.json()
      if (!res.ok) {
        setJoinCodeError(data.error || "That join code isn't valid. Check it with your LGU and try again.")
        return
      }
      setJoinCodeOrgName(data.organization.name)
    } catch {
      setJoinCodeError('Cannot connect to server. Please try again.')
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
      const res = await fetch(`${API_BASE_URL}/api/register`, {
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
      setRegError('Cannot connect to server. Please try again.')
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
      const res = await fetch(`${API_BASE_URL}/api/register/verify-otp`, {
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
      setRegOtpError('Cannot connect to server. Please try again.')
    } finally {
      setRegOtpLoading(false)
    }
  }, [regData.email, regOtpCode, navigate])

  const handleResendRegOtp = useCallback(async () => {
    setRegResendMessage('')
    setRegResendLoading(true)
    try {
      await fetch(`${API_BASE_URL}/api/register/resend-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: regData.email.trim().toLowerCase() })
      })
      setRegResendMessage('A new code has been sent to your email.')
    } catch {
      setRegResendMessage('Cannot connect to server. Please try again.')
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
      await fetch(`${API_BASE_URL}/api/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: forgotEmail.trim().toLowerCase() })
      })
      // The API always responds the same way regardless of whether the email
      // exists, so there's nothing to branch on here - just show the sent state.
      setForgotSent(true)
    } catch {
      setForgotError('Cannot connect to server. Please try again.')
    }
    setForgotLoading(false)
  }, [forgotEmail])

  const handleKeyDown = (e) => {
    if (e.key !== 'Enter') return
    if (tab === 'login') handleLogin()
    else if (regStep === 1) handleRegNext()
    else handleRegister()
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

        {/* ── RIGHT ── */}
        <div className="lp-right">
          <div className={`lp-card${tab === 'register' && regStep === 2 ? ' lp-card-wide' : ''}`}>

            {/* Mobile logo */}
            <div className="lp-mobile-logo">
              <GraduationCapIcon width={24} height={24} />
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
                        <label>Monthly Household Income (₱)</label>
                        <input
                          className={`lp-input${regFieldErrors.monthlyIncome ? ' input-err' : ''}`}
                          type="number" placeholder="e.g. 15000" min="0" step="1"
                          value={regData.monthlyIncome}
                          onChange={e => { setRegData(p => ({ ...p, monthlyIncome: e.target.value })); setRegError('') }} />
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