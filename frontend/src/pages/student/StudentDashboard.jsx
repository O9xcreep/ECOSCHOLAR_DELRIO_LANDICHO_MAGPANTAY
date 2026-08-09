import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { apiFetch, getUser, displayStatus } from '../../api'
import './StudentDashboard.css'

const STATUS_COLORS = {
  'Approved': 'badge-green',
  'Rejected': 'badge-red',
  'Waitlisted': 'badge-yellow',
  'Newly Submitted': 'badge-blue',
  'Pending Verification': 'badge-yellow',
  'Not Yet Reviewed': 'badge-purple',
  'Incomplete': 'badge-red',
}

const DEFAULT_DOCS = [
  { document_name: 'Enrollment Form', status: 'Missing' },
  { document_name: 'Barangay Endorsement', status: 'Missing' },
  { document_name: 'School ID', status: 'Missing' },
  { document_name: 'Grade 12 Grades', status: 'Missing' },
  { document_name: '4Ps Certificate', status: 'Not Required' },
  { document_name: 'Proof of Income', status: 'Missing' },
]

function StudentDashboard() {
  const navigate = useNavigate()
  const location = useLocation() //Will Used to trigger re fetch on every visit ~~~

  const [application, setApplication] = useState(null)
  const [documents, setDocuments] = useState(DEFAULT_DOCS)
  const [loading, setLoading] = useState(true)

  
  const user = getUser() || {}

  useEffect(() => {
    if (!user.email) {
      setLoading(false)
      return
    }


    setLoading(true)
    setApplication(null)
    setDocuments(DEFAULT_DOCS)

    apiFetch(`/api/student/application?email=${encodeURIComponent(user.email)}`)
      .then(res => res.json())
      .then(data => {
        if (data.application) {
          setApplication(data.application)
          if (data.documents && data.documents.length > 0) {
            setDocuments(data.documents)
          }
        }
        setLoading(false)
      })
      .catch(err => {
        console.error('Dashboard fetch error:', err)
        setLoading(false)
      })
  }, [location.key])

  // Calculate stats
  const uploaded = documents.filter(d => d.status === 'Uploaded').length
  const missing = documents.filter(d => d.status === 'Missing').length
  const requiredDocs = documents.filter(d => d.status !== 'Not Required').length
  const completion = application
    ? Math.round((uploaded / Math.max(requiredDocs, 1)) * 100)
    : 0

  const getStepsDone = () => {
    if (!application) return 0
    const status = application.application_status
    if (status === 'Approved' || status === 'Rejected') return 3
    if (uploaded > 0) return 2
    return 1
  }

  const stepsDone = getStepsDone()

  return (
    <div className="student-dashboard">

      {/* Header */}
      <div className="sd-header">
        <div>
          <h2 className="sd-title">Dashboard</h2>
          <p className="sd-sub">
            Welcome back, <strong>{user.full_name || 'Student'}!</strong>
          </p>
          {application && (
            <p className="sd-appid">
              Application ID: <span className="appid">
                #SP-{String(application.id).padStart(4, '0')}
              </span>
            </p>
          )}
        </div>
      </div>

      {loading ? (
        <div className="sd-loading">Loading your application data...</div>
      ) : (
        <>
          {/* Stats */}
          <div className="sd-stats">
            <div className="sd-stat-card">
              <div>
                <h3>{completion}%</h3>
                <p>Completion</p>
              </div>
            </div>
            <div className="sd-stat-card">
              <div>
                <h3>{stepsDone} / 3</h3>
                <p>Steps Done</p>
              </div>
            </div>
            <div className="sd-stat-card">
              <div>
                <h3>{uploaded}</h3>
                <p>Docs Uploaded</p>
              </div>
            </div>
            <div className="sd-stat-card">
              <div>
                <h3>{missing}</h3>
                <p>Missing Docs</p>
              </div>
            </div>
          </div>

          {/* Bottom Row */}
          <div className="sd-bottom">

            {/* Application Status */}
            <div className="sd-card sd-status-card">
              <div className="sd-card-header">
                <h3>Application Status</h3>
                {application ? (
                  <span className={`badge ${STATUS_COLORS[displayStatus(application.application_status, application.ml_status)] || 'badge-yellow'}`}>
                    {displayStatus(application.application_status, application.ml_status) || 'Pending'}
                  </span>
                ) : (
                  <span className="status-badge-incomplete">Not Started</span>
                )}
              </div>

              {/* Step Indicator */}
              <div className="sd-steps">
                {['Personal Info', 'Documents', 'Review'].map((step, i) => (
                  <div key={i} className="sd-step-wrapper">
                    <div className={`sd-step-circle
                      ${i < stepsDone ? 'done' : i === stepsDone ? 'current' : ''}`}>
                      {i + 1}
                    </div>
                    <span className={`sd-step-label
                      ${i < stepsDone ? 'done' : i === stepsDone ? 'current' : ''}`}>
                      {step}
                    </span>
                    {i < 2 && (
                      <div className={`sd-step-line ${i < stepsDone - 1 ? 'done' : ''}`} />
                    )}
                  </div>
                ))}
              </div>

              {/* Status Message */}
              {application ? (
                <>
                  <p className="sd-progress-text">
                    {application.application_status === 'Approved' &&
                      'Congratulations. Your scholarship application has been approved.'}
                    {application.application_status === 'Rejected' && application.ml_status === 'Eligible' &&
                      'Your application met the eligibility criteria, but there were more qualified applicants than available slots. You have been waitlisted and may be promoted automatically if a slot opens up.'}
                    {application.application_status === 'Rejected' && application.ml_status !== 'Eligible' &&
                      'Unfortunately your application was not approved this time.'}
                    {application.application_status === 'Newly Submitted' &&
                      'Your application has been submitted and is waiting for review.'}
                    {application.application_status === 'Pending Verification' &&
                      'Your documents are being verified by our team.'}
                    {application.application_status === 'Not Yet Reviewed' &&
                      'Your application is in the queue and will be reviewed soon.'}
                    {application.application_status === 'Incomplete' &&
                      'Your application is incomplete. Please upload all required documents.'}
                  </p>

                  {application.application_status === 'Rejected' && application.ml_status !== 'Eligible' && application.rejection_reason && (
                    <p className="sd-rejection-reason">{application.rejection_reason}</p>
                  )}

                  {/* Progress Bar */}
                  <div className="sd-progress-track">
                    <div
                      className="sd-progress-fill"
                      style={{ width: `${completion}%` }}>
                      {completion}%
                    </div>
                  </div>

                  {/* Submitted Date */}
                  {application.submitted_at && (
                    <p className="sd-submitted-date">
                      Submitted: {new Date(application.submitted_at)
                        .toLocaleDateString('en-PH', {
                          month: 'long', day: 'numeric', year: 'numeric'
                        })}
                    </p>
                  )}
                </>
              ) : (
                <>
                  <p className="sd-progress-text">
                    You haven't submitted an application yet. Start your application now!
                  </p>
                  <div className="sd-progress-track">
                    <div className="sd-progress-fill" style={{ width: '0%' }}>0%</div>
                  </div>
                </>
              )}

              <button
                className="btn-continue"
                onClick={() => navigate(
                  application ? '/student/view-application' : '/student/application'
                )}>
                {application ? 'View My Application →' : 'Start Application →'}
              </button>
            </div>

            {/* Uploaded Documents */}
            <div className="sd-card sd-docs-card">
              <div className="sd-card-header">
                <h3>Uploaded Documents</h3>
              </div>
              <div className="sd-docs-header">
                <span>Document</span>
                <span>Status</span>
              </div>
              <div className="sd-docs-list">
                {documents.map((doc, i) => (
                  <div key={i} className="sd-doc-row">
                    <span className="sd-doc-name">
                      {doc.document_name || doc.label}
                    </span>
                    <span className={`sd-doc-badge ${
                      doc.status === 'Uploaded' ? 'badge-uploaded' :
                      doc.status === 'Not Required' ? 'badge-not-required' :
                      'badge-missing'
                    }`}>
                      {doc.status}
                    </span>
                  </div>
                ))}
              </div>
              <button
                className="btn-upload-missing"
                onClick={() => navigate('/student/documents')}>
                + Upload Missing Files
              </button>
            </div>

          </div>
        </>
      )}
    </div>
  )
}

export default StudentDashboard