import { useState, useEffect, useRef } from 'react'
import { apiFetch, displayStatus } from '../api'
import './ApplicantModal.css'

// Must match backend's SELFIE_DOC_LABEL / ID_DOC_LABEL (backend/app.py). The selfie is
// pulled out of the generic documents grid below and shown side-by-side with the ID
// photo instead, for the reviewer to manually compare - no automated face-matching.
const SELFIE_DOC_LABEL = 'Selfie / Face Photo'
const ID_DOC_LABEL = 'School ID'

// A multi-option checkbox field stores its answer as an array - empty means
// "nothing selected", same as an empty string for every other field type.
function hasValue(v) {
  return Array.isArray(v) ? v.length > 0 : Boolean(v)
}

// LGU-configurable (see admin Form Builder) - fetched at runtime, not hardcoded.
function mergeDocuments(documents, requiredDocTypes) {
  return requiredDocTypes.map(docType => {
    const uploaded = documents.find(d => d.document_name === docType.label)
    if (uploaded) return { label: docType.label, status: uploaded.status || 'Uploaded', ocr_status: uploaded.ocr_status }
    return { label: docType.label, status: docType.required ? 'Missing' : 'Not Required', ocr_status: null }
  })
}

function ScoreBar({ label, value, color }) {
  return (
    <div className="score-bar-row">
      <div className="score-bar-header">
        <span className="score-bar-label">{label}</span>
        <span className="score-bar-value">{value}%</span>
      </div>
      <div className="score-bar-track">
        <div className="score-bar-fill"
          style={{ width: `${value}%`, background: color }} />
      </div>
    </div>
  )
}

