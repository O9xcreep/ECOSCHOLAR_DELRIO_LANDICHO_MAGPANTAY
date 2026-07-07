import { useState, useEffect } from 'react'
import { apiFetch } from '../../api'
import './applicants.css'
import ApplicantModal from '../../components/ApplicantModal'

const STATUS_TABS = ['All', 'Approved', 'Rejected']

const statusClass = {
  'Approved': 'badge-green',
  'Rejected': 'badge-red',
  'Not Yet Reviewed': 'badge-yellow',
  'Newly Submitted': 'badge-blue',
  'Pending Verification': 'badge-yellow',
  'Incomplete': 'badge-red',
}

const avatarColors = [
  '#7c3aed', '#2563eb', '#059669', '#dc2626',
  '#d97706', '#7c3aed', '#0891b2', '#be185d',
  '#059669', '#dc2626'
]

function getInitials(name) {
  if (!name) return '?'
  return name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
}

function Applicants() {
  const [applicants, setApplicants] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('All')
  const [search, setSearch] = useState('')
  const [selectedApplicant, setSelectedApplicant] = useState(null)

  const fetchApplicants = async () => {
    try {
      const res = await apiFetch('/api/applicants')
      const data = await res.json()
      setApplicants(data.applicants || [])
    } catch (err) {
      console.error('Error:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchApplicants()
  }, [])

  const pageStatuses = ['Approved', 'Rejected']

  const filtered = applicants.filter(a => {
    const appStatus = a.application_status
    const isPageStatus = pageStatuses.includes(appStatus)
    const matchTab = activeTab === 'All' || appStatus === activeTab
    const matchSearch =
      a.full_name?.toLowerCase().includes(search.toLowerCase()) ||
      a.course?.toLowerCase().includes(search.toLowerCase())
    return isPageStatus && matchTab && matchSearch
  })

  const getTabCount = (tab) => {
    if (tab === 'All') {
      return applicants.filter(a => pageStatuses.includes(a.application_status)).length
    }
    return applicants.filter(a => a.application_status === tab).length
  }

  return (
    <div className="applicants-page">

      {/* Header */}
      <div className="page-header">
        <h2 className="page-title">Applicants</h2>
        <div className="header-right">
          <div className="search-box">
            <span className="search-icon"></span>
            <input
              type="text"
              placeholder="Search Applicant..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        {STATUS_TABS.map(tab => (
          <button
            key={tab}
            className={`tab-btn ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}>
            {tab}
            <span className="tab-count">{getTabCount(tab)}</span>
          </button>
        ))}
      </div>

      {/* Loading */}
      {loading ? (
        <div className="empty-state">
          <p>Loading applicants...</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          <p>No applicants found.</p>
        </div>
      ) : (
        <div className="cards-grid">
          {filtered.map((applicant, i) => (
            <div key={applicant.id} className="applicant-card">
              <div className="card-top">
                <div className="applicant-avatar"
                  style={{ background: avatarColors[i % avatarColors.length] }}>
                  {getInitials(applicant.full_name)}
                </div>
                <span className={`badge ${statusClass[applicant.application_status] || 'badge-yellow'}`}>
                  {applicant.application_status || 'Pending'}
                </span>
              </div>
              <div className="card-body">
                <h4 className="applicant-name">{applicant.full_name}</h4>
                <p className="applicant-course">{applicant.course}</p>
                <p className="applicant-gwa">GWA: <strong>{applicant.gpa}</strong></p>
                <p className="applicant-date">
                  {applicant.submitted_at
                    ? new Date(applicant.submitted_at).toLocaleDateString('en-PH', {
                        month: 'short', day: '2-digit', year: 'numeric'
                      })
                    : 'N/A'}
                </p>
              </div>
              <div className="card-footer">
                <button
                  className="btn-view"
                  onClick={() => setSelectedApplicant(applicant)}>
                  View Profile
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      <ApplicantModal
        applicant={selectedApplicant}
        onClose={() => setSelectedApplicant(null)}
        onStatusChange={fetchApplicants}
      />

    </div>
  )
}

export default Applicants