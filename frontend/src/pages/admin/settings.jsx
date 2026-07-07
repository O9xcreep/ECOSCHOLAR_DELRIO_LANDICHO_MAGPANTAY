import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './settings.css'

const TABS = ['Profile', 'Security', 'Notifications', 'System', 'Roles & Access']

// ── PROFILE TAB ──
function ProfileTab() {
  const navigate = useNavigate()
  const user = JSON.parse(localStorage.getItem('user') || '{}')
  const [showConfirm, setShowConfirm] = useState(false)

  const handleLogout = () => {
    localStorage.removeItem('user')   
    navigate('/login')                
  }

  return (
    <div className="tab-content">
      <div className="settings-card">
        <h4 className="card-label">Account information</h4>
        <div className="settings-row">
          <div className="admin-avatar-lg">
            {user.full_name ? user.full_name.charAt(0).toUpperCase() : 'S'}
          </div>
          <button className="btn-change">Change photo</button>
          <div className="info-item">
            <span className="info-label">Full name</span>
            {/* Real name from localStorage */}
            <span className="info-value">{user.full_name || 'Student'}</span>
            <button className="btn-edit">Edit</button>
          </div>
          <div className="info-item">
            <span className="info-label">Email address</span>
            {/*  Real email from localStorage */}
            <span className="info-value">{user.email || '—'}</span>
            <button className="btn-edit">Edit</button>
          </div>
          <div className="info-item">
            <span className="info-label">Role</span>
            <span className="badge badge-purple">
              {user.role === 'admin' ? 'Administrator' : 'Student'}
            </span>
          </div>
          <div className="info-item">
            <span className="info-label">Account status</span>
            <span className="badge badge-green">Active</span>
          </div>
        </div>
      </div>

      <div className="settings-card">
        <h4 className="card-label">Preferences</h4>
        <div className="settings-row">
          <div className="info-item">
            <span className="info-label">Language</span>
            <select className="settings-select">
              <option>English (PH)</option>
              <option>Filipino</option>
            </select>
          </div>
          <div className="info-item">
            <span className="info-label">Date format</span>
            <select className="settings-select">
              <option>MM/DD/YYYY</option>
              <option>DD/MM/YYYY</option>
              <option>YYYY-MM-DD</option>
            </select>
          </div>
          <div className="info-item">
            <span className="info-label">Academic year</span>
            <span className="badge badge-yellow">2025-2026</span>
          </div>
        </div>
      </div>

      {/* Logout Section */}
      <div className="settings-card">
        <h4 className="card-label">Session</h4>
        <div className="settings-row">
          <div className="info-item">
            <span className="info-label">Sign out</span>
            <span className="info-sub">
              You are logged in as <strong>{user.email || 'unknown'}</strong>.
              Logging out will clear your session.
            </span>
            {!showConfirm ? (
              <button
                className="btn-danger-outline"
                onClick={() => setShowConfirm(true)}>
                Logout
              </button>
            ) : (
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginTop: '8px' }}>
                <span style={{ fontSize: '13px', color: '#6B7280' }}>Are you sure?</span>
                <button className="btn-danger" onClick={handleLogout}>Yes, Logout</button>
                <button className="btn-change" onClick={() => setShowConfirm(false)}>Cancel</button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="settings-card danger-card">
        <h4 className="card-label danger-label">Danger zone</h4>
        <div className="settings-row">
          <div className="info-item">
            <span className="info-label">Deactivate account</span>
            <span className="info-sub">Temporarily disable this account</span>
            <button className="btn-danger-outline">Deactivate</button>
          </div>
          <div className="info-item">
            <span className="info-label">Delete account</span>
            <span className="info-sub">Permanently remove all data</span>
            <button className="btn-danger">Delete</button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── SECURITY TAB ──
function SecurityTab() {
  return (
    <div className="tab-content">
      <div className="settings-card">
        <h4 className="card-label">Password</h4>
        <div className="settings-row">
          <div className="info-item">
            <span className="info-label">Current password</span>
            <span className="info-sub">Last changed 3 months ago</span>
          </div>
          <button className="btn-primary">Change password</button>
          <div className="info-item">
            <span className="info-label">Two-factor authentication</span>
            <span className="info-sub">Add an extra layer of security</span>
          </div>
          <div className="toggle-row">
            <span>Off</span>
            <label className="toggle">
              <input type="checkbox" />
              <span className="slider" />
            </label>
          </div>
        </div>
      </div>

      <div className="settings-card">
        <h4 className="card-label">Login history</h4>
        <div className="login-list">
          {[
            { device: 'Chrome - Windows', location: 'Quezon City, PH', date: 'May 16, 2026, 9:04 AM', current: true },
            { device: 'Chrome - Windows', location: 'Quezon City, PH', date: 'May 15, 2026, 3:22 PM', current: false },
            { device: 'Mobile - Android', location: 'Quezon City, PH', date: 'May 13, 2026, 11:00 AM', current: false },
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
  const [emailToggles, setEmailToggles] = useState({
    newApplicant: true,
    statusChanged: true,
    deadlineReminder: true,
    slotFilled: false,
  })

  const [appToggles, setAppToggles] = useState({
    notifBadge: true,
    reportsReady: false,
  })

  const toggle = (setter, key) => {
    setter(prev => ({ ...prev, [key]: !prev[key] }))
  }

  return (
    <div className="tab-content">
      <div className="settings-card">
        <h4 className="card-label">Email notifications</h4>
        <div className="notif-grid">
          {[
            { key: 'newApplicant', label: 'New applicant submitted', sub: 'Get notified when someone applies' },
            { key: 'statusChanged', label: 'Application status changed', sub: 'Approved, rejected, or under review' },
            { key: 'deadlineReminder', label: 'Scholarship deadline reminder', sub: '3 days before closing date' },
            { key: 'slotFilled', label: 'Slot filled alert', sub: 'When a scholarship reaches full capacity' },
          ].map(item => (
            <div key={item.key} className="notif-item">
              <div>
                <p className="notif-label">{item.label}</p>
                <p className="notif-sub">{item.sub}</p>
              </div>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={emailToggles[item.key]}
                  onChange={() => toggle(setEmailToggles, item.key)}
                />
                <span className="slider" />
              </label>
              <span className="toggle-text">
                {emailToggles[item.key] ? 'On' : 'Off'}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="settings-card">
        <h4 className="card-label">In-app notifications</h4>
        <div className="notif-grid">
          {[
            { key: 'notifBadge', label: 'Show notification badge', sub: 'Bell icon counter on the top bar' },
            { key: 'reportsReady', label: 'Reports ready alert', sub: 'When a new report is generated' },
          ].map(item => (
            <div key={item.key} className="notif-item">
              <div>
                <p className="notif-label">{item.label}</p>
                <p className="notif-sub">{item.sub}</p>
              </div>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={appToggles[item.key]}
                  onChange={() => toggle(setAppToggles, item.key)}
                />
                <span className="slider" />
              </label>
              <span className="toggle-text">
                {appToggles[item.key] ? 'On' : 'Off'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── SYSTEM TAB ──
function SystemTab() {
  return (
    <div className="tab-content">
      <div className="settings-card">
        <h4 className="card-label">Scholarship settings</h4>
        <div className="settings-row">
          <div className="info-item">
            <span className="info-label">Default minimum GWA</span>
            <span className="info-sub">Applicants below this are auto-flagged</span>
            <select className="settings-select">
              <option>1.75</option>
              <option>2.00</option>
              <option>2.25</option>
              <option>2.50</option>
            </select>
          </div>
          <div className="info-item">
            <span className="info-label">Active academic year</span>
            <select className="settings-select">
              <option>2025-2026</option>
              <option>2026-2027</option>
            </select>
          </div>
          <div className="info-item">
            <span className="info-label">Allow late applications</span>
            <span className="info-sub">Accept submissions past the deadline</span>
            <label className="toggle">
              <input type="checkbox" />
              <span className="slider" />
            </label>
          </div>
        </div>
      </div>

      <div className="settings-card">
        <h4 className="card-label">Data & export</h4>
        <div className="settings-row">
          <div className="info-item">
            <span className="info-label">Export all applicants</span>
            <span className="info-sub">Download complete applicant list as CSV</span>
            <button className="btn-primary">Export CSV</button>
          </div>
          <div className="info-item">
            <span className="info-label">Export reports</span>
            <span className="info-sub">Download analytics summary as PDF</span>
            <button className="btn-primary">Export PDF</button>
          </div>
          <div className="info-item">
            <span className="info-label">Backup data</span>
            <span className="info-sub">Last backup: May 10, 2026</span>
            <button className="btn-primary">Backup now</button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── ROLES TAB ──
function RolesTab() {
  return (
    <div className="tab-content">
      <div className="settings-card">
        <h4 className="card-label">User roles</h4>
        <div className="roles-grid">
          <div className="role-item">
            <p className="role-name">Administrator</p>
            <p className="role-desc">Full access — manage all data, settings, and users</p>
            <span className="badge badge-green">You</span>
          </div>
          <div className="role-item">
            <p className="role-name">Reviewer</p>
            <p className="role-desc">Can view and update applicant status only</p>
            <button className="btn-primary">Manage</button>
          </div>
          <div className="role-item">
            <p className="role-name">Viewer</p>
            <p className="role-desc">Read-only access to applicants and reports</p>
            <button className="btn-primary">Manage</button>
          </div>
        </div>
      </div>

      <div className="settings-card">
        <h4 className="card-label">Staff accounts</h4>
        <div className="staff-list">
          {[
            { name: 'Maria Santos', email: 'maria@ecoscolar.edu.ph', role: 'Reviewer', roleClass: 'badge-yellow' },
            { name: 'Carlo Reyes', email: 'carlo@ecoscolar.edu.ph', role: 'Viewer', roleClass: 'badge-blue' },
          ].map((staff, i) => (
            <div key={i} className="staff-row">
              <div className="staff-avatar">
                {staff.name.split(' ').map(n => n[0]).join('')}
              </div>
              <div>
                <p className="staff-name">{staff.name}</p>
                <p className="staff-email">{staff.email}</p>
              </div>
              <span className={`badge ${staff.roleClass}`}>{staff.role}</span>
              <button className="btn-edit">Edit</button>
            </div>
          ))}
        </div>
        <button className="btn-invite">Invite staff</button>
      </div>
    </div>
  )
}

// ── MAIN SETTINGS ──
function Settings() {
  const [activeTab, setActiveTab] = useState('Profile')

  return (
    <div className="settings-page">
      <div className="settings-header">
        <div>
          <h2 className="page-title">Settings</h2>
          <p className="page-sub">Manage your account, system preferences, and access controls.</p>
        </div>
      </div>

      {/* Tabs */}
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

      {/* Tab Content */}
      {activeTab === 'Profile' && <ProfileTab />}
      {activeTab === 'Security' && <SecurityTab />}
      {activeTab === 'Notifications' && <NotificationsTab />}
      {activeTab === 'System' && <SystemTab />}
      {activeTab === 'Roles & Access' && <RolesTab />}
    </div>
  )
}

export default Settings