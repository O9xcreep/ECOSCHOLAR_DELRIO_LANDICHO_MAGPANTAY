import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, getUser, setSession, logout } from '../../api'
import './settings.css'

const ALL_TABS = ['Profile', 'Security', 'System', 'Team']

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
            <span className="badge badge-purple">{user.role === 'admin' ? 'Administrator' : 'LGU Member'}</span>
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

// ── PENDING ADMIN REQUESTS ──
function AdminRequestsSection({ onApproved }) {
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [actioningId, setActioningId] = useState(null)
  const [actionError, setActionError] = useState('')

  const loadRequests = async () => {
    setLoading(true)
    setLoadError(false)
    try {
      const res = await apiFetch('/api/admin-requests?status=pending')
      if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
      const data = await res.json()
      setRequests(data.requests || [])
    } catch {
      setLoadError(true)
    }
    setLoading(false)
  }

  useEffect(() => { loadRequests() }, [])

  const handleApprove = async (req) => {
    if (!window.confirm(`Grant admin access to ${req.full_name} (${req.email})? They'll receive an email to set their password.`)) return
    setActionError('')
    setActioningId(req.id)
    try {
      const res = await apiFetch(`/api/admin-requests/${req.id}/approve`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) { setActionError(data.error || 'Failed to approve request'); return }
      setRequests(prev => prev.filter(r => r.id !== req.id))
      onApproved?.(data.admin)
    } catch {
      setActionError('Cannot connect to server. Please try again.')
    } finally {
      setActioningId(null)
    }
  }

  const handleReject = async (req) => {
    if (!window.confirm(`Reject the admin request from ${req.full_name} (${req.email})?`)) return
    setActionError('')
    setActioningId(req.id)
    try {
      const res = await apiFetch(`/api/admin-requests/${req.id}/reject`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) { setActionError(data.error || 'Failed to reject request'); return }
      setRequests(prev => prev.filter(r => r.id !== req.id))
    } catch {
      setActionError('Cannot connect to server. Please try again.')
    } finally {
      setActioningId(null)
    }
  }

  if (loading) return <p className="info-sub">Loading pending requests...</p>
  if (loadError) {
    return (
      <div>
        <div className="security-error" style={{ marginBottom: '10px' }}>Couldn't load admin requests.</div>
        <button className="btn-change" onClick={loadRequests}>Retry</button>
      </div>
    )
  }
  if (requests.length === 0) return null

  return (
    <div className="settings-card" style={{ marginBottom: '20px' }}>
      <h4 className="card-label" style={{ marginBottom: '4px' }}>Pending Admin Requests</h4>
      <p className="info-sub" style={{ marginBottom: '14px' }}>
        Submitted via "Apply as Admin" on the login page. Verify the requester is a real LGU official before approving.
      </p>
      {actionError && <div className="security-error" style={{ marginBottom: '10px' }}>{actionError}</div>}
      <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '0' }}>
        {requests.map(req => (
          <div key={req.id} className="info-item" style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', display: 'flex', padding: '12px 0', borderBottom: '1px solid #F0F0F0' }}>
            <div>
              <span className="info-value">{req.full_name}</span>
              <span className="info-sub">{req.email} · {req.office}</span>
              <span className="info-sub">{req.municipality} · {req.contact_number}</span>
              {req.message && <span className="info-sub">"{req.message}"</span>}
              <span className="info-sub">Submitted {req.created_at}</span>
            </div>
            <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
              <button className="btn-primary" onClick={() => handleApprove(req)} disabled={actioningId === req.id}>
                {actioningId === req.id ? 'Working...' : 'Approve'}
              </button>
              <button className="btn-danger-outline" onClick={() => handleReject(req)} disabled={actioningId === req.id}>
                Reject
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const EMPTY_TEAM_FORM = { full_name: '', email: '', role: 'lgu_member', permissions: { can_review_applicants: false, can_manage_members: false } }

// ── TEAM TAB ──
function TeamTab() {
  const currentUser = getUser() || {}
  const isSuperAdmin = currentUser.role === 'admin'
  const [admins, setAdmins] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_TEAM_FORM)
  const [formError, setFormError] = useState('')
  const [creating, setCreating] = useState(false)
  const [removingId, setRemovingId] = useState(null)
  const [resendingId, setResendingId] = useState(null)
  const [resendMessage, setResendMessage] = useState('')
  const [savingPermissionsId, setSavingPermissionsId] = useState(null)
  const [permissionsError, setPermissionsError] = useState('')

  const loadAdmins = async () => {
    setLoading(true)
    setLoadError(false)
    try {
      const res = await apiFetch('/api/admins')
      if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
      const data = await res.json()
      setAdmins(data.admins || [])
    } catch {
      setLoadError(true)
    }
    setLoading(false)
  }

  useEffect(() => { loadAdmins() }, [])

  const handleCreate = async () => {
    setFormError('')
    if (!form.full_name.trim() || !form.email.trim()) {
      setFormError('Full name and email are required'); return
    }

    setCreating(true)
    try {
      const res = await apiFetch('/api/admins', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form)
      })
      const data = await res.json()
      if (!res.ok) { setFormError(data.error || 'Failed to create admin account'); return }
      setAdmins(prev => [...prev, data.admin])
      setForm(EMPTY_TEAM_FORM)
      setShowForm(false)
    } catch {
      setFormError('Cannot connect to server. Please try again.')
    } finally {
      setCreating(false)
    }
  }

  const handleTogglePermission = async (admin, key) => {
    setPermissionsError('')
    setSavingPermissionsId(admin.id)
    const nextPermissions = { ...admin.permissions, [key]: !admin.permissions[key] }
    try {
      const res = await apiFetch(`/api/admins/${admin.id}/permissions`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: 'lgu_member', permissions: nextPermissions })
      })
      const data = await res.json()
      if (!res.ok) { setPermissionsError(data.error || 'Failed to update permissions'); return }
      setAdmins(prev => prev.map(a => a.id === admin.id ? data.admin : a))
    } catch {
      setPermissionsError('Cannot connect to server. Please try again.')
    } finally {
      setSavingPermissionsId(null)
    }
  }

  const handleResendInvite = async (admin) => {
    setResendMessage('')
    setResendingId(admin.id)
    try {
      const res = await apiFetch(`/api/admins/${admin.id}/resend-invite`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) { alert(data.error || 'Failed to resend invite'); return }
      setResendMessage(`Invite resent to ${admin.email}`)
    } catch {
      alert('Cannot connect to server. Please try again.')
    } finally {
      setResendingId(null)
    }
  }

  const handleRemove = async (admin) => {
    if (!window.confirm(`Remove admin access for ${admin.full_name} (${admin.email})?`)) return
    setRemovingId(admin.id)
    try {
      const res = await apiFetch(`/api/admins/${admin.id}`, { method: 'DELETE' })
      const data = await res.json()
      if (!res.ok) { alert(data.error || 'Failed to remove admin account'); return }
      setAdmins(prev => prev.filter(a => a.id !== admin.id))
    } catch {
      alert('Cannot connect to server. Please try again.')
    } finally {
      setRemovingId(null)
    }
  }

  return (
    <div className="tab-content">
      <AdminRequestsSection onApproved={(admin) => admin && setAdmins(prev => [...prev, admin])} />
      <div className="settings-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <h4 className="card-label" style={{ marginBottom: 0 }}>Admin Accounts</h4>
          {!showForm && (
            <button className="btn-primary" onClick={() => setShowForm(true)}>+ Add Admin</button>
          )}
        </div>
        <p className="info-sub" style={{ marginBottom: '14px' }}>
          Super admins have full access. LGU members only get the specific permissions you grant them below.
        </p>
        {resendMessage && <p className="info-sub" style={{ color: '#16a34a', marginBottom: '14px' }}>{resendMessage}</p>}
        {permissionsError && <div className="security-error" style={{ marginBottom: '14px' }}>{permissionsError}</div>}

        {showForm && (
          <div className="settings-row" style={{ marginBottom: '18px', flexDirection: 'column', alignItems: 'stretch', gap: '10px' }}>
            {formError && <div className="security-error">{formError}</div>}
            <div className="password-fields">
              <div className="password-field">
                <label>Full name</label>
                <input value={form.full_name} onChange={e => setForm(p => ({ ...p, full_name: e.target.value }))} />
              </div>
              <div className="password-field">
                <label>Email</label>
                <input type="email" value={form.email} onChange={e => setForm(p => ({ ...p, email: e.target.value }))} />
              </div>
            </div>

            <div className="password-field">
              <label>Role</label>
              <select
                className="settings-select"
                value={form.role}
                onChange={e => setForm(p => ({ ...p, role: e.target.value }))}>
                <option value="lgu_member">LGU Member (scoped access)</option>
                {isSuperAdmin && <option value="admin">Super Admin (full access)</option>}
              </select>
            </div>

            {form.role === 'lgu_member' && (
              <div className="password-field">
                <label>Permissions</label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 400, fontSize: '13.5px', marginBottom: '6px' }}>
                  <input
                    type="checkbox"
                    checked={form.permissions.can_review_applicants}
                    onChange={e => setForm(p => ({ ...p, permissions: { ...p.permissions, can_review_applicants: e.target.checked } }))}
                  />
                  Review applicants (view/decide applications, ranking, reports)
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 400, fontSize: '13.5px' }}>
                  <input
                    type="checkbox"
                    checked={form.permissions.can_manage_members}
                    onChange={e => setForm(p => ({ ...p, permissions: { ...p.permissions, can_manage_members: e.target.checked } }))}
                  />
                  Manage team members (add/remove, approve admin requests)
                </label>
              </div>
            )}

            <p className="info-sub" style={{ marginBottom: 0 }}>
              They'll receive an email with a verification code to set their own password at /admin-setup.
            </p>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button className="btn-primary" onClick={handleCreate} disabled={creating}>
                {creating ? 'Creating...' : 'Create account'}
              </button>
              <button className="btn-change" onClick={() => { setShowForm(false); setForm(EMPTY_TEAM_FORM); setFormError('') }}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <p className="info-sub">Loading admin accounts...</p>
        ) : loadError ? (
          <div>
            <div className="security-error" style={{ marginBottom: '10px' }}>Couldn't load admin accounts.</div>
            <button className="btn-change" onClick={loadAdmins}>Retry</button>
          </div>
        ) : (
          <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '0' }}>
            {admins.map(admin => {
              // An lgu_member (even with can_manage_members) can't touch a super
              // admin's account at all - matches the backend's guard exactly.
              const canManageThisRow = isSuperAdmin || admin.role !== 'admin'
              return (
              <div key={admin.id} className="info-item" style={{ flexDirection: 'column', alignItems: 'stretch', padding: '12px 0', borderBottom: '1px solid #F0F0F0', gap: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <span className="info-value">
                      {admin.full_name} {admin.id === currentUser.id && <span className="badge badge-purple" style={{ marginLeft: '8px' }}>You</span>}
                      <span className="badge" style={{ marginLeft: '8px', background: admin.role === 'admin' ? '#EDE9FE' : '#E0F2FE', color: admin.role === 'admin' ? '#5B21B6' : '#075985' }}>
                        {admin.role === 'admin' ? 'Super Admin' : 'LGU Member'}
                      </span>
                      {!admin.password_set && <span className="badge" style={{ marginLeft: '8px', background: '#FEF3C7', color: '#92400E' }}>Setup pending</span>}
                    </span>
                    <span className="info-sub">{admin.email}</span>
                    {(admin.office || admin.municipality) && (
                      <span className="info-sub">{[admin.office, admin.municipality].filter(Boolean).join(' · ')}</span>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                    {!admin.password_set && canManageThisRow && (
                      <button
                        className="btn-change"
                        onClick={() => handleResendInvite(admin)}
                        disabled={resendingId === admin.id}>
                        {resendingId === admin.id ? 'Sending...' : 'Resend Invite'}
                      </button>
                    )}
                    {admin.id !== currentUser.id && canManageThisRow && admins.length > 1 && (
                      <button
                        className="btn-danger-outline"
                        onClick={() => handleRemove(admin)}
                        disabled={removingId === admin.id}>
                        {removingId === admin.id ? 'Removing...' : 'Remove'}
                      </button>
                    )}
                  </div>
                </div>
                {admin.role === 'lgu_member' && (
                  <div style={{ display: 'flex', gap: '18px', paddingLeft: '2px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12.5px', color: 'var(--text-secondary, #6B7280)' }}>
                      <input
                        type="checkbox"
                        checked={admin.permissions.can_review_applicants}
                        disabled={admin.id === currentUser.id || savingPermissionsId === admin.id}
                        onChange={() => handleTogglePermission(admin, 'can_review_applicants')}
                      />
                      Review applicants
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12.5px', color: 'var(--text-secondary, #6B7280)' }}>
                      <input
                        type="checkbox"
                        checked={admin.permissions.can_manage_members}
                        disabled={admin.id === currentUser.id || savingPermissionsId === admin.id}
                        onChange={() => handleTogglePermission(admin, 'can_manage_members')}
                      />
                      Manage team members
                    </label>
                  </div>
                )}
              </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ── MAIN SETTINGS ──
function Settings() {
  const [activeTab, setActiveTab] = useState('Profile')
  const currentUser = getUser() || {}
  const isSuperAdmin = currentUser.role === 'admin'
  const canManageMembers = isSuperAdmin || !!currentUser.permissions?.can_manage_members

  // System (eligibility/export settings) stays super-admin-only; Team needs
  // can_manage_members. Profile/Security are always available to everyone.
  const tabs = ALL_TABS.filter(tab =>
    (tab !== 'System' || isSuperAdmin) && (tab !== 'Team' || canManageMembers)
  )

  return (
    <div className="settings-page">
      <div className="settings-header">
        <div>
          <h2 className="page-title">Settings</h2>
          <p className="page-sub">Manage your account and system preferences.</p>
        </div>
      </div>

      <div className="settings-tabs">
        {tabs.map(tab => (
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
      {activeTab === 'Team' && <TeamTab />}
    </div>
  )
}

export default Settings
