import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, getUser, displayStatus, connectionErrorMessage } from '../../api'
import { parseServerDate } from '../../dateUtils'
import { compressImageFile, MAX_UPLOAD_BYTES } from '../../fileUtils'
import Reveal from '../../components/Reveal'
import StatTile from '../../components/StatTile'
import ScoreBreakdown from '../../components/ScoreBreakdown'
import ApprovedNextSteps from '../../components/ApprovedNextSteps'
import pageBg from '../../assets/bg1.jpg'
import './ApplicantDetails.css'

// Must match backend's SELFIE_DOC_LABEL (backend/app.py) - stored/uploaded through the
// same generic document pipeline as everything else, but pulled out into its own
// "Identity Verification" card here instead of the general document checklist below.
const SELFIE_DOC_LABEL = 'Selfie / Face Photo'

const STATUS_COLORS = {
  'Approved': 'badge-green',
  'Rejected': 'badge-red',
  'Waitlisted': 'badge-yellow',
  'Newly Submitted': 'badge-blue',
  'Pending Verification': 'badge-yellow',
  'Not Yet Reviewed': 'badge-purple',
  'Incomplete': 'badge-red',
  'Withdrawn': 'badge-gray',
}

const STATUS_MESSAGES = {
  'Approved': 'Congratulations. Your scholarship application has been approved.',
  'Rejected': 'Unfortunately your application was not approved this time.',
  'Waitlisted': 'Your application met the eligibility criteria, but there were more qualified applicants than available slots. You have been waitlisted and may be promoted automatically if a slot opens up.',
  'Newly Submitted': 'Your application has been submitted and is waiting for review.',
  'Pending Verification': 'Your documents are being verified by our team.',
  'Not Yet Reviewed': 'Your application is in the queue and will be reviewed soon.',
  'Incomplete': 'Your application is incomplete. Please upload all required documents.',
  'Withdrawn': 'You have withdrawn this application. If you change your mind, you can submit a new application.',
}

// Renders a stored answer for display; booleans come from single Yes/No
// checkboxes and arrays from multi-option checkbox questions.
function formatAnswer(value) {
  if (value === null || value === undefined || value === '') return 'N/A'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'N/A'
  return String(value)
}

const hasAnswer = (v) => Array.isArray(v) ? v.length > 0 : (v !== null && v !== undefined && v !== '')

