import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, getUser } from '../../api'
import './ApplicationView.css'

const STATUS_COLORS = {
  'Approved': 'badge-green',
  'Rejected': 'badge-red',
  'Newly Submitted': 'badge-blue',
  'Pending Verification': 'badge-yellow',
  'Not Yet Reviewed': 'badge-purple',
  'Incomplete': 'badge-red',
}

const STATUS_MESSAGES = {
  'Approved': 'Congratulations. Your scholarship application has been approved.',
  'Rejected': 'Unfortunately your application was not approved this time.',
  'Newly Submitted': 'Your application has been submitted and is waiting for review.',
  'Pending Verification': 'Your documents are being verified by our team.',
  'Not Yet Reviewed': 'Your application is in the queue and will be reviewed soon.',
  'Incomplete': 'Your application is incomplete. Please upload all required documents.',
}

function ApplicationView() {
  const navigate = useNavigate()
  const [application, setApplication] = useState(null)
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)

  const user = getUser() || {}

  useEffect(() => {
    if (!user.email) { setLoading(false); return }

    apiFetch(`/api/student/application?email=${encodeURIComponent(user.email)}`)
      .then(res => res.json())
      .then(data => {
        if (data.application) {
          setApplication(data.application)
          setDocuments(data.documents || [])
        }
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="av-container">
        <div className="av-loading">Loading your application...</div>
      </div>
    )
  }

  if (!application) {
    return (
      <div className="av-container">
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

  return (
    <div className="av-container">

      {/* Header */}
      <div className="av-header">
        <div>
          <h2 className="av-title">My Application</h2>
          <p className="av-sub">
            Application ID: <span className="av-id">
              #SP-{String(application.id).padStart(4, '0')}
            </span>
          </p>
        </div>
        <span className={`badge ${STATUS_COLORS[status] || 'badge-yellow'}`}>
          {status}
        </span>
      </div>

      {/* Status Banner */}
      <div className={`av-status-banner ${
        status === 'Approved' ? 'banner-green' :
        status === 'Rejected' ? 'banner-red' : 'banner-blue'
      }`}>
        <p>{STATUS_MESSAGES[status] || 'Your application is being processed.'}</p>

        {status === 'Rejected' && application.rejection_reason && (
          <p className="av-rejection-reason">{application.rejection_reason}</p>
        )}

        {application.submitted_at && (
          <p className="av-submitted">
            Submitted: {new Date(application.submitted_at).toLocaleDateString('en-PH', {
              month: 'long',
              day: 'numeric',
              year: 'numeric'
            })}
          </p>
        )}

        {application.reviewed_at && (
          <p className="av-reviewed">
            Reviewed on: {new Date(application.reviewed_at)
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
            <p>{application.religion}</p>
          </div>
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
            <p>{application.father_occupation}</p>
          </div>
          <div className="av-field">
            <label>Mother's Name</label>
            <p>{application.mother_name}</p>
          </div>
          <div className="av-field">
            <label>Mother's Occupation</label>
            <p>{application.mother_occupation}</p>
          </div>
          <div className="av-field">
            <label>Household Income</label>
            <p>{application.household_income}</p>
          </div>
          <div className="av-field">
            <label>Family Size</label>
            <p>{application.family_size} members</p>
          </div>
        </div>
      </div>

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
      <div className="av-card">
        <h3 className="av-card-title">Submitted Documents</h3>
        {documents.length === 0 ? (
          <p style={{ color: '#888', fontSize: '14px' }}>No documents uploaded yet.</p>
        ) : (
          <div className="av-docs">
            {documents.map((doc, i) => (
              <div key={i} className="av-doc-row">
                <span className="av-doc-name">{doc.document_name}</span>
                <span className={`badge ${
                  doc.status === 'Uploaded' ? 'badge-green' :
                  doc.status === 'Not Required' ? 'badge-gray' : 'badge-red'
                }`}>
                  {doc.status === 'Uploaded' ? 'Uploaded' :
                   doc.status === 'Not Required' ? '— Not Required' : 'Missing'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="av-footer">
        <button className="av-btn-secondary"
          onClick={() => navigate('/student/dashboard')}>
          ← Back to Dashboard
        </button>
        {status === 'Incomplete' && (
          <button className="av-btn-primary"
            onClick={() => navigate('/student/documents')}>
            Upload Missing Documents
          </button>
        )}
      </div>

    </div>
  )
}

export default ApplicationView