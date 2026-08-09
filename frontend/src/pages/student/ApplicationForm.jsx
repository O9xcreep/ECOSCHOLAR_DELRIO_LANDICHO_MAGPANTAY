import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../../api'
import './ApplicationForm.css'

// ── DATA ──
// These three lists must match the eligibility model's encoding exactly
// (see backend/schema/ml_model.md) - the values are one-hot/ordinal encoded
// by exact string match, so don't rename or reorder without updating the model too.
const EDUCATION_LEVELS = ['None', 'Elementary', 'High School', 'Vocational', 'College', 'Postgraduate']
const OCCUPATION_CATEGORIES = [
  'Unemployed', 'Informal/Vendor', 'Laborer/Driver', 'Skilled Trade',
  'Office/Clerical', 'Professional', 'Deceased/Not Applicable'
]
const HOUSING_SITUATIONS = ['Owned', 'Rented', 'Living with relatives', 'Informal settler']

const COURSES = [
  'BS Computer Science',
  'BS Information Technology',
  'BS Information Systems',
  'BS Nursing',
  'BS Midwifery',
  'BS Medical Technology',
  'BS Pharmacy',
  'BS Education (Elementary)',
  'BS Education (Secondary)',
  'BS Psychology',
  'BS Social Work',
  'BS Business Administration',
  'BS Accountancy',
  'BS Accounting Technology',
  'BS Entrepreneurship',
  'BS Hotel and Restaurant Management',
  'BS Tourism Management',
  'BS Civil Engineering',
  'BS Electrical Engineering',
  'BS Mechanical Engineering',
  'BS Electronics Engineering',
  'BS Computer Engineering',
  'BS Architecture',
  'BS Criminology',
  'BS Agriculture',
  'BS Forestry',
  'BS Marine Biology',
  'AB Communication',
  'AB Political Science',
  'AB English',
  'Others'
]

const RELIGIONS = [
  'Roman Catholic',
  'Iglesia ni Cristo',
  'Islam',
  'Born Again Christian',
  'Seventh Day Adventist',
  'Jesus Miracle Crusade',
  'Others'
]

const YEAR_LEVELS = ['1st Year', '2nd Year', '3rd Year', '4th Year', '5th Year']
const SEMESTERS = ['1st Semester', '2nd Semester', 'Summer']

// ── VALIDATE STEP 1 ──
function validateStep1(data) {
  const errors = {}
  if (!data.fullName.trim()) errors.fullName = 'Full name is required'
  if (!data.email.trim()) errors.email = 'Email is required'
  else if (!/\S+@\S+\.\S+/.test(data.email)) errors.email = 'Enter a valid email address'
  if (!data.address.trim()) errors.address = 'Address is required'
  if (!data.religion) errors.religion = 'Religion is required'
  if (!data.gender) errors.gender = 'Gender is required'
  if (!data.dob) errors.dob = 'Date of birth is required'
  if (!data.citizenship.trim()) errors.citizenship = 'Citizenship is required'
  if (!data.contactNumber.trim()) errors.contactNumber = 'Contact number is required'
  else if (!/^09\d{9}$/.test(data.contactNumber.replace(/\s/g, '')))
    errors.contactNumber = 'Enter a valid PH number (e.g. 09123456789)'
  if (!data.fatherName.trim()) errors.fatherName = "Father's name is required"
  if (!data.fatherOccupation) errors.fatherOccupation = "Father's occupation is required"
  if (!data.fatherEducation) errors.fatherEducation = "Father's education level is required"
  if (!data.motherName.trim()) errors.motherName = "Mother's name is required"
  if (!data.motherOccupation) errors.motherOccupation = "Mother's occupation is required"
  if (!data.motherEducation) errors.motherEducation = "Mother's education level is required"
  if (!data.monthlyIncome) errors.monthlyIncome = 'Monthly household income is required'
  else if (data.monthlyIncome < 0) errors.monthlyIncome = 'Enter a valid amount'
  if (!data.familySize) errors.familySize = 'Family size is required'
  else if (data.familySize < 1 || data.familySize > 20)
    errors.familySize = 'Enter a valid family size (1-20)'
  if (data.numSiblings === '') errors.numSiblings = 'Number of siblings is required'
  else if (data.numSiblings < 0 || data.numSiblings > 20)
    errors.numSiblings = 'Enter a valid number (0-20)'
  if (data.numSiblingsStudying === '') errors.numSiblingsStudying = 'This field is required'
  else if (data.numSiblingsStudying < 0 || Number(data.numSiblingsStudying) > Number(data.numSiblings || 0))
    errors.numSiblingsStudying = 'Cannot exceed total number of siblings'
  if (!data.housingSituation) errors.housingSituation = 'Housing situation is required'
  if (!data.hasOtherScholarship) errors.hasOtherScholarship = 'Please indicate if you have other scholarships'
  if (data.hasOtherScholarship === 'Yes' && !data.otherScholarshipDetails.trim()) {
    errors.otherScholarshipDetails = 'Please provide details about your other scholarships'
  }
  return errors
}

