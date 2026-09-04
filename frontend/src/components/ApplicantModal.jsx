import { useState, useEffect, useRef } from 'react'
import { apiFetch, displayStatus } from '../api'
import './ApplicantModal.css'

const MOCK_BREAKDOWN = [
  { label: 'GPA Score', value: 95, color: '#10b981' },
  { label: 'Income Score', value: 88, color: '#7c3aed' },
  { label: 'Family Size Score', value: 80, color: '#2563eb' },
  { label: 'Location Score', value: 72, color: '#f59e0b' },
]

// LGU-configurable (see admin Form Builder) - fetched at runtime, not hardcoded.
function mergeDocuments(documents, requiredDocTypes) {
  return requiredDocTypes.map(docType => {
    const uploaded = documents.find(d => d.document_name === docType.label)
    if (uploaded) return { label: docType.label, status: uploaded.status || 'Uploaded' }
    return { label: docType.label, status: docType.required ? 'Missing' : 'Not Required' }
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

  const [ocrResult, setOcrResult] = useState(null)
  const [verifying, setVerifying] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [updateSuccess, setUpdateSuccess] = useState('')
  const [auditTrail, setAuditTrail] = useState([])
  const [loadingAudit, setLoadingAudit] = useState(false)
  const [mlData, setMlData] = useState(null)
  const [documents, setDocuments] = useState([])
  const [viewingDoc, setViewingDoc] = useState('')
  const [customFieldDefs, setCustomFieldDefs] = useState([])
  const [requiredDocTypes, setRequiredDocTypes] = useState([])
  const modalRef = useRef(null)
  const closeBtnRef = useRef(null)

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
  if (!applicant) return

  // Fetch audit trail
  setLoadingAudit(true)
  apiFetch(`/api/audit-trail/${applicant.id}`)
    .then(res => res.json())
    .then(data => {
      setAuditTrail(data.trail || [])
      setLoadingAudit(false)
    })
    .catch(() => setLoadingAudit(false))

  // Fetch real ML score (only meaningful once documents have been verified)
  apiFetch(`/api/score-applicant/${applicant.id}`)
    .then(res => res.json())
    .then(data => {
      if (data.ml_score !== undefined) {
        setMlData(data)
      }
    })
    .catch(() => {})

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

  const handleVerifyDoc = async (doc, applicantId) => {
    setVerifying(true)
    setOcrResult(null)
    try {
      const response = await apiFetch('/api/verify-document', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          applicant_id: applicantId || 1,
          document_name: doc.label || doc.document_name
        })
      })
      const data = await response.json()
      setOcrResult(data)
    } catch {
      setOcrResult({ status: 'Error', error: 'Cannot connect to server' })
    }
    setVerifying(false)
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
            remarks: ''
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

  const handleVerifyAndDecide = async () => {
    if (!window.confirm(
      "Confirm the submitted documents are correct and complete. " +
      "The eligibility model will then decide Approved/Rejected automatically."
    )) return

    setUpdating(true)
    try {
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
      alert('Cannot connect to server')
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

  const mlScore = mlData?.ml_score ?? profile.ml_score ?? 'N/A'
  const mlStatus = mlData?.ml_status ?? profile.ml_status ?? 'Pending'
  const mlBreakdown = mlData?.breakdown ?? MOCK_BREAKDOWN

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
            <div>
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
                  <p className="ml-note">
                    {mlData?.regressor_cutoff !== undefined
                      ? `Score cutoff for reference: ${mlData.regressor_cutoff}`
                      : 'Preview only - verify documents to make this the official decision'}
                  </p>
                </div>
              </div>
              <div className="ml-breakdown">
                {mlBreakdown.map((item, i) => (
                  <ScoreBar key={i} {...item} />
                ))}
              </div>
            </div>
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
          {profile.extra_fields && Object.keys(profile.extra_fields).some(k => profile.extra_fields[k]) && (
            <div className="modal-section">
              <h3 className="section-title">Additional Information</h3>
              <div className="info-grid">
                {Object.entries(profile.extra_fields)
                  .filter(([, value]) => value)
                  .map(([key, value]) => {
                    const def = customFieldDefs.find(f => f.key === key)
                    const label = def ? def.label : key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
                    return (
                      <div key={key} className="info-field">
                        <label>{label}</label>
                        <p>{String(value)}</p>
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

          {/* Documents */}
          <div className="modal-section">
            <h3 className="section-title">Submitted Documents</h3>
            <div className="docs-grid">
              {mergeDocuments(documents, requiredDocTypes).map((doc, i) => (
                <div key={i} className="doc-item">
                  <div className="doc-item-left">
                    <span className="doc-label">{doc.label}</span>
                    <span className={`doc-badge ${getDocBadge(doc.status)}`}>
                      {doc.status}
                    </span>
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
                    {isPending && (doc.status === 'Submitted' || doc.status === 'Uploaded') && (
                      <button
                        className="btn-verify-doc"
                        onClick={() => handleVerifyDoc(doc, profile.id)}>
                        Verify
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {verifying && (
              <div className="ocr-loading">Running OCR verification...</div>
            )}

            {ocrResult && (
              <div className={`ocr-result ${
                ocrResult.status === 'Verified' ? 'ocr-verified' :
                ocrResult.status === 'Partially Verified' ? 'ocr-partial' :
                'ocr-failed'
              }`}>
                <div className="ocr-result-header">
                  <h4>OCR Verification Result</h4>
                  <span className="ocr-confidence">Confidence: {ocrResult.confidence}%</span>
                  <span className={`ocr-status-badge ${
                    ocrResult.status === 'Verified' ? 'badge-green' :
                    ocrResult.status === 'Partially Verified' ? 'badge-yellow' :
                    'badge-red'
                  }`}>
                    {ocrResult.status}
                  </span>
                </div>
                {(ocrResult.flags || []).length > 0 && (
                  <div className="ocr-fraud-flags">
                    {ocrResult.flags.map((flag, i) => (
                      <p key={i} className="ocr-fraud-flag">⚠ {flag}</p>
                    ))}
                  </div>
                )}
                <div className="ocr-checks">
                  {(ocrResult.checks || []).map((check, i) => (
                    <div key={i} className="ocr-check-item">
                      <span style={{ color: check.passed ? '#10b981' : '#ef4444', fontWeight: 600 }}>
                        {check.passed ? 'Pass' : 'Fail'}
                      </span>
                      <span>{check.check}</span>
                    </div>
                  ))}
                </div>
                {ocrResult.extracted_text && (
                  <div className="ocr-text-preview">
                    <p className="ocr-text-label">Extracted text preview:</p>
                    <p className="ocr-text">{ocrResult.extracted_text.slice(0, 200)}...</p>
                  </div>
                )}
                {ocrResult.error && (
                  <p style={{ color: '#ef4444', fontSize: '13px' }}>{ocrResult.error}</p>
                )}
              </div>
            )}
          </div>

          {/* Audit Trail */}
          <div className="modal-section">
            <h3 className="section-title">Audit Trail</h3>
            {loadingAudit ? (
              <p style={{ fontSize: '13px', color: '#888' }}>Loading audit trail...</p>
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
          <button className="btn-close-modal" onClick={onClose}>Close</button>

          {updateSuccess && (() => {
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
                disabled={updating}
                onClick={() => handleStatusUpdate('Newly Submitted')}>
                {updating ? 'Updating...' : 'Revoke Approval'}
              </button>
            )}
            {isRejected && (
              <button className="btn-approve-modal"
                disabled={updating}
                onClick={() => handleStatusUpdate('Newly Submitted')}>
                {updating ? 'Updating...' : 'Reconsider'}
              </button>
            )}
            {isPending && (
              <button className="btn-approve-modal"
                disabled={updating}
                onClick={handleVerifyAndDecide}>
                {updating ? 'Deciding...' : 'Verify Documents & Decide Eligibility'}
              </button>
            )}
            {isWithdrawn && (
              <span style={{ fontSize: '13px', color: '#6b7280' }}>This application was withdrawn by the applicant.</span>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}

export default ApplicantModal