function ApplicantModal({ applicant, onClose, onStatusChange }) {

  const [updating, setUpdating] = useState(false)
  const [updateSuccess, setUpdateSuccess] = useState('')
  const [runningOcr, setRunningOcr] = useState(false)
  const [ocrProgress, setOcrProgress] = useState(null) // { done, total } while documents are being OCR-checked
  const [ocrCheckWarnings, setOcrCheckWarnings] = useState(null)
  const [auditTrail, setAuditTrail] = useState([])
  const [loadingAudit, setLoadingAudit] = useState(false)
  const [mlData, setMlData] = useState(null)
  const [documents, setDocuments] = useState([])
  const [viewingDoc, setViewingDoc] = useState('')
  const [customFieldDefs, setCustomFieldDefs] = useState([])
  const [requiredDocTypes, setRequiredDocTypes] = useState([])
  const [selfieImgUrl, setSelfieImgUrl] = useState('')
  const [idImgUrl, setIdImgUrl] = useState('')
  const [remarks, setRemarks] = useState('')
  const modalRef = useRef(null)
  const closeBtnRef = useRef(null)
  const remarksRef = useRef(null)
  const currentApplicantIdRef = useRef(null)

  // ALL HOOKS BEFORE EARLY RETURN

  // Escape-to-close, focus moved into the modal on open, and Tab trapped
  // within it while it's open - without this, keyboard-only users have no
  // way to dismiss the modal short of tabbing all the way to the close button.
  useEffect(() => {
    if (!applicant) return

    closeBtnRef.current?.focus()

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key !== 'Tab' || !modalRef.current) return
      const focusable = modalRef.current.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [applicant, onClose])

 useEffect(() => {
  currentApplicantIdRef.current = applicant?.id ?? null
  if (!applicant) return

  setRemarks('')
  // This modal stays mounted between applicants, so clear the last one's score.
  setMlData(null)

  // Fetch audit trail
  setLoadingAudit(true)
  apiFetch(`/api/audit-trail/${applicant.id}`)
    .then(res => res.json())
    .then(data => {
      setAuditTrail(data.trail || [])
      setLoadingAudit(false)
    })
    .catch(() => setLoadingAudit(false))

  // A score is only shown once the applicant has been decided; before that it
  // appears when "Start Eligibility" returns it. This fetch is just for the
  // per-factor breakdown of an already-decided applicant.
  const applicantId = applicant.id
  const status = applicant.application_status || applicant.status
  if (status === 'Approved' || status === 'Rejected') {
    apiFetch(`/api/score-applicant/${applicantId}`)
      .then(res => res.json())
      .then(data => {
        if (data.ml_score !== undefined && currentApplicantIdRef.current === applicantId) {
          setMlData(data)
        }
      })
      .catch(() => {})
  }

  // Fetch the applicant's actual uploaded documents
  apiFetch(`/api/documents/${applicant.id}`)
    .then(res => res.json())
    .then(data => setDocuments(data.documents || []))
    .catch(() => setDocuments([]))

  // Field labels for this LGU's custom fields, to display applicant.extra_fields nicely
  apiFetch('/api/form-fields')
    .then(res => res.json())
    .then(data => setCustomFieldDefs(data.fields || []))
    .catch(() => setCustomFieldDefs([]))

  // This LGU's configured document checklist (see admin Form Builder)
  apiFetch('/api/document-requirements')
    .then(res => res.json())
    .then(data => setRequiredDocTypes((data.requirements || []).filter(r => r.enabled)))
    .catch(() => setRequiredDocTypes([]))
}, [applicant])

  // Fetch the selfie + ID photos as images (not the "open in new tab" flow the rest of
  // the documents grid uses) so they can be shown side-by-side for visual comparison.
  useEffect(() => {
    if (!applicant) return

    let cancelled = false
    const urls = []

    const loadImage = (documentName, setUrl) => {
      const doc = documents.find(d => d.document_name === documentName)
      if (!doc || (doc.status !== 'Uploaded' && doc.status !== 'Submitted')) {
        setUrl('')
        return
      }
      apiFetch(`/api/documents/${applicant.id}/view?document_name=${encodeURIComponent(documentName)}`)
        .then(res => (res.ok ? res.blob() : null))
        .then(blob => {
          if (cancelled || !blob) return
          const url = URL.createObjectURL(blob)
          urls.push(url)
          setUrl(url)
        })
        .catch(() => {})
    }

    loadImage(SELFIE_DOC_LABEL, setSelfieImgUrl)
    loadImage(ID_DOC_LABEL, setIdImgUrl)

    return () => {
      cancelled = true
      urls.forEach(URL.revokeObjectURL)
    }
  }, [applicant, documents])

  // EARLY RETURN AFTER ALL HOOKS
  if (!applicant) return null

  const profile = { ...applicant }
  const currentStatus = applicant.application_status || applicant.status || ''
  const isApproved = currentStatus === 'Approved'
  const isRejected = currentStatus === 'Rejected'
  const isWithdrawn = currentStatus === 'Withdrawn'
  const isPending = !isApproved && !isRejected && !isWithdrawn
  // Display-only: an eligible applicant bumped by the accepted-applicant limit
  // reads as "Waitlisted" rather than "Rejected" - isRejected etc. above still
  // drive actual behavior (buttons, overrides) off the real stored status.
  const displayCurrentStatus = displayStatus(currentStatus, applicant.ml_status)

  // OCR-checks every pending document, one per request: OCR is slow on a small
  // server, and a single request covering all of them can outlive the server's
  // timeout and get dropped. Each finished document is saved server-side, so a
  // dropped connection only costs the document in flight - checking again
  // picks up where it stopped. Resolves { ok: true, warnings } or
  // { ok: false, message } (no message when the modal moved to another
  // applicant); network failures reject.
  const checkAllDocuments = async () => {
    const applicantId = profile.id
    const attempted = []
    let done = 0
    try {
      while (true) {
        const response = await apiFetch(`/api/applications/${applicantId}/check-documents`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ exclude: attempted })
        })
        const data = await response.json()
        if (!response.ok) return { ok: false, message: data.error || 'Could not run the OCR check' }
        if (currentApplicantIdRef.current !== applicantId) return { ok: false }

        done += data.results.length
        attempted.push(...data.results.map(r => r.document_name))
        setOcrProgress({ done, total: done + data.remaining })

        const docsResponse = await apiFetch(`/api/documents/${applicantId}`).catch(() => null)
        const docsData = docsResponse ? await docsResponse.json().catch(() => null) : null
        if (docsData && currentApplicantIdRef.current === applicantId) {
          setDocuments(docsData.documents || [])
        }

        if (data.remaining === 0 || data.results.length === 0) {
          return { ok: true, warnings: data.warnings || [] }
        }
      }
    } finally {
      setOcrProgress(null)
    }
  }

  const handleRunOcrCheck = async () => {
    setRunningOcr(true)
    try {
      const outcome = await checkAllDocuments()
      if (outcome.ok) {
        setOcrCheckWarnings(outcome.warnings)
      } else if (outcome.message) {
        alert(outcome.message)
      }
    } catch {
      alert('Lost connection to the server during the OCR check. Documents already checked were saved - tap "Run OCR Check" to continue.')
    }
    setRunningOcr(false)
  }

  const handleViewDoc = async (doc) => {
    const documentName = doc.label || doc.document_name
    setViewingDoc(documentName)
    try {
      const response = await apiFetch(
        `/api/documents/${profile.id}/view?document_name=${encodeURIComponent(documentName)}`
      )
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        alert(data.error || 'Could not load this document')
        return
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank')
    } catch {
      alert('Cannot connect to server')
    }
    setViewingDoc('')
  }

  const handleStatusUpdate = async (newStatus) => {
    const msg = newStatus === 'Newly Submitted'
      ? 'Move this applicant back to the Applications list?'
      : `Change status to ${newStatus}?`
    if (!window.confirm(msg)) return

    setUpdating(true)
    try {
      const response = await apiFetch(
        `/api/applications/${applicant.id}/status`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            status: newStatus,
            old_status: currentStatus,
            remarks: remarks.trim()
          })
        }
      )
      if (response.ok) {
        setUpdateSuccess(newStatus)
        if (onStatusChange) await onStatusChange()
        setTimeout(() => {
          onClose()
          setUpdateSuccess('')
        }, 1000)
      } else {
        alert('Failed to update status')
      }
    } catch {
      alert('Cannot connect to server')
    }
    setUpdating(false)
  }

  const handleRequestChanges = async () => {
    if (!remarks.trim()) {
      alert('Please enter a comment describing what needs to change before requesting changes.')
      remarksRef.current?.focus()
      return
    }
    if (!window.confirm(
      "Send this comment to the applicant and mark their application as needing changes? " +
      "They'll be able to edit and resubmit."
    )) return

    setUpdating(true)
    try {
      const response = await apiFetch(`/api/applications/${applicant.id}/request-changes`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ comment: remarks.trim() })
      })
      const data = await response.json()
      if (response.ok) {
        setUpdateSuccess('Changes Requested')
        if (onStatusChange) await onStatusChange()
        setTimeout(() => {
          onClose()
          setUpdateSuccess('')
        }, 1200)
      } else {
        alert(data.error || 'Could not request changes for this applicant')
      }
    } catch {
      alert('Cannot connect to server')
    }
    setUpdating(false)
  }

  const handleVerifyAndDecide = async () => {
    if (!window.confirm(
      "This will let the eligibility model decide Approved/Rejected (any documents " +
      "not yet OCR-checked will be checked automatically first). Any issues found " +
      "will be shown for your review - you can still Reconsider/Revoke afterward " +
      "if you disagree. Continue?"
    )) return

    setUpdating(true)
    try {
      // OCR first, a document at a time, so the decision request below finds
      // nothing left to OCR and stays fast.
      const ocr = await checkAllDocuments()
      if (!ocr.ok) {
        if (ocr.message) alert(ocr.message)
        setUpdating(false)
        return
      }

      const response = await apiFetch(`/api/applications/${applicant.id}/verify`, {
        method: 'PUT'
      })
      const data = await response.json()

      if (response.ok) {
        setMlData(data)
        setUpdateSuccess(data.status)
        if (onStatusChange) await onStatusChange()
        setTimeout(() => {
          onClose()
          setUpdateSuccess('')
        }, 1200)
      } else {
        alert(data.error || 'Could not decide eligibility for this applicant')
      }
    } catch {
      alert('Cannot connect to server. Documents already OCR-checked were saved - tap "Start Eligibility" again to continue.')
    }
    setUpdating(false)
  }

  const getScoreColor = (score) => {
    if (score >= 80) return '#10b981'
    if (score >= 60) return '#f59e0b'
    return '#ef4444'
  }

  const getDocBadge = (status) => {
    if (status === 'Submitted' || status === 'Uploaded') return 'doc-submitted'
    if (status === 'Not Required') return 'doc-not-required'
    return 'doc-missing'
  }

  // Official only: a decided applicant, or the result Start Eligibility just returned.
  const hasOfficialScore = isApproved || isRejected || Boolean(mlData)
  const mlScore = mlData?.ml_score ?? profile.ml_score ?? 'N/A'
  const mlStatus = mlData?.ml_status ?? profile.ml_status ?? 'Pending'
  const mlBreakdown = mlData?.breakdown ?? []

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-container"
        onClick={e => e.stopPropagation()}
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="applicant-modal-name">

        {/* Header */}
        <div className="modal-header">
          <div className="modal-applicant-info">
            <div className="modal-avatar">
              {(profile.full_name || 'A')
                .split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
            </div>
            <div className="modal-name-block">
              <h2 className="modal-name" id="applicant-modal-name">{profile.full_name}</h2>
              <p className="modal-course">{profile.course} — {profile.year_level}</p>
              <p className="modal-email">{profile.email}</p>
            </div>
          </div>
          <div className="modal-header-right">
            <span className={`modal-status-badge ${
              isApproved ? 'badge-green' :
              isWithdrawn ? 'badge-gray' :
              isRejected ? (displayCurrentStatus === 'Waitlisted' ? 'badge-yellow' : 'badge-red') : 'badge-yellow'
            }`}>
              {displayCurrentStatus || 'Pending'}
            </span>
            <button className="modal-close" onClick={onClose} ref={closeBtnRef} aria-label="Close">&times;</button>
          </div>
        </div>

        {/* Body */}
        <div className="modal-body">

          {/* ML Score */}
          <div className="modal-section">
            <h3 className="section-title">ML Eligibility Score</h3>
            {hasOfficialScore ? (
              <div className="ml-score-card">
                <div className="ml-score-main">
                  <div className="ml-score-circle"
                    style={{ borderColor: getScoreColor(mlScore) }}>
                    <span className="ml-score-number"
                      style={{ color: getScoreColor(mlScore) }}>
                      {mlScore}
                    </span>
                    <span className="ml-score-label">/ 100</span>
                  </div>
                  <div>
                    <p className="ml-status-label">Status</p>
                    <span className={`badge ${mlStatus === 'Eligible' ? 'badge-green' : 'badge-red'}`}>
                      {mlStatus}
                    </span>
                    {mlData?.regressor_cutoff !== undefined && (
                      <p className="ml-note">Score cutoff for reference: {mlData.regressor_cutoff}</p>
                    )}
                  </div>
                </div>
                <div className="ml-breakdown">
                  {mlBreakdown.map((item, i) => (
                    <ScoreBar key={i} {...item} />
                  ))}
                </div>
              </div>
            ) : (
              <div className="ml-score-card">
                <p className="ml-score-pending">
                  {isWithdrawn
                    ? 'No score - this application is withdrawn.'
                    : 'Not scored yet. Tap "Start Eligibility" to check the documents and run the eligibility model.'}
                </p>
              </div>
            )}
            {(mlData?.warnings || []).length > 0 && (
              <div className="ocr-fraud-flags" style={{ marginTop: '10px' }}>
                <p className="ml-status-label">Worth a look before deciding:</p>
                {mlData.warnings.map((w, i) => (
                  <p key={i} className="ocr-fraud-flag">⚠ {w}</p>
                ))}
              </div>
            )}
          </div>

          {/* Personal Info */}
          <div className="modal-section">
            <h3 className="section-title">Personal Information</h3>
            <div className="info-grid">
              <div className="info-field">
                <label>Full Name</label>
                <p>{profile.full_name}</p>
              </div>
              <div className="info-field">
                <label>Email Address</label>
                <p>{profile.email}</p>
              </div>
              <div className="info-field">
                <label>Contact Number</label>
                <p>{profile.contact_number}</p>
              </div>
              <div className="info-field">
                <label>Date of Birth</label>
                <p>{profile.date_of_birth
                  ? new Date(profile.date_of_birth).toLocaleDateString('en-PH', {
                      month: 'long', day: 'numeric', year: 'numeric'
                    })
                  : 'N/A'}</p>
              </div>
              <div className="info-field">
                <label>Gender</label>
                <p>{profile.gender}</p>
              </div>
              <div className="info-field">
                <label>Religion</label>
                <p>{profile.religion}</p>
              </div>
              <div className="info-field full">
                <label>Address</label>
                <p>{profile.address}</p>
              </div>
            </div>
          </div>

          {/* Parental Details */}
          <div className="modal-section">
            <h3 className="section-title">Parental & Financial Details</h3>
            <div className="info-grid">
              <div className="info-field">
                <label>Father's Name</label>
                <p>{profile.father_name}</p>
              </div>
              <div className="info-field">
                <label>Father's Occupation</label>
                <p>{profile.father_occupation}</p>
              </div>
              <div className="info-field">
                <label>Mother's Name</label>
                <p>{profile.mother_name}</p>
              </div>
              <div className="info-field">
                <label>Mother's Occupation</label>
                <p>{profile.mother_occupation}</p>
              </div>
              <div className="info-field">
                <label>Household Income</label>
                <p>{profile.household_income}</p>
              </div>
              <div className="info-field">
                <label>Family Size</label>
                <p>{profile.family_size} members</p>
              </div>
              <div className="info-field full">
                <label>Other Scholarship</label>
                <p>
                  {profile.has_other_scholarship
                    ? <span style={{ color: '#ef4444', fontWeight: 600 }}>
                        Yes — {profile.other_scholarship_details || 'Not specified'}
                      </span>
                    : <span style={{ color: '#10b981', fontWeight: 600 }}>
                        No other scholarship
                      </span>
                  }
                </p>
              </div>
            </div>
          </div>

          {/* LGU-defined custom fields, if this LGU has any configured */}
          {profile.extra_fields && Object.keys(profile.extra_fields).some(k => hasValue(profile.extra_fields[k])) && (
            <div className="modal-section">
              <h3 className="section-title">Additional Information</h3>
              <div className="info-grid">
                {Object.entries(profile.extra_fields)
                  .filter(([, value]) => hasValue(value))
                  .map(([key, value]) => {
                    const def = customFieldDefs.find(f => f.key === key)
                    const label = def ? def.label : key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
                    return (
                      <div key={key} className="info-field">
                        <label>{label}</label>
                        <p>{Array.isArray(value) ? value.join(', ') : String(value)}</p>
                      </div>
                    )
                  })}
              </div>
            </div>
          )}

          {/* Academic Info */}
          <div className="modal-section">
            <h3 className="section-title">Academic Information</h3>
            <div className="info-grid">
              <div className="info-field full">
                <label>School / University</label>
                <p>{profile.school}</p>
              </div>
              <div className="info-field full">
                <label>School Address</label>
                <p>{profile.school_address}</p>
              </div>
              <div className="info-field">
                <label>Course</label>
                <p>{profile.course}</p>
              </div>
              <div className="info-field">
                <label>Year Level</label>
                <p>{profile.year_level}</p>
              </div>
              <div className="info-field">
                <label>GWA / GPA</label>
                <p className="gwa-value">{profile.gpa}</p>
              </div>
              <div className="info-field">
                <label>Academic Year</label>
                <p>{profile.academic_year}</p>
              </div>
              <div className="info-field">
                <label>Semester</label>
                <p>{profile.semester}</p>
              </div>
            </div>
          </div>

          {/* Identity Verification (selfie vs. ID photo, manual comparison) */}
          <div className="modal-section">
            <h3 className="section-title">Identity Verification</h3>
            <p className="identity-note">
              Compare the two photos below to confirm this is the same person. This is a
              manual check — no automated face-matching is performed.
            </p>
            <div className="identity-compare">
              <div className="identity-photo">
                <p className="identity-photo-label">Selfie</p>
                {selfieImgUrl
                  ? <img src={selfieImgUrl} alt="Applicant selfie" />
                  : <div className="identity-photo-placeholder">Not yet uploaded</div>}
              </div>
              <div className="identity-photo">
                <p className="identity-photo-label">{ID_DOC_LABEL}</p>
                {idImgUrl
                  ? <img src={idImgUrl} alt="Applicant ID" />
                  : <div className="identity-photo-placeholder">Not yet uploaded</div>}
              </div>
            </div>
          </div>

          {/* Documents */}
          <div className="modal-section">
            <div className="section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Submitted Documents</span>
              <button
                className="btn-verify-doc"
                disabled={runningOcr || updating}
                onClick={handleRunOcrCheck}>
                {runningOcr
                  ? (ocrProgress ? `Running OCR (${ocrProgress.done}/${ocrProgress.total})...` : 'Running OCR...')
                  : 'Run OCR Check'}
              </button>
            </div>
            <div className="docs-grid">
              {mergeDocuments(documents, requiredDocTypes.filter(r => r.label !== SELFIE_DOC_LABEL)).map((doc, i) => (
                <div key={i} className="doc-item">
                  <div className="doc-item-left">
                    <span className="doc-label">{doc.label}</span>
                    <span className={`doc-badge ${getDocBadge(doc.status)}`}>
                      {doc.status}
                    </span>
                    {doc.status === 'Uploaded' && (
                      <span className={`doc-badge ${
                        doc.ocr_status === 'Verified' ? 'badge-green' :
                        doc.ocr_status === 'Partially Verified' ? 'badge-yellow' :
                        doc.ocr_status === 'Failed Verification' ? 'badge-red' : 'badge-gray'
                      }`}>
                        {doc.ocr_status || 'Not verified yet'}
                      </span>
                    )}
                  </div>
                  <div className="doc-item-actions">
                    {(doc.status === 'Submitted' || doc.status === 'Uploaded') && (
                      <button
                        className="btn-verify-doc"
                        disabled={viewingDoc === (doc.label || doc.document_name)}
                        onClick={() => handleViewDoc(doc)}>
                        {viewingDoc === (doc.label || doc.document_name) ? 'Opening...' : 'View'}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {ocrCheckWarnings !== null && (
              ocrCheckWarnings.length > 0 ? (
                <div className="ocr-fraud-flags" style={{ marginTop: '10px' }}>
                  {ocrCheckWarnings.map((w, i) => (
                    <p key={i} className="ocr-fraud-flag">⚠ {w}</p>
                  ))}
                </div>
              ) : (
                <p className="ml-note" style={{ marginTop: '10px' }}>No issues found.</p>
              )
            )}
          </div>

          {/* Audit Trail */}
          <div className="modal-section">
            <h3 className="section-title">Audit Trail</h3>
            {loadingAudit ? (
              <p style={{ fontSize: '13px', color: '#4d4d4d' }}>Loading audit trail...</p>
            ) : auditTrail.length === 0 ? (
              <div className="audit-empty">
                <p>No actions recorded yet for this application.</p>
              </div>
            ) : (
              <div className="audit-list">
                {auditTrail.map((entry, i) => (
                  <div key={i} className="audit-row">
                    <div className="audit-content">
                      <p className="audit-action">{entry.action}</p>
                      <p className="audit-meta">
                        By <strong>{entry.performed_by}</strong>
                        {' · '}
                        {new Date(entry.performed_at).toLocaleDateString('en-PH', {
                          month: 'long', day: 'numeric', year: 'numeric',
                          hour: '2-digit', minute: '2-digit'
                        })}
                      </p>
                      {entry.old_status && (
                        <p className="audit-status-change">
                          <span className="audit-old">{entry.old_status}</span>
                          {' → '}
                          <span className="audit-new">
                            {entry.new_status === 'Rejected' && entry.performed_by_role === 'system'
                              ? 'Waitlisted' : entry.new_status}
                          </span>
                        </p>
                      )}
                      {entry.remarks && (
                        <p className="audit-remarks">"{entry.remarks}"</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>

        {/* Footer */}
        <div className="modal-footer">
          {(isApproved || isRejected || isPending) && (
            <div className="remarks-field">
              <label htmlFor="applicant-remarks">
                {isPending
                  ? 'Comment for the applicant (required to Request Changes)'
                  : 'Note (optional, visible in the audit trail)'}
              </label>
              <textarea
                id="applicant-remarks"
                ref={remarksRef}
                rows={2}
                placeholder="e.g. what's missing, or why this decision is being reconsidered..."
                value={remarks}
                onChange={e => setRemarks(e.target.value)}
              />
            </div>
          )}

          <div className="modal-footer-row">
          <button className="btn-close-modal" onClick={onClose}>Close</button>

          {updateSuccess && (() => {
            if (updateSuccess === 'Changes Requested') {
              return <div className="update-success success-yellow">Changes Requested</div>
            }
            const label = displayStatus(updateSuccess, mlData?.ml_status)
            return (
              <div className={`update-success ${
                updateSuccess === 'Approved' ? 'success-green' :
                label === 'Waitlisted' ? 'success-yellow' : 'success-red'
              }`}>
                {updateSuccess === 'Approved'
                  ? 'Application Approved'
                  : label === 'Waitlisted'
                  ? 'Applicant Waitlisted'
                  : updateSuccess === 'Rejected'
                  ? 'Application Rejected'
                  : 'Status Updated'}
              </div>
            )
          })()}

          <div className="footer-actions">
            {isApproved && (
              <button className="btn-reject-modal"
                disabled={updating || runningOcr}
                onClick={() => handleStatusUpdate('Newly Submitted')}>
                {updating ? 'Updating...' : 'Revoke Approval'}
              </button>
            )}
            {isRejected && (
              <button className="btn-approve-modal"
                disabled={updating || runningOcr}
                onClick={() => handleStatusUpdate('Newly Submitted')}>
                {updating ? 'Updating...' : 'Reconsider'}
              </button>
            )}
            {isPending && (
              <button className="btn-reject-modal"
                disabled={updating || runningOcr}
                onClick={handleRequestChanges}>
                {updating ? 'Sending...' : 'Request Changes'}
              </button>
            )}
            {isPending && (
              <button className="btn-approve-modal"
                disabled={updating || runningOcr}
                onClick={handleVerifyAndDecide}>
                {updating
                  ? (ocrProgress ? `Checking documents ${ocrProgress.done}/${ocrProgress.total}...` : 'Starting...')
                  : 'Start Eligibility'}
              </button>
            )}
            {isWithdrawn && (
              <span style={{ fontSize: '13px', color: '#4b5563' }}>
                {applicant.admin_comment
                  ? `Changes were requested: "${applicant.admin_comment}"`
                  : 'This application was withdrawn by the applicant.'}
              </span>
            )}
          </div>
          </div>
        </div>

      </div>
    </div>
  )
}

export default ApplicantModal