// ── VALIDATE STEP 2 ──
function validateStep2(data) {
  const errors = {}
  if (!data.school.trim()) errors.school = 'School name is required'
  if (!data.schoolAddress.trim()) errors.schoolAddress = 'School address is required'
  if (!data.course) errors.course = 'Course is required'
  if (!data.yearLevel) errors.yearLevel = 'Year level is required'
  if (!data.gpa) errors.gpa = 'GWA is required'
  else if (data.gpa < 75 || data.gpa > 99)
    errors.gpa = 'GWA must be between 75 and 99'
  if (!data.academicYear.trim()) errors.academicYear = 'Academic year is required'
  else if (!/^\d{4}-\d{4}$/.test(data.academicYear))
    errors.academicYear = 'Format must be e.g. 2025-2026'
  if (!data.semester) errors.semester = 'Semester is required'
  return errors
}

// ── VALIDATE STEP 3 ──
function validateStep3(data, consent) {
  const errors = {}
  const required = [
    { key: 'enrollmentForm', label: 'Enrollment Form' },
    { key: 'barangayEndorsement', label: 'Barangay Endorsement' },
    { key: 'schoolId', label: 'School ID' },
    { key: 'grade12', label: 'Grade 12 Grades' },
    { key: 'proofOfIncome', label: 'Proof of Income' },
  ]
  required.forEach(({ key, label }) => {
    if (!data[key]) errors[key] = `${label} is required`
  })
  if (!consent) errors.privacyConsent = 'You must agree to the Data Privacy Act to submit'
  return errors
}

// ── STEP INDICATOR ──
function StepIndicator({ currentStep }) {
  const steps = ['Personal Info', 'Academic Info', 'Requirements']
  return (
    <div className="step-indicator">
      {steps.map((step, index) => (
        <div key={index} className="step-wrapper">
          <div className={`step-circle 
            ${currentStep === index + 1 ? 'active' : ''} 
            ${currentStep > index + 1 ? 'done' : ''}`}>
            {index + 1}
          </div>
          <span className={`step-label ${currentStep === index + 1 ? 'active' : ''}`}>
            {step}
          </span>
          {index < steps.length - 1 && (
            <div className={`step-line ${currentStep > index + 1 ? 'done' : ''}`} />
          )}
        </div>
      ))}
    </div>
  )
}

// ── FIELD COMPONENT ──
function Field({ label, error, children }) {
  return (
    <div className="form-group">
      <label>{label}</label>
      {children}
      {error && <span className="error-msg">{error}</span>}
    </div>
  )
}

