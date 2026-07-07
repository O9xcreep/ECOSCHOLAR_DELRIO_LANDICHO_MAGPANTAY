import { useState, useEffect } from 'react'
import { apiFetch } from '../../api'
import './Applications.css'
import ApplicantModal from '../../components/ApplicantModal'

const PAGE_STATUSES = [
  'Newly Submitted',
  'Pending Verification',
  'Not Yet Reviewed',
  'Incomplete'
]

const TABS = [
  { label: 'All', key: 'All' },
  { label: 'Newly Submitted', key: 'Newly Submitted' },
  { label: 'Pending Verification', key: 'Pending Verification' },
  { label: 'Not Yet Reviewed', key: 'Not Yet Reviewed' },
  { label: 'Incomplete', key: 'Incomplete' },
]

const statusClass = {
  'Newly Submitted': 'badge-blue',
  'Pending Verification': 'badge-yellow',
  'Not Yet Reviewed': 'badge-purple',
  'Incomplete': 'badge-red',
}

const avatarColors = [
  '#7c3aed','#2563eb','#059669','#dc2626',
  '#d97706','#0891b2','#be185d','#7c3aed',
  '#2563eb','#059669'
]

function getInitials(name) {
  if (!name) return '?'
  return name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
}

function Applications() {
  const [applications, setApplications] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('All')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState([])
  const [selectedApplicant, setSelectedApplicant] = useState(null)

  const fetchApplications = async () => {
    try {
      const res = await apiFetch('/api/applicants')
      const data = await res.json()
      setApplications(data.applicants || [])
    } catch (err) {
      console.error('Error:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchApplications()
  }, [])

  const pageApplications = applications.filter(a =>
    PAGE_STATUSES.includes(a.application_status)
  )

  const filtered = pageApplications.filter(a => {
    const matchTab = activeTab === 'All' || a.application_status === activeTab
    const matchSearch =
      a.full_name?.toLowerCase().includes(search.toLowerCase()) ||
      a.course?.toLowerCase().includes(search.toLowerCase())
    return matchTab && matchSearch
  })

  const toggleSelect = (id) => {
    setSelected(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    )
  }

  const toggleAll = () => {
    if (selected.length === filtered.length) setSelected([])
    else setSelected(filtered.map(a => a.id))
  }

  const getTabCount = (key) => {
    if (key === 'All') return pageApplications.length
    return pageApplications.filter(a => a.application_status === key).length
  }

  return (
    <div className="applications-page">

      {/* Stat Cards */}
      <div className="app-stats">
        {TABS.slice(1).map(tab => (
          <div key={tab.key}
            className={`app-stat-card stat-${tab.key.replace(/\s/g, '-').toLowerCase()}`}>
            <h3>{getTabCount(tab.key)}</h3>
            <p>{tab.label}</p>
          </div>
        ))}
      </div>

      {/* Header */}
      <div className="page-header">
        <div className="tabs">
          {TABS.map(tab => (
            <button
              key={tab.key}
              className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.key)}>
              {tab.label}
              <span className="tab-count">{getTabCount(tab.key)}</span>
            </button>
          ))}
        </div>
        <div className="header-actions">
          <div className="search-box">
            <span></span>
            <input
              type="text"
              placeholder="Search applicant..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <button className="btn-export">Export</button>
        </div>
      </div>

      {/* Table */}
      <div className="table-card">
        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>
            Loading applications...
          </div>
        ) : (
          <table className="app-table">
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    checked={selected.length === filtered.length && filtered.length > 0}
                    onChange={toggleAll}
                  />
                </th>
                <th>APPLICANT</th>
                <th>APPLICATION</th>
                <th>COURSE</th>
                <th>GWA</th>
                <th>SUBMITTED</th>
                <th>STATUS</th>
                <th>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan="8" className="empty-row">
                    No applications found.
                  </td>
                </tr>
              ) : (
                filtered.map((app, i) => (
                  <tr key={app.id}
                    className={selected.includes(app.id) ? 'selected-row' : ''}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.includes(app.id)}
                        onChange={() => toggleSelect(app.id)}
                      />
                    </td>
                    <td>
                      <div className="applicant-cell">
                        <div className="mini-avatar"
                          style={{ background: avatarColors[i % avatarColors.length] }}>
                          {getInitials(app.full_name)}
                        </div>
                        <div>
                          <p className="cell-name">
                            {app.full_name}
                            {app.has_other_scholarship === 1 && (
                              <span className="scholarship-flag" title={`Also receiving: ${app.other_scholarship_details}`}>
                                Other scholarship
                              </span>
                            )}
                          </p>
                          <p className="cell-email">{app.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="cell-app">
                      {app.application_type || 'General'}
                    </td>
                    <td className="cell-course">{app.course}</td>
                    <td className="cell-gwa">{app.gpa}</td>
                    <td className="cell-date">
                      {app.submitted_at
                        ? new Date(app.submitted_at).toLocaleDateString('en-PH', {
                            month: 'short', day: '2-digit', year: 'numeric'
                          })
                        : 'N/A'}
                    </td>
                    <td>
                      <span className={`badge ${statusClass[app.application_status] || 'badge-yellow'}`}>
                        {app.application_status || 'Pending'}
                      </span>
                    </td>
                    <td>
                      <div className="action-btns">
                        <button
                          className="action-btn view"
                          title="View"
                          onClick={() => setSelectedApplicant(app)}>
                          View
                        </button>
                        <button
                          className="action-btn approve"
                          title="Verify documents & let the model decide eligibility"
                          onClick={async () => {
                            if (!window.confirm(
                              `Confirm ${app.full_name}'s documents are correct and complete. ` +
                              `The eligibility model will then decide Approved/Rejected automatically.`
                            )) return
                            const res = await apiFetch(
                              `/api/applications/${app.id}/verify`,
                              { method: 'PUT' }
                            )
                            const data = await res.json()
                            if (!res.ok) alert(data.error || 'Could not decide eligibility for this applicant')
                            fetchApplications()
                          }}>
                          Verify
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}

        {/* Pagination */}
        <div className="pagination">
          <p className="pagination-info">
            Showing {filtered.length} of {pageApplications.length} applications
          </p>
          <div className="pagination-btns">
            <button className="page-btn active">1</button>
          </div>
        </div>
      </div>

      {/* Modal */}
      <ApplicantModal
        applicant={selectedApplicant}
        onClose={() => setSelectedApplicant(null)}
        onStatusChange={fetchApplications}
      />

    </div>
  )
}

export default Applications