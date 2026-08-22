import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, getUser, setSession, logout } from '../../api'
import './settings.css'

const TABS = ['Profile', 'Security', 'System']

// ── PROFILE TAB ──
function ProfileTab() {
  const navigate = useNavigate()
  const user = getUser() || {}
  const [fullName, setFullName] = useState(user.full_name || '')
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [showConfirm, setShowConfirm] = useState(false)

  const handleSave = async () => {
    setError('')
    if (!fullName.trim()) { setError('Full name cannot be empty'); return }
    setSaving(true)
    try {
      const res = await apiFetch('/api/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: fullName.trim() })
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Failed to update profile'); return }
      setSession({ ...user, full_name: data.fullName }, localStorage.getItem('token'))
      setEditing(false)
    } catch {
      setError('Cannot connect to server. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="tab-content">
      <div className="settings-card">
        <h4 className="card-label">Account Information</h4>
        <div className="settings-row">
          <div className="admin-avatar-lg">
            {user.full_name ? user.full_name.charAt(0).toUpperCase() : 'A'}
          </div>

          <div className="info-item">
            <span className="info-label">Full name</span>
            {editing ? (
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <input
                  className="settings-select"
                  style={{ background: '#fff' }}
                  value={fullName}
                  onChange={e => setFullName(e.target.value)}
                  autoFocus
                />
                <button className="btn-primary" onClick={handleSave} disabled={saving}>
                  {saving ? 'Saving...' : 'Save'}
                </button>
                <button className="btn-change" onClick={() => { setEditing(false); setFullName(user.full_name || ''); setError('') }}>
                  Cancel
                </button>
              </div>
            ) : (
              <>
                <span className="info-value">{user.full_name || 'Admin'}</span>
                <button className="btn-edit" onClick={() => setEditing(true)}>Edit</button>
              </>
            )}
            {error && <span className="info-sub" style={{ color: '#ef4444' }}>{error}</span>}
          </div>

          <div className="info-item">
            <span className="info-label">Email address</span>
            <span className="info-value">{user.email || '—'}</span>
            <span className="info-sub">Linked to your account, cannot be changed here</span>
          </div>

          <div className="info-item">
            <span className="info-label">Role</span>
            <span className="badge badge-purple">Administrator</span>
          </div>

          <div className="info-item">
            <span className="info-label">Account status</span>
            <span className="badge badge-green">Active</span>
          </div>
        </div>
      </div>

      <div className="settings-card">
        <h4 className="card-label">Session</h4>
        <div className="settings-row">
          <div className="info-item">
            <span className="info-label">Sign out</span>
            <span className="info-sub">
              You are logged in as <strong>{user.email || 'unknown'}</strong>.
              Logging out will end this session everywhere it's used.
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
    </div>
  )
}

// ── SECURITY TAB ──
function SecurityTab() {
  const [passwords, setPasswords] = useState({ current: '', next: '', confirm: '' })
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
    if (!passwords.next) { setError('New password is required'); return }
    if (passwords.next.length < 8) { setError('New password must be at least 8 characters'); return }
    if (passwords.next !== passwords.confirm) { setError('New passwords do not match'); return }

    setSaving(true)
    try {
      const res = await apiFetch('/api/change-password', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: passwords.current, new_password: passwords.next })
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Failed to change password'); return }
      setSuccess(true)
      setPasswords({ current: '', next: '', confirm: '' })
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
          <div className="password-field">
            <label>Current Password</label>
            <input type="password" value={passwords.current} onChange={e => handleChange('current', e.target.value)} />
          </div>
          <div className="password-field">
            <label>New Password</label>
            <input type="password" value={passwords.next} onChange={e => handleChange('next', e.target.value)} />
          </div>
          <div className="password-field">
            <label>Confirm New Password</label>
            <input type="password" value={passwords.confirm} onChange={e => handleChange('confirm', e.target.value)} />
          </div>
        </div>

        <button className="btn-primary" onClick={handleSubmit} disabled={saving} style={{ marginTop: '14px' }}>
          {saving ? 'Updating...' : 'Update Password'}
        </button>
      </div>
    </div>
  )
}

// ── SYSTEM TAB ──
function SystemTab() {
  const [slots, setSlots] = useState(20)
  const [savedLimit, setSavedLimit] = useState(20)
  const [approvedCount, setApprovedCount] = useState(0)
  const [savingLimit, setSavingLimit] = useState(false)
  const [limitError, setLimitError] = useState('')
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    apiFetch('/api/settings')
      .then(res => res.json())
      .then(data => {
        if (typeof data.max_accepted === 'number') { setSlots(data.max_accepted); setSavedLimit(data.max_accepted) }
        if (typeof data.approved_count === 'number') setApprovedCount(data.approved_count)
      })
      .catch(() => {})
  }, [])

  const handleSaveLimit = async () => {
    setLimitError('')
    setSavingLimit(true)
    try {
      const res = await apiFetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_accepted: slots })
      })
      const data = await res.json()
      if (!res.ok) { setLimitError(data.error || 'Failed to update the applicant limit'); return }
      setSavedLimit(data.max_accepted)
      setApprovedCount(data.approved_count)
    } catch {
      setLimitError('Cannot connect to server. Please try again.')
    } finally {
      setSavingLimit(false)
    }
  }

  const handleExportCsv = async () => {
    setExporting(true)
    try {
      const res = await apiFetch('/api/applicants')
      const data = await res.json()
      const applicants = data.applicants || []
      const columns = [
        'full_name', 'email', 'city', 'course', 'gpa', 'ml_score', 'ml_status',
        'application_status', 'submitted_at',
      ]
      const escape = v => `"${String(v ?? '').replace(/"/g, '""')}"`
      const rows = [columns.join(',')]
      applicants.forEach(a => rows.push(columns.map(c => escape(a[c])).join(',')))
      const blob = new Blob([rows.join('\n')], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ecoscholar-applicants-${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert('Failed to export applicants')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="tab-content">
      <div className="settings-card">
        <h4 className="card-label">Accepted Applicant Limit</h4>
        <p className="info-sub" style={{ marginBottom: '14px' }}>
          Approved status is always the top-{savedLimit} eligible applicants by ML score.
          Currently {approvedCount} of {savedLimit} slots accepted. Also editable from the
          Ranking page.
        </p>
        <div className="settings-row">
          <input
            type="number"
            min={1}
            className="settings-select"
            style={{ width: '90px', background: '#fff' }}
            value={slots}
            onChange={e => setSlots(Number(e.target.value))}
          />
          <button className="btn-primary" onClick={handleSaveLimit} disabled={savingLimit || slots === savedLimit}>
            {savingLimit ? 'Saving...' : 'Save'}
          </button>
        </div>
        {limitError && <div className="security-error" style={{ marginTop: '10px' }}>{limitError}</div>}
      </div>

      <div className="settings-card">
        <h4 className="card-label">Data Export</h4>
        <div className="settings-row">
          <div className="info-item">
            <span className="info-label">Export all applicants</span>
            <span className="info-sub">Download the full applicant list as CSV</span>
          </div>
          <button className="btn-primary" onClick={handleExportCsv} disabled={exporting}>
            {exporting ? 'Exporting...' : 'Export CSV'}
          </button>
        </div>
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
          <p className="page-sub">Manage your account and system preferences.</p>
        </div>
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
      {activeTab === 'System' && <SystemTab />}
    </div>
  )
}

export default Settings