// ── STEP 1 ──
function Step1({ data, onChange, errors }) {
  return (
    <div className="step-content">
      <h2>Step 1: Personal Information</h2>

      <div className="form-section">
        <h3 className="section-title">Core Identity</h3>
        <div className="form-grid-2">

          <Field label="Full Name" error={errors.fullName}>
            <input
              className={errors.fullName ? 'input-error' : ''}
              type="text" placeholder="Enter your full name"
              value={data.fullName}
              onChange={e => onChange('fullName', e.target.value)} />
          </Field>

          {/* Email locked to logged-in account */}
          <Field label="Email Address" error={errors.email}>
            <input
              type="email"
              value={data.email}
              readOnly
              style={{
                background: '#F3F4F6',
                color: '#6B7280',
                cursor: 'not-allowed',
                border: '1.5px solid #E5E7EB'
              }}
              title="Email is tied to your account and cannot be changed"
            />
            <span style={{ fontSize: '11.5px', color: '#9CA3AF', marginTop: '4px', display: 'block' }}>
              Linked to your account
            </span>
          </Field>

          <Field label="Address" error={errors.address}>
            <input
              className={`full ${errors.address ? 'input-error' : ''}`}
              type="text" placeholder="Street, City, Province"
              value={data.address}
              onChange={e => onChange('address', e.target.value)} />
          </Field>

          <Field label="Religion" error={errors.religion}>
            <select
              className={errors.religion ? 'input-error' : ''}
              value={data.religion}
              onChange={e => onChange('religion', e.target.value)}>
              <option value="">Select religion</option>
              {RELIGIONS.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </Field>

          <Field label="Gender" error={errors.gender}>
            <select
              className={errors.gender ? 'input-error' : ''}
              value={data.gender}
              onChange={e => onChange('gender', e.target.value)}>
              <option value="">Select gender</option>
              <option value="Male">Male</option>
              <option value="Female">Female</option>
            </select>
          </Field>

          <Field label="Date of Birth" error={errors.dob}>
            <input
              className={errors.dob ? 'input-error' : ''}
              type="date"
              value={data.dob}
              onChange={e => onChange('dob', e.target.value)} />
          </Field>

        </div>
      </div>

      <div className="form-section">
        <h3 className="section-title">Background Details</h3>
        <div className="form-grid-2">

          <Field label="Citizenship" error={errors.citizenship}>
            <input
              className={errors.citizenship ? 'input-error' : ''}
              type="text" placeholder="Filipino"
              value={data.citizenship}
              onChange={e => onChange('citizenship', e.target.value)} />
          </Field>

          <Field label="Contact Number" error={errors.contactNumber}>
            <input
              className={errors.contactNumber ? 'input-error' : ''}
              type="text" placeholder="09123456789"
              value={data.contactNumber}
              onChange={e => onChange('contactNumber', e.target.value)} />
          </Field>

        </div>
      </div>

      <div className="form-section">
        <h3 className="section-title">Parental Details</h3>
        <div className="form-grid-2">

          <Field label="Father's Name" error={errors.fatherName}>
            <input
              className={errors.fatherName ? 'input-error' : ''}
              type="text" placeholder="First M. Last"
              value={data.fatherName}
              onChange={e => onChange('fatherName', e.target.value)} />
          </Field>

          <Field label="Father's Occupation" error={errors.fatherOccupation}>
            <select
              className={errors.fatherOccupation ? 'input-error' : ''}
              value={data.fatherOccupation}
              onChange={e => onChange('fatherOccupation', e.target.value)}>
              <option value="">Select occupation</option>
              {OCCUPATION_CATEGORIES.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          </Field>

          <Field label="Father's Education Level" error={errors.fatherEducation}>
            <select
              className={errors.fatherEducation ? 'input-error' : ''}
              value={data.fatherEducation}
              onChange={e => onChange('fatherEducation', e.target.value)}>
              <option value="">Select education level</option>
              {EDUCATION_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
            </select>
          </Field>

          <Field label="Mother's Name" error={errors.motherName}>
            <input
              className={errors.motherName ? 'input-error' : ''}
              type="text" placeholder="First M. Last"
              value={data.motherName}
              onChange={e => onChange('motherName', e.target.value)} />
          </Field>

          <Field label="Mother's Occupation" error={errors.motherOccupation}>
            <select
              className={errors.motherOccupation ? 'input-error' : ''}
              value={data.motherOccupation}
              onChange={e => onChange('motherOccupation', e.target.value)}>
              <option value="">Select occupation</option>
              {OCCUPATION_CATEGORIES.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          </Field>

          <Field label="Mother's Education Level" error={errors.motherEducation}>
            <select
              className={errors.motherEducation ? 'input-error' : ''}
              value={data.motherEducation}
              onChange={e => onChange('motherEducation', e.target.value)}>
              <option value="">Select education level</option>
              {EDUCATION_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
            </select>
          </Field>

          <Field label="Estimated Monthly Household Income (₱)" error={errors.monthlyIncome}>
            <input
              className={errors.monthlyIncome ? 'input-error' : ''}
              type="number" placeholder="e.g. 15000" min="0" step="1"
              value={data.monthlyIncome}
              onChange={e => onChange('monthlyIncome', e.target.value)} />
          </Field>

          <Field label="Housing Situation" error={errors.housingSituation}>
            <select
              className={errors.housingSituation ? 'input-error' : ''}
              value={data.housingSituation}
              onChange={e => onChange('housingSituation', e.target.value)}>
              <option value="">Select housing situation</option>
              {HOUSING_SITUATIONS.map(h => <option key={h} value={h}>{h}</option>)}
            </select>
          </Field>

          <Field label="Family Size" error={errors.familySize}>
            <input
              className={errors.familySize ? 'input-error' : ''}
              type="number" placeholder="e.g. 5" min="1" max="20"
              value={data.familySize}
              onChange={e => onChange('familySize', e.target.value)} />
          </Field>

          <Field label="Number of Siblings" error={errors.numSiblings}>
            <input
              className={errors.numSiblings ? 'input-error' : ''}
              type="number" placeholder="e.g. 2" min="0" max="20"
              value={data.numSiblings}
              onChange={e => onChange('numSiblings', e.target.value)} />
          </Field>

          <Field label="Siblings Currently Studying" error={errors.numSiblingsStudying}>
            <input
              className={errors.numSiblingsStudying ? 'input-error' : ''}
              type="number" placeholder="e.g. 1" min="0" max="20"
              value={data.numSiblingsStudying}
              onChange={e => onChange('numSiblingsStudying', e.target.value)} />
          </Field>

        </div>
      </div>
      <div className="form-section">
        <h3 className="section-title">Scholarship Information</h3>
        <div className="form-grid-1">

          <Field
            label="Are you currently receiving any scholarship from barangay, city, or provincial level?"
            error={errors.hasOtherScholarship}>
            <div className="radio-group">
              <label className="radio-option">
                <input
                  type="radio"
                  name="hasOtherScholarship"
                  value="no"
                  checked={data.hasOtherScholarship === 'no'}
                  onChange={e => onChange('hasOtherScholarship', e.target.value)}
                />
                <span>No — I am not receiving any other scholarship</span>
              </label>
              <label className="radio-option">
                <input
                  type="radio"
                  name="hasOtherScholarship"
                  value="yes"
                  checked={data.hasOtherScholarship === 'yes'}
                  onChange={e => onChange('hasOtherScholarship', e.target.value)}
                />
                <span>Yes — I am currently receiving another scholarship</span>
              </label>
            </div>
          </Field>

          {data.hasOtherScholarship === 'yes' && (
            <Field
              label="Please specify which scholarship you are receiving"
              error={errors.otherScholarshipDetails}>
              <input
                className={errors.otherScholarshipDetails ? 'input-error' : ''}
                type="text"
                placeholder="e.g. Barangay San Jose Scholarship, CHED Scholarship, etc."
                value={data.otherScholarshipDetails}
                onChange={e => onChange('otherScholarshipDetails', e.target.value)}
              />
            </Field>
          )}

          {data.hasOtherScholarship === 'yes' && (
            <div className="scholarship-warning">
              <p>
                <strong>Important:</strong> Receiving multiple scholarships
                from different government levels may affect your eligibility.
                Your application will be flagged for review by the admin.
              </p>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}

// ── STEP 2 ──
function Step2({ data, onChange, errors }) {
  return (
    <div className="step-content">
      <h2>Step 2: Academic Information</h2>
      <div className="form-section">
        <h3 className="section-title">Academic Details</h3>
        <div className="form-grid-1">

          <Field label="College / University" error={errors.school}>
            <input
              className={errors.school ? 'input-error' : ''}
              type="text" placeholder="Enter your school name"
              value={data.school}
              onChange={e => onChange('school', e.target.value)} />
          </Field>

          <Field label="School Address" error={errors.schoolAddress}>
            <input
              className={errors.schoolAddress ? 'input-error' : ''}
              type="text" placeholder="Street, City, Province"
              value={data.schoolAddress}
              onChange={e => onChange('schoolAddress', e.target.value)} />
          </Field>

          <Field label="Course" error={errors.course}>
            <select
              className={errors.course ? 'input-error' : ''}
              value={data.course}
              onChange={e => onChange('course', e.target.value)}>
              <option value="">Select your course</option>
              {COURSES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>

          <Field label="Year Level" error={errors.yearLevel}>
            <select
              className={errors.yearLevel ? 'input-error' : ''}
              value={data.yearLevel}
              onChange={e => onChange('yearLevel', e.target.value)}>
              <option value="">Select year level</option>
              {YEAR_LEVELS.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </Field>

          <Field label="GWA (Percentage Scale)" error={errors.gpa}>
            <input
              className={errors.gpa ? 'input-error' : ''}
              type="number" placeholder="e.g. 88.5"
              step="0.01" min="75" max="99"
              value={data.gpa}
              onChange={e => onChange('gpa', e.target.value)} />
            <span style={{ fontSize: '11.5px', color: '#9CA3AF', marginTop: '4px', display: 'block' }}>
              Your Grade 12 GWA (or latest GWA), on the 75-99 percentage scale
            </span>
          </Field>

          <Field label="Academic Year" error={errors.academicYear}>
            <input
              className={errors.academicYear ? 'input-error' : ''}
              type="text" placeholder="e.g. 2025-2026"
              value={data.academicYear}
              onChange={e => onChange('academicYear', e.target.value)} />
          </Field>

          <Field label="Semester" error={errors.semester}>
            <select
              className={errors.semester ? 'input-error' : ''}
              value={data.semester}
              onChange={e => onChange('semester', e.target.value)}>
              <option value="">Select semester</option>
              {SEMESTERS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>

        </div>
      </div>
    </div>
  )
}

// ── STEP 3 ──
function Step3({ data, onChange, errors, consent, onConsentChange }) {
  const requirements = [
    { key: 'enrollmentForm', label: 'Copy of Enrollment Form', required: true },
    { key: 'barangayEndorsement', label: 'Copy of Barangay Endorsement', required: true },
    { key: 'schoolId', label: 'School ID', required: true },
    { key: 'grade12', label: 'Copy of Grade 12 Grades', required: true },
    { key: 'fourPsCert', label: 'If 4Ps member, 1 copy of 4Ps Certificate', required: false },
    { key: 'proofOfIncome', label: 'Proof of Income (Certificate of Indig ency)', required: true },
  ]

  return (
    <div className="step-content">
      <h2>Requirements</h2>
      <p className="req-note">Fields marked with <span className="req-star">*</span> are required.</p>
      <div className="form-section">
        {requirements.map(req => (
          <div key={req.key} className="upload-group">
            <label>
              {req.label}
              {req.required && <span className="req-star"> *</span>}
            </label>
            <div
              className={`upload-box ${errors[req.key] ? 'upload-error' : ''}`}
              onClick={() => document.getElementById(req.key).click()}>
              {data[req.key] ? (
                <span className="upload-filename">{data[req.key].name}</span>
              ) : (
                <span className="upload-placeholder">Click to upload (PDF, JPG, PNG)</span>
              )}
              <input
                type="file"
                id={req.key}
                style={{ display: 'none' }}
                accept=".pdf,.jpg,.jpeg,.png"
                onChange={e => onChange(req.key, e.target.files[0], req.label)}
              />
            </div>
            
            {errors[req.key] && (
              <span className="error-msg">{errors[req.key]}</span>
            )}
          </div>
        ))}
      {/* Data Privacy Consent */}
          <div className="privacy-consent-box">
              <div className="privacy-consent-inner">
                <input
                  type="checkbox"
                  id="privacyConsent"
                  checked={consent}
                  onChange={e => onConsentChange(e.target.checked)}
                  className="privacy-checkbox"
                />
                <label htmlFor="privacyConsent" className="privacy-label">
                  <span className="privacy-title">
                    Data Privacy Consent (RA 10173)
                  </span>
                  <span className="privacy-text">
                    I hereby consent to the collection, storage, and processing of my
                    personal information by the Local Government Unit for the purpose
                    of scholarship evaluation and grant distribution, in accordance
                    with the <strong>Data Privacy Act of 2012 (Republic Act No. 10173)</strong>.
                    I understand that my data will be kept confidential and used solely
                    for scholarship-related purposes.
                  </span>
                </label>
              </div>
              {errors.privacyConsent && (
                <span className="error-msg">{errors.privacyConsent}</span>
              )}
        </div>
      </div>
    </div>
  )
}

// ── MAIN FORM ──
function ApplicationForm() {
  const navigate = useNavigate()

  const user = JSON.parse(localStorage.getItem('user') || '{}')
  const lockedEmail = user.email || ''

  const [currentStep, setCurrentStep] = useState(1)
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [submitSuccess, setSubmitSuccess] = useState(false)
  const [existingApplication, setExistingApplication] = useState(null)
  const [duplicateReason, setDuplicateReason] = useState('')
  const [privacyConsent, setPrivacyConsent] = useState(false)
  const [autoFilling, setAutoFilling] = useState(false)
  const [autoFillResults, setAutoFillResults] = useState({})

  const [step1Data, setStep1Data] = useState({
   fullName: user.full_name || '',
    email: lockedEmail,
   address: '', religion: '',
   gender: '', dob: '', citizenship: 'Filipino',
   contactNumber: '', fatherName: '', fatherOccupation: '', fatherEducation: '',
   motherName: '', motherOccupation: '', motherEducation: '',
    monthlyIncome: '', familySize: '',
    numSiblings: '', numSiblingsStudying: '', housingSituation: '',
    hasOtherScholarship: '',
    otherScholarshipDetails: ''
  })

  const [step2Data, setStep2Data] = useState({
    school: '', schoolAddress: '', course: '',
    yearLevel: '', gpa: '', academicYear: '', semester: ''
  })

  const [step3Data, setStep3Data] = useState({
    enrollmentForm: null, barangayEndorsement: null,
    schoolId: null, grade12: null,
    fourPsCert: null, proofOfIncome: null
  })

  // Personal info collected at registration pre-fills Step 1 so it isn't retyped here.
  // Only blank fields are filled in, so anything the user has already started editing wins.
  useEffect(() => {
    (async () => {
      try {
        const res = await apiFetch('/api/profile')
        if (!res.ok) return
        const { profile } = await res.json()
        setStep1Data(prev => {
          const next = { ...prev }
          for (const key of Object.keys(profile)) {
            if (key === 'email') continue
            if (profile[key] && !next[key]) next[key] = profile[key]
          }
          return next
        })
      } catch {
        // profile pre-fill is a convenience, not required for the form to work
      }
    })()
  }, [])

  const handleStep1Change = (field, value) => {
    if (field === 'email') return
    setStep1Data(prev => ({ ...prev, [field]: value }))
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }))
  }

  const handleStep2Change = (field, value) => {
    setStep2Data(prev => ({ ...prev, [field]: value }))
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }))
  }

  const handleAutoFill = async (file, docLabel) => {
    if (!file) return
    setAutoFilling(true)

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('doc_type', docLabel)

      const response = await apiFetch('/api/ocr-autofill', {
        method: 'POST',
        body: formData
      })

      const data = await response.json()

      if (data.success && Object.keys(data.fields).length > 0) {
        const fields = data.fields

        // Auto-fill Step 1 fields
        if (fields.fullName && !step1Data.fullName)
          setStep1Data(prev => ({ ...prev, fullName: fields.fullName }))
        if (fields.address && !step1Data.address)
          setStep1Data(prev => ({ ...prev, address: fields.address }))
        if (fields.monthlyIncome && !step1Data.monthlyIncome)
          setStep1Data(prev => ({ ...prev, monthlyIncome: fields.monthlyIncome }))
        if (fields.fatherName && !step1Data.fatherName)
          setStep1Data(prev => ({ ...prev, fatherName: fields.fatherName }))
        if (fields.motherName && !step1Data.motherName)
          setStep1Data(prev => ({ ...prev, motherName: fields.motherName }))

        // Auto-fill Step 2 fields
        if (fields.school && !step2Data.school)
          setStep2Data(prev => ({ ...prev, school: fields.school }))
        if (fields.course && !step2Data.course)
          setStep2Data(prev => ({ ...prev, course: fields.course }))
        if (fields.yearLevel && !step2Data.yearLevel)
          setStep2Data(prev => ({ ...prev, yearLevel: fields.yearLevel }))
        if (fields.semester && !step2Data.semester)
          setStep2Data(prev => ({ ...prev, semester: fields.semester }))
        if (fields.academicYear && !step2Data.academicYear)
          setStep2Data(prev => ({ ...prev, academicYear: fields.academicYear }))
        if (fields.gpa && !step2Data.gpa)
          setStep2Data(prev => ({ ...prev, gpa: fields.gpa }))

        // Show what was filled
        setAutoFillResults(fields)
        setTimeout(() => setAutoFillResults({}), 5000)
      }

    } catch (err) {
      console.error('AutoFill error:', err)
    }
    setAutoFilling(false)
  }

  const handleStep3Change = (field, value, docLabel) => {
    setStep3Data(prev => ({ ...prev, [field]: value }))
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }))
    // Trigger OCR autofill
    if (value && docLabel) {
      handleAutoFill(value, docLabel)
    }
  }

  const handleNext = () => {
    let currentErrors = {}
    if (currentStep === 1) currentErrors = validateStep1(step1Data)
    if (currentStep === 2) currentErrors = validateStep2(step2Data)

    if (Object.keys(currentErrors).length > 0) {
      setErrors(currentErrors)
      window.scrollTo({ top: 0, behavior: 'smooth' })
      return
    }

    setErrors({})
    setCurrentStep(currentStep + 1)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleBack = () => {
    setErrors({})
    setCurrentStep(currentStep - 1)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleSubmit = async () => {
    const currentErrors = validateStep3(step3Data, privacyConsent)
    if (Object.keys(currentErrors).length > 0) {
      setErrors(currentErrors)
      return
    }

    setSubmitting(true)

    try {
      const response = await apiFetch('/api/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...step1Data,
          email: lockedEmail,
          ...step2Data,
          applicationType: 'General Application'
        })
      })

      const data = await response.json()

      // ── DUPLICATE: 409 Conflict ──
      if (response.status === 409) {
        setExistingApplication(data.existing_application)
        setDuplicateReason(data.duplicate_reason || 'email')
        setSubmitting(false)
        return
      }

      if (!response.ok) {
        alert('Error: ' + data.error)
        setSubmitting(false)
        return
      }

      const applicantId = data.applicant_id

      // ── Upload documents ──
      const docKeys = [
        { key: 'enrollmentForm', label: 'Enrollment Form' },
        { key: 'barangayEndorsement', label: 'Barangay Endorsement' },
        { key: 'schoolId', label: 'School ID' },
        { key: 'grade12', label: 'Grade 12 Grades' },
        { key: 'fourPsCert', label: '4Ps Certificate' },
        { key: 'proofOfIncome', label: 'Proof of Income' },
      ]

      for (const doc of docKeys) {
        if (step3Data[doc.key]) {
          const formData = new FormData()
          formData.append('file', step3Data[doc.key])
          formData.append('applicant_id', applicantId)
          formData.append('document_name', doc.label)

          await apiFetch('/api/upload', {
            method: 'POST',
            body: formData
          })
        }
      }

      setSubmitSuccess(true)
      setSubmitting(false)

    } catch {
      alert('Cannot connect to server. Please try again.')
      setSubmitting(false)
    }
  }

  // ── EXISTING APPLICATION SCREEN ──
  if (existingApplication) {
  return (
    <div className="form-container">
      <div className="success-screen">
        <h2>Duplicate Application Detected</h2>

        {/* Show reason */}
        <div className="duplicate-reason-box">
          {duplicateReason === 'email' && (
            <p>A duplicate was detected because your
              <strong> email address</strong> is already
              registered in our system.</p>
          )}
          {duplicateReason === 'name_and_birthdate' && (
            <p>A duplicate was detected because an applicant with
              the same <strong>full name and date of birth</strong> already
              exists in our system.</p>
          )}
          <p className="duplicate-note">
            If you believe this is an error, please contact the
            scholarship office at City Hall.
          </p>
        </div>

        <div className="existing-app-details">
          <div className="existing-app-row">
            <span className="existing-app-label">Application ID</span>
            <span className="existing-app-value">
              #SP-{String(existingApplication.id).padStart(4, '0')}
            </span>
          </div>
          <div className="existing-app-row">
            <span className="existing-app-label">Status</span>
            <span className={`badge ${
              existingApplication.application_status === 'Approved'
                ? 'badge-green' :
              existingApplication.application_status === 'Rejected'
                ? 'badge-red' : 'badge-yellow'
            }`}>
              {existingApplication.application_status || 'Pending'}
            </span>
          </div>
          <div className="existing-app-row">
            <span className="existing-app-label">Course</span>
            <span className="existing-app-value">
              {existingApplication.course}
            </span>
          </div>
          <div className="existing-app-row">
            <span className="existing-app-label">GWA</span>
            <span className="existing-app-value">
              {existingApplication.gpa}
            </span>
          </div>
          <div className="existing-app-row">
            <span className="existing-app-label">Submitted</span>
            <span className="existing-app-value">
              {existingApplication.submitted_at
                ? new Date(existingApplication.submitted_at)
                    .toLocaleDateString('en-PH', {
                      month: 'long', day: 'numeric', year: 'numeric'
                    })
                : 'N/A'}
            </span>
          </div>
        </div>

        <button
          className="btn-next"
          onClick={() => navigate('/student/dashboard')}>
          Go to Dashboard
        </button>
      </div>
    </div>
  )
}

  // ── SUCCESS SCREEN ──
  if (submitSuccess) {
    return (
      <div className="form-container">
        <div className="success-screen">
          <h2>Application Submitted</h2>
          <p>Your scholarship application has been successfully submitted.</p>
          <p>You will be notified via email once your application has been reviewed.</p>
          <div className="success-details">
            <p>Check your email for confirmation</p>
            <p>Your documents have been uploaded</p>
            <p>Review takes 3-5 business days</p>
          </div>
          <button className="btn-next" onClick={() => navigate('/student/dashboard')}>
            Go to Dashboard
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="form-container">
      <StepIndicator currentStep={currentStep} />
      
      {/* AutoFill notification */}
      {autoFilling && (
        <div className="autofill-banner loading">
          Reading document with OCR... Auto-filling your form...
        </div>
      )}

      {Object.keys(autoFillResults).length > 0 && !autoFilling && (
        <div className="autofill-banner success">
          OCR Auto-filled {Object.keys(autoFillResults).length} field(s):
          {' '}{Object.keys(autoFillResults).join(', ')}
        </div>
      )}
      {currentStep === 1 &&
        <Step1 data={step1Data} onChange={handleStep1Change} errors={errors} />}
      {currentStep === 2 &&
        <Step2 data={step2Data} onChange={handleStep2Change} errors={errors} />}
      {currentStep === 3 &&
        <Step3
          data={step3Data}
          onChange={handleStep3Change}
          errors={errors}
          consent={privacyConsent}
          onConsentChange={(val) => {
            setPrivacyConsent(val)
            if (errors.privacyConsent) setErrors(prev => ({ ...prev, privacyConsent: '' }))
          }}
        />}

      <div className="form-footer">
        <button className="btn-draft">Save Draft</button>
        <div className="footer-right">
          {currentStep > 1 && (
            <button className="btn-back" onClick={handleBack}>← Back</button>
          )}
          {currentStep < 3 ? (
            <button className="btn-next" onClick={handleNext}>
              {currentStep === 1 ? 'Next: Academic Info →' : 'Next →'}
            </button>
          ) : (
            <button
              className="btn-submit"
              onClick={handleSubmit}
              disabled={submitting}>
              {submitting ? 'Submitting...' : 'Submit Application'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default ApplicationForm