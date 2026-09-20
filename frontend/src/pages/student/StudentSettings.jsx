import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, getUser, setSession, clearSession, logout, connectionErrorMessage } from '../../api'
import Reveal from '../../components/Reveal'
import Credits from '../../components/Credits'
import pageBg from '../../assets/bg4.jpg'
import './StudentSettings.css'

const TABS = ['Profile', 'Security', 'Credits']

// ── YOUR ORGANIZATIONS ──
// A student's own membership list is self-service (no privilege risk, role
// is always 'student') - unlike the admin-side equivalent, joining here
// happens instantly, the same way registration already works with a join
// code, no approval needed.
function YourOrganizationsCard() {
  const [memberships, setMemberships] = useState([])
  const [loading, setLoading] = useState(true)
  const [switchingId, setSwitchingId] = useState('')
  const [switchError, setSwitchError] = useState('')

  const [joinCode, setJoinCode] = useState('')
  const [joinCodeOrgName, setJoinCodeOrgName] = useState('')
  const [joinCodeError, setJoinCodeError] = useState('')
  const [joinCodeChecking, setJoinCodeChecking] = useState(false)
  const [joining, setJoining] = useState(false)
  const [joinError, setJoinError] = useState('')

  useEffect(() => {
    apiFetch('/api/memberships')
      .then(res => res.json())
      .then(data => setMemberships(data.memberships || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSwitch = async (organizationId) => {
    setSwitchError('')
    setSwitchingId(organizationId)
    try {
      const res = await apiFetch('/api/organizations/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ organization_id: organizationId })
      })
      const data = await res.json()
      if (!res.ok) { setSwitchError(data.error || 'Failed to switch organization'); return }
      setSession(data.user, data.token)
      // Full reload - nothing on this page (or any other) re-reads "current
      // org" reactively after mount, so an in-place update would leave every
      // list/dashboard showing stale data from the previous org.
      window.location.href = '/student/dashboard'
    } catch {
      setSwitchError(connectionErrorMessage())
    } finally {
      setSwitchingId('')
    }
  }

  const handleJoinCodeBlur = async () => {
    const code = joinCode.trim().toUpperCase()
    setJoinCodeOrgName('')
    setJoinCodeError('')
    if (!code) return
    setJoinCodeChecking(true)
    try {
      const res = await apiFetch(`/api/organizations/lookup?code=${encodeURIComponent(code)}`)
      const data = await res.json()
      if (!res.ok) { setJoinCodeError(data.error || "That join code isn't valid. Check it with your LGU and try again."); return }
      setJoinCodeOrgName(data.organization.name)
    } catch {
      setJoinCodeError(connectionErrorMessage())
    } finally {
      setJoinCodeChecking(false)
    }
  }

  const handleJoin = async () => {
    setJoinError('')
    if (!joinCode.trim()) { setJoinError('Enter a join code'); return }
    setJoining(true)
    try {
      const res = await apiFetch('/api/organizations/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ join_code: joinCode.trim().toUpperCase() })
      })
      const data = await res.json()
      if (!res.ok) { setJoinError(data.error || 'Failed to join organization'); return }
      setSession(data.user, data.token)
      window.location.href = '/student/dashboard'
    } catch {
      setJoinError(connectionErrorMessage())
    } finally {
      setJoining(false)
    }
  }

  return (
    <div className="settings-card">
      <h4 className="card-label">Your Organizations</h4>
      {loading ? (
        <p className="field-value" style={{ fontWeight: 400 }}>Loading...</p>
      ) : (
        memberships.map(m => (
          <div key={m.organization_id} className="info-field full">
            <div className="field-row">
              <p className="field-value">
                {m.organization_name || 'Unknown organization'}
                {m.is_active && <span className="badge badge-green" style={{ marginLeft: '8px' }}>Active</span>}
              </p>
              {!m.is_active && (
                <button className="btn-edit" onClick={() => handleSwitch(m.organization_id)} disabled={switchingId === m.organization_id}>
                  {switchingId === m.organization_id ? 'Switching...' : 'Switch'}
                </button>
              )}
            </div>
          </div>
        ))
      )}
      {switchError && <div className="security-error">{switchError}</div>}

      <div className="info-field full" style={{ marginTop: '10px' }}>
        <label>Join another LGU</label>
        {joinError && <div className="security-error">{joinError}</div>}
        <div className="edit-row">
          <input
            className="edit-input"
            placeholder="LGU Join Code"
            value={joinCode}
            onChange={e => { setJoinCode(e.target.value); setJoinCodeOrgName(''); setJoinCodeError('') }}
            onBlur={handleJoinCodeBlur}
          />
          <button className="btn-save" onClick={handleJoin} disabled={joining}>
            {joining ? 'Joining...' : 'Join'}
          </button>
        </div>
        {joinCodeChecking && <p className="field-value" style={{ fontWeight: 400 }}>Checking...</p>}
        {joinCodeOrgName && <p className="field-value" style={{ fontWeight: 400, color: '#059669' }}>Joining {joinCodeOrgName}</p>}
        {joinCodeError && <p className="field-value" style={{ fontWeight: 400, color: '#ef4444' }}>{joinCodeError}</p>}
      </div>
    </div>
  )
}

// ── DANGER ZONE (DELETE ACCOUNT) ──
function DangerZoneCard() {
  const navigate = useNavigate()
  const [showConfirm, setShowConfirm] = useState(false)
  const [password, setPassword] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  const handleDelete = async () => {
    setError('')
    setDeleting(true)
    try {
      const res = await apiFetch('/api/account', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Failed to delete account'); return }
      clearSession()
      navigate('/login')
    } catch {
      setError(connectionErrorMessage())
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="settings-card">
      <h4 className="card-label">Danger Zone</h4>
      <div className="info-field full">
        <label>Delete account</label>
        <p className="field-value" style={{ fontWeight: 400, marginBottom: '10px' }}>
          Permanently deletes your login. Your past application stays visible to admins, exactly as it
          does today - only your ability to sign in is gone.
        </p>
        {!showConfirm ? (
          <button className="btn-danger-outline" onClick={() => setShowConfirm(true)}>Delete Account</button>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'flex-start' }}>
            <input
              type="password"
              className="edit-input"
              placeholder="Enter your password to confirm"
              value={password}
              onChange={e => setPassword(e.target.value)}
            />
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <button className="btn-danger" onClick={handleDelete} disabled={deleting || !password}>
                {deleting ? 'Deleting...' : 'Yes, Permanently Delete'}
              </button>
              <button className="btn-cancel-edit" onClick={() => { setShowConfirm(false); setPassword(''); setError('') }}>Cancel</button>
            </div>
            {error && <span style={{ fontSize: '13px', color: '#ef4444' }}>{error}</span>}
          </div>
        )}
      </div>
    </div>
  )
}

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
      setError(connectionErrorMessage())
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

      <YourOrganizationsCard />

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
              <span style={{ fontSize: '13px', color: '#4b5563' }}>Are you sure?</span>
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
      setError(connectionErrorMessage())
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

      <DangerZoneCard />
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
        {activeTab === 'Credits' && <Credits />}
      </Reveal>
    </div>
  )
}

export default StudentSettings
