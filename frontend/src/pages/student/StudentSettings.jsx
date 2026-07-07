import { useState } from 'react'
import './StudentSettings.css'

const TABS = ['Profile', 'Security', 'Notifications']

// ── PROF tab ──
function ProfileTab() {
  const [editing, setEditing] = useState(null)
  const [formData, setFormData] = useState({
    fullName: 'Juan Dela Cruz',
    email: 'juan.dc@gmail.com',
    contactNumber: '09123456789',
    address: 'Block 5 Lot 12, Brgy. San Jose, Tanza, Cavite',
  })

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  return (
    <div className="tab-content">

      {/* Account Info */}
      <div className="settings-card">
        <h4 className="card-label">Account Information</h4>
        <div className="profile-top">
          <div className="profile-avatar">JD</div>
          <div className="profile-info">
            <h3 className="profile-name">{formData.fullName}</h3>
            <p className="profile-role">Applicant</p>
            <p className="profile-id">Application ID: <span>#SP-2026-0042</span></p>
          </div>
          <button className="btn-change-photo">Change Photo</button>
        </div>

        <div className="info-grid">
          {[
            { key: 'fullName', label: 'Full Name', type: 'text' },
            { key: 'email', label: 'Email Address', type: 'email' },
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
                  <button className="btn-save"
                    onClick={() => setEditing(null)}>
                    Save
                  </button>
                  <button className="btn-cancel-edit"
                    onClick={() => setEditing(null)}>
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="field-row">
                  <p className="field-value">{formData[field.key]}</p>
                  <button className="btn-edit"
                    onClick={() => setEditing(field.key)}>
                    Edit
                  </button>
                </div>
              )}
            </div>
          ))}
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
            <span className="badge badge-yellow">Incomplete</span>
          </div>
          <div className="status-item">
            <span className="status-label">Member Since</span>
            <span className="status-value">May 1, 2026</span>
          </div>
          <div className="status-item">
            <span className="status-label">Last Updated</span>
            <span className="status-value">May 16, 2026</span>
          </div>
        </div>
      </div>

    </div>
  )
}

// ── SECURITY TAB ──
function SecurityTab() {
  const [showCurrent, setShowCurrent] = useState(false)
  const [showNew, setShowNew] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [passwords, setPasswords] = useState({
    current: '', newPass: '', confirm: ''
  })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  const handleChange = (field, value) => {
    setPasswords(prev => ({ ...prev, [field]: value }))
    setError('')
    setSuccess(false)
  }

  const handleSubmit = () => {
    if (!passwords.current) { setError('Current password is required'); return }
    if (!passwords.newPass) { setError('New password is required'); return }
    if (passwords.newPass.length < 8) { setError('Password must be at least 8 characters'); return }
    if (passwords.newPass !== passwords.confirm) { setError('Passwords do not match'); return }
    setSuccess(true)
    setPasswords({ current: '', newPass: '', confirm: '' })
  }

  return (
    <div className="tab-content">
      <div className="settings-card">
        <h4 className="card-label">Change Password</h4>

        {error && <div className="security-error">{error}</div>}
        {success && <div className="security-success">Password changed successfully.</div>}

        <div className="password-fields">
          {[
            { key: 'current', label: 'Current Password', show: showCurrent, toggle: () => setShowCurrent(!showCurrent) },
            { key: 'newPass', label: 'New Password', show: showNew, toggle: () => setShowNew(!showNew) },
            { key: 'confirm', label: 'Confirm New Password', show: showConfirm, toggle: () => setShowConfirm(!showConfirm) },
          ].map(field => (
            <div key={field.key} className="password-field">
              <label>{field.label}</label>
              <div className="password-wrapper">
                <input
                  type={field.show ? 'text' : 'password'}
                  placeholder="••••••••"
                  value={passwords[field.key]}
                  onChange={e => handleChange(field.key, e.target.value)}
                />
                <button className="toggle-pw" onClick={field.toggle}>
                  {field.show ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="password-requirements">
          <p className="req-title">Password requirements:</p>
          <ul>
            <li className={passwords.newPass.length >= 8 ? 'met' : ''}>At least 8 characters</li>
            <li className={/[A-Z]/.test(passwords.newPass) ? 'met' : ''}>One uppercase letter</li>
            <li className={/[0-9]/.test(passwords.newPass) ? 'met' : ''}>One number</li>
          </ul>
        </div>

        <button className="btn-primary" onClick={handleSubmit}>
          Update Password
        </button>
      </div>

      <div className="settings-card">
        <h4 className="card-label">Login History</h4>
        <div className="login-list">
          {[
            { device: 'Chrome - Windows', location: 'Tanza, Cavite, PH', date: 'May 16, 2026, 7:00 PM', current: true },
            { device: 'Chrome - Mobile', location: 'Tanza, Cavite, PH', date: 'May 15, 2026, 10:30 AM', current: false },
            { device: 'Firefox - Windows', location: 'Tanza, Cavite, PH', date: 'May 13, 2026, 3:00 PM', current: false },
          ].map((log, i) => (
            <div key={i} className="login-row">
              <div>
                <p className="login-device">{log.device}</p>
                <p className="login-detail">{log.location} — {log.date}</p>
              </div>
              <span className={`badge ${log.current ? 'badge-green' : 'badge-gray'}`}>
                {log.current ? 'Current' : 'Past'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── NOTIFICATIONS TAB ──
function NotificationsTab() {
  const [toggles, setToggles] = useState({
    statusUpdate: true,
    deadlineReminder: true,
    documentAlert: true,
    emailNotif: true,
    smsNotif: false,
  })

  const toggle = (key) => {
    setToggles(prev => ({ ...prev, [key]: !prev[key] }))
  }

  const notifications = [
    { key: 'statusUpdate', label: 'Application status updates', sub: 'Get notified when your application status changes' },
    { key: 'deadlineReminder', label: 'Deadline reminders', sub: '3 days before the application deadline' },
    { key: 'documentAlert', label: 'Missing document alerts', sub: 'Reminders to upload required documents' },
    { key: 'emailNotif', label: 'Email notifications', sub: 'Receive notifications via email' },
    { key: 'smsNotif', label: 'SMS notifications', sub: 'Receive notifications via text message' },
  ]

  return (
    <div className="tab-content">
      <div className="settings-card">
        <h4 className="card-label">Notification Preferences</h4>
        <div className="notif-list">
          {notifications.map(item => (
            <div key={item.key} className="notif-item">
              <div className="notif-info">
                <p className="notif-label">{item.label}</p>
                <p className="notif-sub">{item.sub}</p>
              </div>
              <div className="notif-toggle-row">
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={toggles[item.key]}
                    onChange={() => toggle(item.key)}
                  />
                  <span className="slider" />
                </label>
                <span className="toggle-text">
                  {toggles[item.key] ? 'On' : 'Off'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── MAIN ──
function StudentSettings() {
  const [activeTab, setActiveTab] = useState('Profile')

  return (
    <div className="student-settings-page">
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

      {activeTab === 'Profile' && <ProfileTab />}
      {activeTab === 'Security' && <SecurityTab />}
      {activeTab === 'Notifications' && <NotificationsTab />}
    </div>
  )
}

export default StudentSettings