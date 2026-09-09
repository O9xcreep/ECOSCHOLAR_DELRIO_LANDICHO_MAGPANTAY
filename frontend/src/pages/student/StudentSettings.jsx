import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, getUser, setSession, logout } from '../../api'
import Reveal from '../../components/Reveal'
import pageBg from '../../assets/bg4.jpg'
import './StudentSettings.css'

const TABS = ['Profile', 'Security']

// ── PROFILE TAB ──
function ProfileTab() {
  const navigate = useNavigate()
  const user = getUser() || {}
  const [editing, setEditing] = useState(null)
  const [formData, setFormData] = useState({
    fullName: user.full_name || '', email: user.email || '',
    contactNumber: '', address: '',
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [applicationStatus, setApplicationStatus] = useState(null)
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)

  useEffect(() => {
    apiFetch('/api/profile')
      .then(res => res.json())
      .then(data => {
        const p = data.profile || {}
        setFormData(prev => ({
          ...prev,
          fullName: p.fullName || prev.fullName,
          contactNumber: p.contactNumber || '',
          address: p.address || '',
        }))
        setLoading(false)
      })
      .catch(() => setLoading(false))

    if (user.email) {
      apiFetch(`/api/student/application?email=${encodeURIComponent(user.email)}`)
        .then(res => res.json())
        .then(data => setApplicationStatus(data.application ? data.application.application_status : 'Not Started'))
        .catch(() => {})
    }
  }, [])

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const fieldToApiKey = { fullName: 'full_name', contactNumber: 'contactNumber', address: 'address' }

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const handleSave = async (key) => {
    setError('')
    const value = formData[key].trim()
    if (!value) { setError('This field cannot be empty'); return }
    setSaving(true)
    try {
      const res = await apiFetch('/api/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [fieldToApiKey[key]]: value })
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Failed to save'); return }
      if (key === 'fullName') setSession({ ...user, full_name: data.fullName }, localStorage.getItem('token'))
      setEditing(null)
    } catch {
      setError('Cannot connect to server. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="tab-content">

      {/* Account Info */}
      <div className="settings-card">
        <h4 className="card-label">Account Information</h4>
        <div className="profile-top">
          <div className="profile-avatar">
            {formData.fullName ? formData.fullName.charAt(0).toUpperCase() : 'S'}
          </div>
          <div className="profile-info">
            <h3 className="profile-name">{formData.fullName || 'Student'}</h3>
            <p className="profile-role">Applicant</p>
          </div>
        </div>

        {error && <div className="security-error">{error}</div>}

        <div className="info-grid">
          {[
            { key: 'fullName', label: 'Full Name', type: 'text' },
            { key: 'contactNumber', label: 'Contact Number', type: 'text' },
            { key: 'address', label: 'Address', type: 'text', full: true },
          ].map(field => (
            <div key={field.key} className={`info-field ${field.full ? 'full' : ''}`}>
              <label>{field.label}</label>
              {editing === field.key ? (
                <div className="edit-row">
                  <input
                    type={field.type}
                    value={formData[field.key]}
                    onChange={e => handleChange(field.key, e.target.value)}
                    className="edit-input"
                    autoFocus
                  />
                  <button className="btn-save" onClick={() => handleSave(field.key)} disabled={saving}>
                    {saving ? 'Saving...' : 'Save'}
                  </button>
                  <button className="btn-cancel-edit" onClick={() => { setEditing(null); setError('') }}>
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="field-row">
                  <p className="field-value">{loading ? '...' : (formData[field.key] || '—')}</p>
                  <button className="btn-edit" onClick={() => setEditing(field.key)}>Edit</button>
                </div>
              )}
            </div>
          ))}

          <div className="info-field">
            <label>Email Address</label>
            <div className="field-row">
              <p className="field-value">{formData.email}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Account Status */}
      <div className="settings-card">
        <h4 className="card-label">Account Status</h4>
        <div className="status-grid">
          <div className="status-item">
            <span className="status-label">Account Status</span>
            <span className="badge badge-green">Active</span>
          </div>
          <div className="status-item">
            <span className="status-label">Application Status</span>
            <span className="badge badge-yellow">{applicationStatus || 'Loading...'}</span>
          </div>
        </div>
      </div>

      {/* Session */}
      <div className="settings-card">
        <h4 className="card-label">Session</h4>
        <div className="info-field full">
          <label>Sign out</label>
          <p className="field-value" style={{ fontWeight: 400, marginBottom: '10px' }}>
            You are logged in as <strong>{user.email || 'unknown'}</strong>.
            Logging out will end this session everywhere it's used.
          </p>
          {!showLogoutConfirm ? (
            <button className="btn-danger-outline" onClick={() => setShowLogoutConfirm(true)}>
              Logout
            </button>
          ) : (
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <span style={{ fontSize: '13px', color: '#6B7280' }}>Are you sure?</span>
              <button className="btn-danger" onClick={handleLogout}>Yes, Logout</button>
              <button className="btn-cancel-edit" onClick={() => setShowLogoutConfirm(false)}>Cancel</button>
            </div>
          )}
        </div>
      </div>

    </div>
  )
}

// ── SECURITY TAB ──
function SecurityTab() {
  const [passwords, setPasswords] = useState({ current: '', newPass: '', confirm: '' })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [saving, setSaving] = useState(false)

  const handleChange = (field, value) => {
    setPasswords(prev => ({ ...prev, [field]: value }))
    setError('')
    setSuccess(false)
  }

  const handleSubmit = async () => {
    setError('')
    setSuccess(false)
    if (!passwords.current) { setError('Current password is required'); return }
    if (!passwords.newPass) { setError('New password is required'); return }
    if (passwords.newPass.length < 8) { setError('Password must be at least 8 characters'); return }
    if (passwords.newPass !== passwords.confirm) { setError('Passwords do not match'); return }

    setSaving(true)
    try {
      const res = await apiFetch('/api/change-password', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: passwords.current, new_password: passwords.newPass })
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Failed to change password'); return }
      setSuccess(true)
      setPasswords({ current: '', newPass: '', confirm: '' })
    } catch {
      setError('Cannot connect to server. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="tab-content">
      <div className="settings-card">
        <h4 className="card-label">Change Password</h4>

        {error && <div className="security-error">{error}</div>}
        {success && <div className="security-success">Password changed successfully.</div>}

        <div className="password-fields">
          {[
            { key: 'current', label: 'Current Password' },
            { key: 'newPass', label: 'New Password' },
            { key: 'confirm', label: 'Confirm New Password' },
          ].map(field => (
            <div key={field.key} className="password-field">
              <label>{field.label}</label>
              <div className="password-wrapper">
                <input
                  type="password"
                  placeholder="••••••••"
                  value={passwords[field.key]}
                  onChange={e => handleChange(field.key, e.target.value)}
                />
              </div>
            </div>
          ))}
        </div>

        <div className="password-requirements">
          <p className="req-title">Password requirements:</p>
          <ul>
            <li className={passwords.newPass.length >= 8 ? 'met' : ''}>At least 8 characters</li>
          </ul>
        </div>

        <button className="btn-primary" onClick={handleSubmit} disabled={saving}>
          {saving ? 'Updating...' : 'Update Password'}
        </button>
      </div>
    </div>
  )
}

// ── MAIN ──
function StudentSettings() {
  const [activeTab, setActiveTab] = useState('Profile')

  return (
    <div className="student-settings-page page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>
      <div className="settings-header">
        <h2 className="page-title">Settings</h2>
        <p className="page-sub">Manage your account and preferences</p>
      </div>

      <div className="settings-tabs">
        {TABS.map(tab => (
          <button
            key={tab}
            className={`settings-tab ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}>
            {tab}
          </button>
        ))}
      </div>

      <Reveal key={activeTab}>
        {activeTab === 'Profile' && <ProfileTab />}
        {activeTab === 'Security' && <SecurityTab />}
      </Reveal>
    </div>
  )
}

export default StudentSettings
