import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { apiFetch, displayStatus, connectionErrorMessage } from '../../api'
import { compressImageFile, MAX_UPLOAD_BYTES } from '../../fileUtils'
import pageBg from '../../assets/bg3.jpg'
import './ApplicationForm.css'
import { INCOME_RANGES } from '../../incomeRanges'

// ── DATA ──
// These three lists must match the eligibility model's encoding exactly
// (see backend/schema/ml_model.md) - the values are one-hot/ordinal encoded
// by exact string match, so don't rename or reorder without updating the model too.
const EDUCATION_LEVELS = ['None', 'Elementary', 'High School', 'Vocational', 'College', 'Postgraduate']
const OCCUPATION_CATEGORIES = [
  'Unemployed', 'Informal/Vendor', 'Laborer/Driver', 'Skilled Trade',
  'Office/Clerical', 'Professional', 'Deceased/Not Applicable'
]
// Display text only - the submitted value stays the exact category string above.
const OCCUPATION_LABELS = { Unemployed: 'Unemployed (including Housewife/Househusband)' }
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
function validateStep1(data, hiddenBuiltins = []) {
  const errors = {}
  if (!data.fullName.trim()) errors.fullName = 'Full name is required'
  if (!data.email.trim()) errors.email = 'Email is required'
  else if (!/\S+@\S+\.\S+/.test(data.email)) errors.email = 'Enter a valid email address'
  if (!data.address.trim()) errors.address = 'Address is required'
  if (!hiddenBuiltins.includes('religion') && !data.religion) errors.religion = 'Religion is required'
  if (!data.gender) errors.gender = 'Gender is required'
  if (!data.dob) errors.dob = 'Date of birth is required'
  if (!hiddenBuiltins.includes('citizenship') && !data.citizenship.trim()) errors.citizenship = 'Citizenship is required'
  if (!data.contactNumber.trim()) errors.contactNumber = 'Contact number is required'
  else if (!/^09\d{9}$/.test(data.contactNumber.replace(/\s/g, '')))
    errors.contactNumber = 'Enter a valid PH number (Number should start with 09 and be 11 digits long)'
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
    errors.academicYear = 'Format must be yyyy-yyyy'
  if (!data.semester) errors.semester = 'Semester is required'
  return errors
}

// ── VALIDATE LGU-DEFINED CUSTOM FIELDS FOR A GIVEN SECTION ──
function validateCustomFields(customFields, section, extraFieldsData) {
  const errors = {}
  customFields
    .filter(f => f.section === section && f.enabled && f.required)
    .forEach(f => {
      const value = extraFieldsData[f.key]
      if (value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0)) {
        errors[f.key] = `${f.label} is required`
      }
    })
  return errors
}