function ApplicantDetails() {
  const navigate = useNavigate()
  const [application, setApplication] = useState(null)
  const [docs, setDocs] = useState([])
  const [dragOver, setDragOver] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [withdrawing, setWithdrawing] = useState(false)
  const [withdrawError, setWithdrawError] = useState('')
  const [uploadError, setUploadError] = useState('')
  const [selfiePreviewUrl, setSelfiePreviewUrl] = useState('')
  // Documents whose readability/name pre-check is in flight, by name.
  const [checking, setChecking] = useState({})
  // This LGU's custom questions, to label the answers in application.extra_fields.
  const [customFieldDefs, setCustomFieldDefs] = useState([])
  const precheckAttempted = useRef(new Set())

  const user = getUser() || {}

  const loadApplicantDetails = async () => {
    setLoading(true)
    setLoadError(false)
    if (!user.email) { setLoading(false); return }

    try {
      const [appRes, reqRes, fieldsRes] = await Promise.all([
        apiFetch(`/api/student/application?email=${encodeURIComponent(user.email)}`),
        apiFetch('/api/document-requirements'),
        apiFetch('/api/form-fields'),
      ])
      if (fieldsRes.ok) {
        const fieldsData = await fieldsRes.json()
        setCustomFieldDefs(fieldsData.fields || [])
      }
      if (!appRes.ok) throw new Error(`Request failed with status ${appRes.status}`)
      const appData = await appRes.json()

      if (appData.application) {
        setApplication(appData.application)

        const reqData = reqRes.ok ? await reqRes.json() : { requirements: [] }
        const requirements = (reqData.requirements || []).filter(r => r.enabled)
        let mergedDocs = requirements.map(r => ({
          id: r.id,
          document_name: r.label,
          required: r.required,
          status: r.required ? 'Missing' : 'Not Required',
          file: null,
        }))
        if (appData.documents && appData.documents.length > 0) {
          mergedDocs = mergedDocs.map(d => {
            const found = appData.documents.find(u => u.document_name === d.document_name)
            return found ? {
              ...d,
              status: found.status,
              warning: found.upload_warning || '',
              needsCheck: found.status === 'Uploaded' && !found.ocr_status,
            } : d
          })
        }
        setDocs(mergedDocs)
      } else {
        setApplication(null)
      }
    } catch (err) {
      console.error('Error:', err)
      setLoadError(true)
    }
    setLoading(false)
  }

  useEffect(() => { loadApplicantDetails() }, [])

  // Asks the server whether an uploaded document is readable and shows the
  // student's name, so they can replace it now instead of after review.
  // Advisory only - a warning never blocks the application.
  const precheckDocument = async (documentName) => {
    if (!application || documentName === SELFIE_DOC_LABEL) return
    setChecking(prev => ({ ...prev, [documentName]: true }))
    try {
      const res = await apiFetch('/api/documents/precheck', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ applicant_id: application.id, document_name: documentName }),
      })
      if (res.ok) {
        const { warning } = await res.json()
        setDocs(prev => prev.map(d => d.document_name === documentName ? { ...d, warning: warning || '' } : d))
      }
    } catch {
      // Pre-check is best-effort; admin verification still runs later.
    } finally {
      setChecking(prev => ({ ...prev, [documentName]: false }))
    }
  }

  // Documents uploaded with the application form (or before this check
  // existed) get checked the first time the student opens this page - one at
  // a time, since each is a full OCR pass on the server.
  useEffect(() => {
    if (!application) return
    const pending = docs.filter(d => d.needsCheck && !precheckAttempted.current.has(d.document_name))
    if (pending.length === 0) return
    pending.forEach(d => precheckAttempted.current.add(d.document_name))
    ;(async () => {
      for (const d of pending) await precheckDocument(d.document_name)
    })()
  }, [application, docs])

  // Show the actual previously-uploaded selfie image (not just its filename/status)
  // so the student can see what's on file without re-taking it.
  useEffect(() => {
    const selfie = docs.find(d => d.document_name === SELFIE_DOC_LABEL)
    if (!application || !selfie || selfie.status !== 'Uploaded' || selfie.file) {
      return
    }
    let objectUrl = ''
    let cancelled = false
    apiFetch(`/api/documents/${application.id}/view?document_name=${encodeURIComponent(SELFIE_DOC_LABEL)}`)
      .then(res => (res.ok ? res.blob() : null))
      .then(blob => {
        if (cancelled || !blob) return
        objectUrl = URL.createObjectURL(blob)
        setSelfiePreviewUrl(objectUrl)
      })
      .catch(() => {})
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [application, docs])

  const handleWithdraw = async () => {
    if (!window.confirm(
      'Withdraw this application? Your submitted information stays on file, but it will no ' +
      'longer be considered for the scholarship. You can submit a new application later if you change your mind.'
    )) return

    setWithdrawing(true)
    setWithdrawError('')
    try {
      const res = await apiFetch('/api/student/application/withdraw', { method: 'PUT' })
      const data = await res.json()
      if (!res.ok) {
        setWithdrawError(data.error || 'Could not withdraw your application.')
        return
      }
      loadApplicantDetails()
    } catch {
      setWithdrawError(connectionErrorMessage())
    } finally {
      setWithdrawing(false)
    }
  }

  const handleUpload = async (id, rawFile) => {
    if (!rawFile || !application) return
    setUploadError('')

    // Downscale before ever creating a preview or reading it into a
    // request body - an uncompressed camera photo can be large enough to
    // crash a low-memory phone at this point (see fileUtils.js).
    const file = await compressImageFile(rawFile)
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadError('That file is too large (max 5MB). Try a lower-resolution photo or a smaller file.')
      return
    }

    setDocs(prev => prev.map(d => d.id === id ? { ...d, file, status: 'Uploaded', warning: '' } : d))

    const doc = docs.find(d => d.id === id)
    if (doc && doc.document_name === SELFIE_DOC_LABEL) {
      setSelfiePreviewUrl(prev => {
        if (prev) URL.revokeObjectURL(prev)
        return URL.createObjectURL(file)
      })
    }
    const formData = new FormData()
    formData.append('file', file)
    formData.append('applicant_id', application.id)
    formData.append('document_name', doc.document_name)

    try {
      const res = await apiFetch('/api/upload', { method: 'POST', body: formData })
      if (!res.ok) throw new Error('Upload failed')
      precheckDocument(doc.document_name)
    } catch (err) {
      console.error('Upload error:', err)
      setDocs(prev => prev.map(d =>
        d.id === id ? { ...d, file: null, status: d.required ? 'Missing' : 'Not Required' } : d
      ))
    }
  }

  const handleRemove = (id) => {
    const doc = docs.find(d => d.id === id)
    if (doc && doc.document_name === SELFIE_DOC_LABEL) {
      setSelfiePreviewUrl(prev => { if (prev) URL.revokeObjectURL(prev); return '' })
    }
    setDocs(prev => prev.map(d =>
      d.id === id ? { ...d, file: null, status: d.required ? 'Missing' : 'Not Required' } : d
    ))
  }

  const handleDrop = (id, e) => {
    e.preventDefault()
    setDragOver(null)
    const file = e.dataTransfer.files[0]
    if (file) handleUpload(id, file)
  }

  const getStatusClass = (status) => {
    if (status === 'Uploaded') return 'badge-uploaded'
    if (status === 'Missing') return 'badge-missing'
    return 'badge-not-required'
  }

  if (loading) {
    return (
      <div className="av-container page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>
        <div className="av-loading">Loading your application...</div>
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="av-container page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>
        <div className="av-empty">
          <h2>Couldn't Load Your Details</h2>
          <p>Check your connection and try again.</p>
          <button className="av-btn-primary" onClick={loadApplicantDetails}>Retry</button>
        </div>
      </div>
    )
  }

  if (!application) {
    return (
      <div className="av-container page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>
        <div className="av-empty">
          <h2>No Application Found</h2>
          <p>You haven't submitted a scholarship application yet.</p>
          <button className="av-btn-primary"
            onClick={() => navigate('/student/application')}>
            Start Application
          </button>
        </div>
      </div>
    )
  }

  const status = application.application_status || 'Pending'
  const displayed = displayStatus(status, application.ml_status)
  // Once reviewed (or withdrawn), documents are frozen - same rule the backend
  // enforces on POST /api/upload. Editing a decided/dead application's files
  // would change what was actually reviewed without a new review happening.
  // Exception: if admin requested changes (Withdrawn + admin_comment), allow editing.
  const adminRequestedChanges = status === 'Withdrawn' && application?.admin_comment
  const docsLocked = (status === 'Approved' || status === 'Rejected' || status === 'Withdrawn') && !adminRequestedChanges
  const selfie = docs.find(d => d.document_name === SELFIE_DOC_LABEL)
  const checklistDocs = docs.filter(d => d.document_name !== SELFIE_DOC_LABEL)
  const uploaded = checklistDocs.filter(d => d.status === 'Uploaded').length
  const missing = checklistDocs.filter(d => d.status === 'Missing').length
  const totalRequired = checklistDocs.filter(d => d.required).length

  // When admin requests changes, we're editing the existing application.
  // Pass a flag to the form so it knows to update existing, not create new.
  const editApplicationState = adminRequestedChanges
    ? { from: 'edit', applicationId: application.id }
    : null

  return (
    <div className="av-container page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>

      {/* Header */}
      <div className="av-header">
        <div>
          <h2 className="av-title">Applicant Details</h2>
          <p className="av-sub">
            Application ID: <span className="av-id">
              #SP-{String(application.id).padStart(4, '0')}
            </span>
          </p>
        </div>
        <span className={`badge ${displayed === 'Withdrawn' && application.admin_comment ? 'badge-yellow' : STATUS_COLORS[displayed] || 'badge-yellow'}`}>
          {displayed === 'Withdrawn' && application.admin_comment ? 'Changes Requested' : displayed}
        </span>
      </div>

      {/* Status Banner */}
      <div className={`av-status-banner ${
        displayed === 'Approved' ? 'banner-green' :
        displayed === 'Waitlisted' ? 'banner-yellow' :
        displayed === 'Rejected' ? 'banner-red' :
        displayed === 'Withdrawn' ? (application.admin_comment ? 'banner-yellow' : 'banner-gray') : 'banner-blue'
      }`}>
        <p>
          {displayed === 'Withdrawn' && application.admin_comment
            ? `An admin requested changes to your application: ${application.admin_comment} Please update your application with the corrected information below.`
            : STATUS_MESSAGES[displayed] || 'Your application is being processed.'}
        </p>

        {displayed === 'Approved' && <ApprovedNextSteps />}

        {status === 'Rejected' && application.ml_status !== 'Eligible' && application.rejection_reason && (
          <p className="av-rejection-reason">{application.rejection_reason}</p>
        )}

        {application.submitted_at && (
          <p className="av-submitted">
            Submitted: {parseServerDate(application.submitted_at).toLocaleDateString('en-PH', {
              month: 'long',
              day: 'numeric',
              year: 'numeric'
            })}
          </p>
        )}

        {application.reviewed_at && (
          <p className="av-reviewed">
            Reviewed on: {parseServerDate(application.reviewed_at)
              .toLocaleDateString('en-PH', {
                month: 'long',
                day: 'numeric',
                year: 'numeric'
              })}
            {application.reviewed_by_name && (
              <span> by <strong>{application.reviewed_by_name}</strong></span>
            )}
          </p>
        )}
      </div>

      {/* Eligibility breakdown - only sent once a decision is released */}
      {application.score_breakdown && (
        <div className="av-card">
          <h3 className="av-card-title">Eligibility Breakdown</h3>
          <ScoreBreakdown breakdown={application.score_breakdown} />
        </div>
      )}

      {/* Identity Verification (selfie for face comparison against ID) */}
      {selfie && (
        <div className="av-card">
          <h3 className="av-card-title">
            Identity Verification
            {selfie.required && <span className="required-star"> *</span>}
          </h3>
          <p className="selfie-instructions">
            Upload a clear photo of your face, looking straight at the camera in good
            lighting. Our team will compare it against your uploaded ID to confirm
            your identity.
          </p>

          <div className="selfie-row">
            <div className="selfie-preview">
              {selfiePreviewUrl ? (
                <img src={selfiePreviewUrl} alt="Your selfie" />
              ) : (
                <div className="selfie-placeholder" aria-hidden="true">
                  <span>No photo yet</span>
                </div>
              )}
            </div>

            <div className="selfie-actions">
              <span className={`badge ${getStatusClass(selfie.status)}`}>
                {selfie.status}
              </span>
              {!docsLocked && (
                <>
                  <button className="btn-upload"
                    onClick={() => document.getElementById(`doc-${selfie.id}`).click()}>
                    {selfie.status === 'Uploaded' ? 'Replace Photo' : 'Upload Photo'}
                  </button>
                  {selfie.status === 'Uploaded' && (
                    <button className="btn-remove" onClick={() => handleRemove(selfie.id)}>
                      Remove
                    </button>
                  )}
                  <input
                    type="file"
                    id={`doc-${selfie.id}`}
                    style={{ display: 'none' }}
                    accept="image/*"
                    onChange={e => handleUpload(selfie.id, e.target.files[0])}
                  />
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Personal Info */}
      <div className="av-card">
        <h3 className="av-card-title">Personal Information</h3>
        <div className="av-grid">
          <div className="av-field">
            <label>Full Name</label>
            <p>{application.full_name}</p>
          </div>
          <div className="av-field">
            <label>Email Address</label>
            <p>{application.email}</p>
          </div>
          <div className="av-field">
            <label>Contact Number</label>
            <p>{application.contact_number}</p>
          </div>
          <div className="av-field">
            <label>Date of Birth</label>
            <p>{application.date_of_birth
              ? new Date(application.date_of_birth).toLocaleDateString('en-PH', {
                  month: 'long', day: 'numeric', year: 'numeric'
                })
              : 'N/A'}</p>
          </div>
          <div className="av-field">
            <label>Gender</label>
            <p>{application.gender}</p>
          </div>
          <div className="av-field">
            <label>Religion</label>
            <p>{formatAnswer(application.religion)}</p>
          </div>
          {hasAnswer(application.citizenship) && (
            <div className="av-field">
              <label>Citizenship</label>
              <p>{application.citizenship}</p>
            </div>
          )}
          <div className="av-field full">
            <label>Address</label>
            <p>{application.address}</p>
          </div>
        </div>
      </div>

      {/* Parental Details */}
      <div className="av-card">
        <h3 className="av-card-title">Parental & Financial Details</h3>
        <div className="av-grid">
          <div className="av-field">
            <label>Father's Name</label>
            <p>{application.father_name}</p>
          </div>
          <div className="av-field">
            <label>Father's Occupation</label>
            <p>{formatAnswer(application.father_occupation)}</p>
          </div>
          <div className="av-field">
            <label>Father's Education</label>
            <p>{formatAnswer(application.father_education)}</p>
          </div>
          <div className="av-field">
            <label>Mother's Name</label>
            <p>{application.mother_name}</p>
          </div>
          <div className="av-field">
            <label>Mother's Occupation</label>
            <p>{formatAnswer(application.mother_occupation)}</p>
          </div>
          <div className="av-field">
            <label>Mother's Education</label>
            <p>{formatAnswer(application.mother_education)}</p>
          </div>
          <div className="av-field">
            <label>Household Income</label>
            <p>{application.household_income_bracket || 'N/A'}</p>
          </div>
          <div className="av-field">
            <label>Family Size</label>
            <p>{hasAnswer(application.family_size) ? `${application.family_size} members` : 'N/A'}</p>
          </div>
          <div className="av-field">
            <label>Housing Situation</label>
            <p>{formatAnswer(application.housing_situation)}</p>
          </div>
          <div className="av-field">
            <label>Number of Siblings</label>
            <p>{formatAnswer(application.num_siblings)}</p>
          </div>
          <div className="av-field">
            <label>Siblings Currently Studying</label>
            <p>{formatAnswer(application.num_siblings_studying)}</p>
          </div>
          <div className="av-field full">
            <label>Other Scholarship</label>
            <p>{application.has_other_scholarship
              ? `Yes — ${application.other_scholarship_details || 'Not specified'}`
              : 'No other scholarship'}</p>
          </div>
        </div>
      </div>

      {/* LGU-defined custom questions the student answered */}
      {application.extra_fields && Object.values(application.extra_fields).some(hasAnswer) && (
        <div className="av-card">
          <h3 className="av-card-title">Additional Information</h3>
          <div className="av-grid">
            {Object.entries(application.extra_fields)
              .filter(([, value]) => hasAnswer(value))
              .map(([key, value]) => {
                const def = customFieldDefs.find(f => f.key === key)
                const label = def ? def.label : key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
                return (
                  <div key={key} className={`av-field${def?.type === 'textarea' ? ' full' : ''}`}>
                    <label>{label}</label>
                    <p>{formatAnswer(value)}</p>
                  </div>
                )
              })}
          </div>
        </div>
      )}

      {/* Academic Info */}
      <div className="av-card">
        <h3 className="av-card-title">Academic Information</h3>
        <div className="av-grid">
          <div className="av-field full">
            <label>School / University</label>
            <p>{application.school}</p>
          </div>
          <div className="av-field full">
            <label>School Address</label>
            <p>{application.school_address}</p>
          </div>
          <div className="av-field">
            <label>Course</label>
            <p>{application.course}</p>
          </div>
          <div className="av-field">
            <label>Year Level</label>
            <p>{application.year_level}</p>
          </div>
          <div className="av-field">
            <label>GWA / GPA</label>
            <p className="av-gwa">{application.gpa}</p>
          </div>
          <div className="av-field">
            <label>Academic Year</label>
            <p>{application.academic_year}</p>
          </div>
          <div className="av-field">
            <label>Semester</label>
            <p>{application.semester}</p>
          </div>
        </div>
      </div>

      {/* Documents */}
      <Reveal className="av-card">
        <h3 className="av-card-title">Documents</h3>
        {uploadError && <p className="av-withdraw-error">{uploadError}</p>}

        <div className="doc-stats">
          <StatTile value={uploaded} label="Uploaded" color="#059669" index={0} />
          <StatTile value={missing} label="Missing" color="#DC2626" index={1} />
          <StatTile value={totalRequired} label="Total Required" color="var(--accent)" index={2} />
          <StatTile
            value={`${totalRequired > 0 ? Math.round((uploaded / totalRequired) * 100) : 0}%`}
            label="Completion" color="#0F172A" index={3}
          />
        </div>

        <div className="doc-progress-track">
          <div className="doc-progress-fill"
            style={{ width: `${totalRequired > 0 ? (uploaded / totalRequired) * 100 : 0}%` }} />
        </div>

        <p className="doc-list-sub">Accepted formats: PDF, JPG, PNG — Max size: 5MB per file</p>

        <div className="doc-list">
          {checklistDocs.map(doc => (
            <div
              key={doc.id}
              className={`doc-item ${dragOver === doc.id ? 'drag-over' : ''}`}
              onDragOver={e => { if (!docsLocked) { e.preventDefault(); setDragOver(doc.id) } }}
              onDragLeave={() => setDragOver(null)}
              onDrop={e => { if (!docsLocked) handleDrop(doc.id, e) }}>

              <div className="doc-info">
                <div>
                  <p className="doc-name">
                    {doc.document_name}
                    {doc.required && <span className="required-star"> *</span>}
                  </p>
                  {doc.file && <p className="doc-filename">{doc.file.name}</p>}
                  {doc.status === 'Uploaded' && !doc.file && (
                    <p className="doc-filename">Previously uploaded</p>
                  )}
                  {doc.status === 'Uploaded' && checking[doc.document_name] && (
                    <p className="doc-hint">Checking document…</p>
                  )}
                  {doc.status === 'Uploaded' && !checking[doc.document_name] && doc.warning && (
                    <p className="doc-warning" role="alert">{doc.warning}</p>
                  )}
                  {doc.status === 'Missing' && (
                    <p className="doc-hint">Drag & drop or click Upload</p>
                  )}
                  {doc.status === 'Not Required' && (
                    <p className="doc-hint">Only required for specific applicants</p>
                  )}
                </div>
              </div>

              <div className="doc-actions">
                <span className={`badge ${getStatusClass(doc.status)}`}>
                  {doc.status}
                </span>
                {docsLocked ? null : doc.status === 'Uploaded' ? (
                  <button className="btn-remove" onClick={() => handleRemove(doc.id)}>
                    Remove
                  </button>
                ) : (
                  <div>
                    <button className="btn-upload"
                      onClick={() => document.getElementById(`doc-${doc.id}`).click()}>
                      Upload
                    </button>
                    <input
                      type="file"
                      id={`doc-${doc.id}`}
                      style={{ display: 'none' }}
                      accept=".pdf,.jpg,.jpeg,.png"
                      onChange={e => handleUpload(doc.id, e.target.files[0])}
                    />
                  </div>
                )}
              </div>

            </div>
          ))}
        </div>

        <div className="doc-note">
          <p>Fields marked with <strong>*</strong> are required. Make sure all required documents are uploaded.</p>
        </div>
      </Reveal>

      {/* Footer */}
      {withdrawError && <p className="av-withdraw-error">{withdrawError}</p>}
      <div className="av-footer">
        <button className="av-btn-secondary"
          onClick={() => navigate('/student/dashboard')}>
          ← Back to Dashboard
        </button>
        {adminRequestedChanges ? (
          <button className="av-btn-primary" onClick={() => navigate('/student/application', { state: editApplicationState })}>
            Edit Application
          </button>
        ) : status === 'Withdrawn' ? (
          <button className="av-btn-primary" onClick={() => navigate('/student/application')}>
            Submit New Application
          </button>
        ) : status === 'Approved' || status === 'Rejected' ? (
          <span style={{ fontSize: '13px', color: '#4b5563' }}>
            This application has already been scored and can no longer be withdrawn.
          </span>
        ) : (
          <button className="av-btn-danger" onClick={handleWithdraw} disabled={withdrawing}>
            {withdrawing ? 'Withdrawing…' : 'Withdraw Application'}
          </button>
        )}
      </div>

    </div>
  )
}

export default ApplicantDetails