// ── VALIDATE STEP 3 ──
function validateStep3(data, consent, requirements) {
  const errors = {}
  requirements
    .filter(r => r.enabled && r.required)
    .forEach(r => {
      if (!data[r.label]) errors[r.label] = `${r.label} is required`
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

// ── LGU-DEFINED CUSTOM FIELDS ──
// Purely informational fields an admin added via Form Builder for this LGU - never
// read by the eligibility model (see build_feature_row on the backend), so nothing
// entered here can ever affect a scoring decision.
function CustomFieldsSection({ customFields, section, values, onChange, errors }) {
  const fields = customFields.filter(f => f.section === section && f.enabled)
  if (fields.length === 0) return null

  return (
    <div className="form-section">
      <h3 className="section-title">Additional Information</h3>
      <div className="form-grid-2">
        {fields.map(f => (
          <Field key={f.key} label={f.label + (f.required ? ' *' : '')} error={errors[f.key]}>
            {f.type === 'select' ? (
              <select
                className={errors[f.key] ? 'input-error' : ''}
                value={values[f.key] || ''}
                onChange={e => onChange(f.key, e.target.value)}>
                <option value="">Select {f.label.toLowerCase()}</option>
                {f.options.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : f.type === 'checkbox' ? (
              f.options && f.options.length > 0 ? (
                <div className="radio-group">
                  {f.options.map(o => {
                    const selected = Array.isArray(values[f.key]) ? values[f.key] : []
                    return (
                      <label key={o} className="radio-option">
                        <input
                          type="checkbox"
                          checked={selected.includes(o)}
                          onChange={e => onChange(f.key, e.target.checked
                            ? [...selected, o]
                            : selected.filter(v => v !== o))}
                        />
                        <span>{o}</span>
                      </label>
                    )
                  })}
                </div>
              ) : (
                <div className="radio-group">
                  <label className="radio-option">
                    <input
                      type="checkbox"
                      checked={values[f.key] === 'Yes'}
                      onChange={e => onChange(f.key, e.target.checked ? 'Yes' : 'No')}
                    />
                    <span>Yes</span>
                  </label>
                </div>
              )
            ) : f.type === 'textarea' ? (
              <textarea
                className={errors[f.key] ? 'input-error' : ''}
                value={values[f.key] || ''}
                onChange={e => onChange(f.key, e.target.value)}
              />
            ) : (
              <input
                className={errors[f.key] ? 'input-error' : ''}
                type={f.type}
                value={values[f.key] || ''}
                onChange={e => onChange(f.key, e.target.value)}
              />
            )}
          </Field>
        ))}
      </div>
    </div>
  )
}

// ── STEP 1 ──
function Step1({ data, onChange, errors, customFields, hiddenBuiltins, extraFieldsData, onExtraFieldChange }) {
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
                color: '#4b5563',
                cursor: 'not-allowed',
                border: '1.5px solid #E5E7EB'
              }}
              title="Email is tied to your account and cannot be changed"
            />
            <span style={{ fontSize: '11.5px', color: '#4b5563', marginTop: '4px', display: 'block' }}>
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

          {!hiddenBuiltins.includes('religion') && (
            <Field label="Religion" error={errors.religion}>
              <select
                className={errors.religion ? 'input-error' : ''}
                value={data.religion}
                onChange={e => onChange('religion', e.target.value)}>
                <option value="">Select religion</option>
                {RELIGIONS.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </Field>
          )}

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

          {!hiddenBuiltins.includes('citizenship') && (
            <Field label="Citizenship" error={errors.citizenship}>
              <input
                className={errors.citizenship ? 'input-error' : ''}
                type="text" placeholder="Filipino"
                value={data.citizenship}
                onChange={e => onChange('citizenship', e.target.value)} />
            </Field>
          )}

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
              {OCCUPATION_CATEGORIES.map(o => <option key={o} value={o}>{OCCUPATION_LABELS[o] || o}</option>)}
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
              {OCCUPATION_CATEGORIES.map(o => <option key={o} value={o}>{OCCUPATION_LABELS[o] || o}</option>)}
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

          <Field label="Estimated Monthly Household Income" error={errors.monthlyIncome}>
            <select
              className={errors.monthlyIncome ? 'input-error' : ''}
              value={data.monthlyIncome}
              onChange={e => onChange('monthlyIncome', e.target.value)}>
              <option value="">Select income range</option>
              {INCOME_RANGES.map(r => <option key={r.label} value={r.value}>{r.label}</option>)}
            </select>
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
              type="number" placeholder="Enter number" min="1" max="20"
              value={data.familySize}
              onChange={e => onChange('familySize', e.target.value)} />
          </Field>

          <Field label="Number of Siblings" error={errors.numSiblings}>
            <input
              className={errors.numSiblings ? 'input-error' : ''}
              type="number" placeholder="Enter number" min="0" max="20"
              value={data.numSiblings}
              onChange={e => onChange('numSiblings', e.target.value)} />
          </Field>

          <Field label="Siblings Currently Studying" error={errors.numSiblingsStudying}>
            <input
              className={errors.numSiblingsStudying ? 'input-error' : ''}
              type="number" placeholder="Enter number" min="0" max="20"
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
                placeholder="Enter scholarship name and details"
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

      <CustomFieldsSection
        customFields={customFields}
        section="personal"
        values={extraFieldsData}
        onChange={onExtraFieldChange}
        errors={errors}
      />
    </div>
  )
}

// ── STEP 2 ──
function Step2({ data, onChange, errors, customFields, extraFieldsData, onExtraFieldChange }) {
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
              type="number" placeholder="Enter your GWA 90.5"
              step="0.01" min="75" max="99"
              value={data.gpa}
              onChange={e => onChange('gpa', e.target.value)} />
            <span style={{ fontSize: '11.5px', color: '#4b5563', marginTop: '4px', display: 'block' }}>
              Your Grade 12 GWA (or latest GWA), on the 75-99 percentage scale
            </span>
          </Field>

          <Field label="Academic Year" error={errors.academicYear}>
            <input
              className={errors.academicYear ? 'input-error' : ''}
              type="text" placeholder="2025-2026"
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

      <CustomFieldsSection
        customFields={customFields}
        section="school"
        values={extraFieldsData}
        onChange={onExtraFieldChange}
        errors={errors}
      />
    </div>
  )
}

// ── STEP 3 ──
function Step3({ data, onChange, onFileError, errors, consent, onConsentChange, requirements }) {
  const visibleRequirements = requirements.filter(r => r.enabled)

  return (
    <div className="step-content">
      <h2>Requirements</h2>
      <p className="req-note">Fields marked with <span className="req-star">*</span> are required.</p>
      <div className="form-section">
        {visibleRequirements.map(req => (
          <div key={req.id} className="upload-group">
            <label>
              {req.label}
              {req.required && <span className="req-star"> *</span>}
            </label>
            <div
              className={`upload-box ${errors[req.label] ? 'upload-error' : ''}`}
              onClick={() => document.getElementById(`doc-${req.id}`).click()}>
              {data[req.label]?.existing ? (
                <span className="upload-filename">Uploaded: {data[req.label].name} (click to replace)</span>
              ) : data[req.label] ? (
                <span className="upload-filename">{data[req.label].name}</span>
              ) : (
                <span className="upload-placeholder">Click to upload (PDF, JPG, PNG)</span>
              )}
              <input
                type="file"
                id={`doc-${req.id}`}
                style={{ display: 'none' }}
                accept=".pdf,.jpg,.jpeg,.png"
                onChange={async e => {
                  const raw = e.target.files[0]
                  if (!raw) return
                  // Downscale before this ever gets held in memory or uploaded -
                  // a raw camera photo can be large enough to crash a low-memory
                  // phone at this point (see fileUtils.js).
                  const file = await compressImageFile(raw)
                  if (file.size > MAX_UPLOAD_BYTES) {
                    onFileError(req.label, 'File is too large (max 5MB). Try a lower-resolution photo or a smaller file.')
                    e.target.value = ''
                    return
                  }
                  onChange(req.label, file)
                }}
              />
            </div>

            {errors[req.label] && (
              <span className="error-msg">{errors[req.label]}</span>
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
  const location = useLocation()

  const user = JSON.parse(localStorage.getItem('user') || '{}')
  const lockedEmail = user.email || ''

  // Check if we're editing an existing application (admin requested changes)
  const editMode = location.state?.from === 'edit'
  const editingApplicationId = location.state?.applicationId

  const [currentStep, setCurrentStep] = useState(1)
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [submitSuccess, setSubmitSuccess] = useState(false)
  const [existingApplication, setExistingApplication] = useState(null)
  const [duplicateReason, setDuplicateReason] = useState('')
  const [privacyConsent, setPrivacyConsent] = useState(false)
  const [cycleCheckDone, setCycleCheckDone] = useState(false)

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

  const [savedDraftTime, setSavedDraftTime] = useState(null)

  const [step2Data, setStep2Data] = useState({
    school: '', schoolAddress: '', course: '',
    yearLevel: '', gpa: '', academicYear: '', semester: ''
  })

  // Keyed by document label ( "Enrollment Form") rather than a fixed set of
  // camelCase keys, since the document checklist itself is LGU-configurable.
  const [step3Data, setStep3Data] = useState({})
  const [docRequirements, setDocRequirements] = useState([])

  // LGU-configurable form: extra fields this LGU has added, and any of the
  // optional built-in fields (religion, citizenship) this LGU has hidden.
  const [customFields, setCustomFields] = useState([])
  const [hiddenBuiltins, setHiddenBuiltins] = useState([])
  const [extraFieldsData, setExtraFieldsData] = useState({})

  // When editing an existing application (admin requested changes), load and pre-fill it.
  // Don't send the user back to dashboard - they need to edit this application.
  useEffect(() => {
    if (!editMode) return
    (async () => {
      try {
        const res = await apiFetch(`/api/student/application?email=${encodeURIComponent(lockedEmail)}`)
        if (res.ok) {
          const data = await res.json()
          if (data.application) {
            // Pre-fill form with existing data
            const app = data.application
            setStep1Data(prev => ({
              ...prev,
              fullName: app.full_name || prev.fullName,
              address: app.address || prev.address,
              religion: app.religion || prev.religion,
              gender: app.gender || prev.gender,
              dob: app.date_of_birth || prev.dob,
              citizenship: app.citizenship || prev.citizenship,
              contactNumber: app.contact_number || prev.contactNumber,
              fatherName: app.father_name || prev.fatherName,
              fatherOccupation: app.father_occupation || prev.fatherOccupation,
              fatherEducation: app.father_education || prev.fatherEducation,
              motherName: app.mother_name || prev.motherName,
              motherOccupation: app.mother_occupation || prev.motherOccupation,
              motherEducation: app.mother_education || prev.motherEducation,
              monthlyIncome: app.monthly_income || prev.monthlyIncome,
              familySize: app.family_size || prev.familySize,
              numSiblings: app.num_siblings ?? prev.numSiblings,
              numSiblingsStudying: app.num_siblings_studying ?? prev.numSiblingsStudying,
              housingSituation: app.housing_situation || prev.housingSituation,
              hasOtherScholarship: app.has_other_scholarship || prev.hasOtherScholarship,
              otherScholarshipDetails: app.other_scholarship_details || prev.otherScholarshipDetails,
            }))
            setStep2Data(prev => ({
              ...prev,
              school: app.school || prev.school,
              schoolAddress: app.school_address || prev.schoolAddress,
              course: app.course || prev.course,
              yearLevel: app.year_level || prev.yearLevel,
              gpa: app.gpa || prev.gpa,
              academicYear: app.academic_year || prev.academicYear,
              semester: app.semester || prev.semester,
            }))

            // Documents already uploaded on this application, keyed by label so
            // Step3 can show "already uploaded" instead of "Missing" on reopen.
            // serialize_document doesn't return a real filename, only
            // document_name, so that doubles as the display name here.
            const existingByLabel = {}
            for (const doc of data.documents || []) {
              if (doc.status === 'Uploaded') {
                existingByLabel[doc.document_name] = { name: doc.document_name, existing: true }
              }
            }
            // Anything the student already touched this session wins over the pre-fill.
            setStep3Data(prev => ({ ...existingByLabel, ...prev }))
          }
        }
      } catch {
        // fail silently and let user proceed with empty form
      }
      setCycleCheckDone(true)
    })()
  }, [editMode])

  // A student who navigates here directly (bookmark, back button) while no
  // scholarship program is open, or who already has an application, gets sent
  // back to the dashboard rather than filling out a form that will just 403 on
  // submit - the dashboard shows the right message for either case. Fails open
  // on a network error so a flaky check never blocks a legitimate submission;
  // POST /api/apply enforces the real gate server-side regardless.
  // Exception: skip this check when editing an existing application.
  useEffect(() => {
    if (editMode) {
      setCycleCheckDone(true)
      return
    }
    (async () => {
      try {
        const res = await apiFetch(`/api/student/application?email=${encodeURIComponent(lockedEmail)}`)
        if (res.ok) {
          const data = await res.json()
          // A self-withdrawn application (Withdrawn, no admin_comment) doesn't
          // block a fresh submission - same rule the dashboard uses to decide
          // "Start Application" vs "View My Application". Only a still-active
          // application (or one Withdrawn by admin request, which must go
          // through the edit flow instead) should send the student back.
          const app = data.application
          const isWithdrawn = app?.application_status === 'Withdrawn'
          const blocksFreshApplication = app && !(isWithdrawn && !app.admin_comment)
          if (blocksFreshApplication || (data.current_cycle && !data.current_cycle.is_open)) {
            navigate('/student/dashboard')
            return
          }
        }
      } catch {
        // fail open - see comment above
      }
      setCycleCheckDone(true)
    })()
  }, [])

  useEffect(() => {
    (async () => {
      try {
        const res = await apiFetch('/api/form-fields')
        if (!res.ok) return
        const data = await res.json()
        setCustomFields(data.fields || [])
        setHiddenBuiltins(data.hidden_builtin_fields || [])
      } catch {
        // form customization is a convenience layer - the base form still works without it
      }
    })()

    ;(async () => {
      try {
        const res = await apiFetch('/api/document-requirements')
        if (!res.ok) return
        const data = await res.json()
        setDocRequirements(data.requirements || [])
      } catch {
        // document customization is a convenience layer - falls back to an empty checklist
      }
    })()
  }, [])

  const handleExtraFieldChange = (key, value) => {
    setExtraFieldsData(prev => ({ ...prev, [key]: value }))
    if (errors[key]) setErrors(prev => ({ ...prev, [key]: '' }))
  }

  // Personal info collected at registration pre-fills Step 1 so it isn't retyped here.
  // Only blank fields are filled in, so anything the user has already started editing wins.
  // Load saved draft if it exists
  useEffect(() => {
    const savedDraft = localStorage.getItem('applicationDraft')
    if (savedDraft) {
      try {
        const draft = JSON.parse(savedDraft)
        setCurrentStep(draft.step || 1)
        setStep1Data(draft.step1 || step1Data)
        setStep2Data(draft.step2 || step2Data)
        setStep3Data(draft.step3 || step3Data)
        setExtraFieldsData(draft.extraFields || {})
      } catch {
        // Draft data is corrupted, ignore it
      }
    }
  }, [])

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

  const handleStep3Change = (field, value) => {
    setStep3Data(prev => ({ ...prev, [field]: value }))
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: '' }))
  }

  const handleStep3FileError = (field, message) => {
    setErrors(prev => ({ ...prev, [field]: message }))
  }

  const handleNext = () => {
    let currentErrors = {}
    if (currentStep === 1) {
      currentErrors = {
        ...validateStep1(step1Data, hiddenBuiltins),
        ...validateCustomFields(customFields, 'personal', extraFieldsData),
      }
    }
    if (currentStep === 2) {
      currentErrors = {
        ...validateStep2(step2Data),
        ...validateCustomFields(customFields, 'school', extraFieldsData),
      }
    }

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

  const handleSaveDraft = () => {
    const draftData = {
      step: currentStep,
      step1: step1Data,
      step2: step2Data,
      step3: step3Data,
      extraFields: extraFieldsData,
      savedAt: new Date().toISOString(),
    }
    localStorage.setItem('applicationDraft', JSON.stringify(draftData))
    setSavedDraftTime(new Date())
    // Show confirmation message
    setTimeout(() => setSavedDraftTime(null), 3000)
  }

  const handleSubmit = async () => {
    const currentErrors = validateStep3(step3Data, privacyConsent, docRequirements)
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
          applicationType: 'General Application',
          extraFields: extraFieldsData,
          ...(editMode && { editMode: true }), // Flag to backend that this is an edit
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

      // ── Upload documents (step3Data is keyed by document label) ──
      for (const [label, file] of Object.entries(step3Data)) {
        if (file instanceof File) {
          const formData = new FormData()
          formData.append('file', file)
          formData.append('applicant_id', applicantId)
          formData.append('document_name', label)

          await apiFetch('/api/upload', {
            method: 'POST',
            body: formData
          })
        }
      }

      setSubmitSuccess(true)
      setSubmitting(false)
      // Clear the draft after successful submission
      localStorage.removeItem('applicationDraft')

    } catch {
      alert(connectionErrorMessage())
      setSubmitting(false)
    }
  }

  // ── EXISTING APPLICATION SCREEN ──
  if (existingApplication) {
  return (
    <div className="form-container page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>
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
              displayStatus(existingApplication.application_status, existingApplication.ml_status) === 'Approved'
                ? 'badge-green' :
              displayStatus(existingApplication.application_status, existingApplication.ml_status) === 'Rejected'
                ? 'badge-red' : 'badge-yellow'
            }`}>
              {displayStatus(existingApplication.application_status, existingApplication.ml_status) || 'Pending'}
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

  if (!cycleCheckDone) {
    return <div className="form-container page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}><p>Loading...</p></div>
  }

  // ── SUCCESS SCREEN ──
  if (submitSuccess) {
    return (
      <div className="form-container page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>
        <div className="success-screen">
          <h2>{editMode ? 'Application Updated' : 'Application Submitted'}</h2>
          <p>{editMode
            ? 'Your scholarship application has been successfully updated with the requested changes.'
            : 'Your scholarship application has been successfully submitted.'
          }</p>
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
    <div className="form-container page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>
      <div className="page-hero">
        <h2 className="page-title">Scholarship Application</h2>
        <p className="page-sub">Complete the three steps below to submit your application.</p>
      </div>
      <StepIndicator currentStep={currentStep} />

      {currentStep === 1 &&
        <Step1
          data={step1Data} onChange={handleStep1Change} errors={errors}
          customFields={customFields} hiddenBuiltins={hiddenBuiltins}
          extraFieldsData={extraFieldsData} onExtraFieldChange={handleExtraFieldChange}
        />}
      {currentStep === 2 &&
        <Step2
          data={step2Data} onChange={handleStep2Change} errors={errors}
          customFields={customFields}
          extraFieldsData={extraFieldsData} onExtraFieldChange={handleExtraFieldChange}
        />}
      {currentStep === 3 &&
        <Step3
          data={step3Data}
          onChange={handleStep3Change}
          onFileError={handleStep3FileError}
          errors={errors}
          requirements={docRequirements}
          consent={privacyConsent}
          onConsentChange={(val) => {
            setPrivacyConsent(val)
            if (errors.privacyConsent) setErrors(prev => ({ ...prev, privacyConsent: '' }))
          }}
        />}

      <div className="form-footer">
        <div className="draft-section">
          <button className="btn-draft" onClick={handleSaveDraft}>
            {savedDraftTime ? 'Saved!' : 'Save Draft'}
          </button>
          {savedDraftTime && (
            <span className="draft-saved-msg">
              Draft saved at {savedDraftTime.toLocaleTimeString('en-PH', { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>
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
              {submitting ? (editMode ? 'Saving...' : 'Submitting...') : (editMode ? 'Save Changes' : 'Submit Application')}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default ApplicationForm