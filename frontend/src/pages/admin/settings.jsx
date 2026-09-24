import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import writeExcelFile from 'write-excel-file/browser'
import { apiFetch, getUser, setSession, clearSession, logout, isFullAccess, connectionErrorMessage } from '../../api'
import FormBuilder from './FormBuilder'
import GuidelinesEditor from './GuidelinesEditor'
import AdminGuide from './AdminGuide'
import Reveal from '../../components/Reveal'
import Credits from '../../components/Credits'
import pageBg from '../../assets/bg3.jpg'
import './settings.css'

const ALL_TABS = ['Profile', 'System', 'Team', 'Credits']

// ── YOUR ORGANIZATIONS ──
// Lists every org this account belongs to (a login can now hold membership
// in more than one), with a "Switch" action, plus a collapsible form to
// request joining another one. Unlike a student's self-service join, this
// always goes to that org's own admins for approval - a join code isn't a
// secret credential, so letting staff self-attach to any org's team
// unvetted would be a real privilege-escalation risk.
function YourOrganizationsCard() {
  const [memberships, setMemberships] = useState([])
  const [loading, setLoading] = useState(true)
  const [switchingId, setSwitchingId] = useState('')
  const [switchError, setSwitchError] = useState('')

  const [showJoinForm, setShowJoinForm] = useState(false)
  const [joinCode, setJoinCode] = useState('')
  const [joinCodeOrgName, setJoinCodeOrgName] = useState('')
  const [joinCodeError, setJoinCodeError] = useState('')
  const [joinCodeChecking, setJoinCodeChecking] = useState(false)
  const [contactNumber, setContactNumber] = useState('')
  const [message, setMessage] = useState('')
  const [proofFile, setProofFile] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [submitSuccess, setSubmitSuccess] = useState('')

  const loadMemberships = () => {
    setLoading(true)
    apiFetch('/api/memberships')
      .then(res => res.json())
      .then(data => setMemberships(data.memberships || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(loadMemberships, [])

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
      // Full reload, not just setSession - nothing on this page (or any
      // other) re-reads "current org" reactively after mount, so an
      // in-place update would leave every list/dashboard showing stale data.
      window.location.href = '/admin/dashboard'
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

  const handleSubmitJoinRequest = async () => {
    setSubmitError('')
    setSubmitSuccess('')
    if (!joinCode.trim() || !contactNumber.trim()) {
      setSubmitError('Join code and contact number are required')
      return
    }
    if (!proofFile) {
      setSubmitError('A valid ID or proof-of-employment document is required')
      return
    }
    setSubmitting(true)
    try {
      const formData = new FormData()
      formData.append('join_code', joinCode.trim().toUpperCase())
      formData.append('contact_number', contactNumber.trim())
      formData.append('message', message.trim())
      formData.append('file', proofFile)
      const res = await apiFetch('/api/admin-requests/join-org', { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) { setSubmitError(data.error || 'Failed to submit request'); return }
      setSubmitSuccess(data.message || 'Your request has been submitted for review.')
      setShowJoinForm(false)
      setJoinCode(''); setJoinCodeOrgName(''); setContactNumber(''); setMessage(''); setProofFile(null)
    } catch {
      setSubmitError(connectionErrorMessage())
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="settings-card">
      <h4 className="card-label">Your Organizations</h4>
      <p className="info-sub" style={{ marginBottom: '14px' }}>
        Every organization your account belongs to. Switch which one is active, or request to join another.
      </p>

      {loading ? (
        <p className="info-sub">Loading...</p>
      ) : (
        <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '0' }}>
          {memberships.map(m => (
            <div key={m.organization_id} className="team-row" style={{ padding: '10px 0', borderBottom: '1px solid #F0F0F0' }}>
              <div className="team-row-info">
                <span className="info-value">
                  {m.organization_name || 'Unknown organization'}
                  <span className="badge" style={{ marginLeft: '8px', background: '#E0F2FE', color: '#075985' }}>
                    {m.role === 'lgu_admin' ? 'Admin' : m.role === 'lgu_member' ? 'LGU Member' : 'Student'}
                  </span>
                  {m.is_active && <span className="badge badge-green" style={{ marginLeft: '8px' }}>Active</span>}
                </span>
              </div>
              <div className="team-row-actions">
                {!m.is_active && (
                  <button className="btn-change" onClick={() => handleSwitch(m.organization_id)} disabled={switchingId === m.organization_id}>
                    {switchingId === m.organization_id ? 'Switching...' : 'Switch'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {switchError && <div className="security-error" style={{ marginTop: '10px' }}>{switchError}</div>}

      <div style={{ marginTop: '18px', paddingTop: '18px', borderTop: '1px solid #F0F0F0' }}>
        {!showJoinForm ? (
          <button className="btn-primary" onClick={() => { setShowJoinForm(true); setSubmitSuccess('') }}>
            Request to Join Another Organization
          </button>
        ) : (
          <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '10px' }}>
            {submitError && <div className="security-error">{submitError}</div>}
            <div className="password-field">
              <label>LGU Join Code</label>
              <input
                value={joinCode}
                onChange={e => { setJoinCode(e.target.value); setJoinCodeOrgName(''); setJoinCodeError('') }}
                onBlur={handleJoinCodeBlur}
                placeholder="e.g. ABCD1234"
              />
              {joinCodeChecking && <span className="info-sub">Checking...</span>}
              {joinCodeOrgName && <span className="info-sub" style={{ color: '#059669' }}>Joining {joinCodeOrgName}</span>}
              {joinCodeError && <span className="info-sub" style={{ color: '#ef4444' }}>{joinCodeError}</span>}
            </div>
            <div className="password-field">
              <label>Contact number</label>
              <input value={contactNumber} onChange={e => setContactNumber(e.target.value)} />
            </div>
            <div className="password-field">
              <label>Message (optional)</label>
              <input value={message} onChange={e => setMessage(e.target.value)} placeholder="Anything the reviewing admin should know" />
            </div>
            <div className="password-field">
              <label>ID or proof of employment</label>
              <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={e => setProofFile(e.target.files[0] || null)} />
            </div>
            <div>
              <button className="btn-primary" onClick={handleSubmitJoinRequest} disabled={submitting}>
                {submitting ? 'Submitting...' : 'Submit Request'}
              </button>
              <button className="btn-change" style={{ marginLeft: '8px' }} onClick={() => setShowJoinForm(false)}>Cancel</button>
            </div>
          </div>
        )}
        {submitSuccess && <div className="info-sub" style={{ color: '#059669', marginTop: '10px' }}>{submitSuccess}</div>}
      </div>
    </div>
  )
}

// ── DANGER ZONE ──
// Deleting an organization is permanent and takes its applicants and uploaded
// documents with it, so it asks for the org's name and the user's password.
function DeleteOrganizationRow({ organization, onDeleted }) {
  const navigate = useNavigate()
  const [showConfirm, setShowConfirm] = useState(false)
  const [confirmName, setConfirmName] = useState('')
  const [password, setPassword] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  const nameMatches = confirmName.trim() === organization.organization_name

  const closeConfirm = () => { setShowConfirm(false); setConfirmName(''); setPassword(''); setError('') }

  const handleDelete = async () => {
    setError('')
    setDeleting(true)
    try {
      const res = await apiFetch(`/api/organizations/${organization.organization_id}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password, confirm_name: confirmName.trim() })
      })
      const data = await res.json()
      if (!res.ok) { setError(data.error || 'Failed to delete organization'); return }
      window.alert(data.message)
      if (data.token) {
        // Deleted the organization they were working in; the server moved them
        // into another one they belong to. Full reload, same as switching.
        setSession(data.user, data.token)
        window.location.href = data.user.role === 'student' ? '/student/dashboard' : '/admin/dashboard'
      } else if (data.signed_out) {
        clearSession()
        navigate('/login')
      } else {
        closeConfirm()
        onDeleted()
      }
    } catch {
      setError(connectionErrorMessage())
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="danger-row">
      <div className="settings-row">
        <div className="info-item">
          <span className="info-label">Delete organization</span>
          <span className="info-sub">
            Permanently deletes <strong>{organization.organization_name}</strong> and everything in it:
            every application and uploaded document, program history, settings and the join code.
            Students keep their logins but their saved information is cleared, and they'll be asked to
            join another organization with a join code. Everyone else on the team loses access to it.
            This cannot be undone.
          </span>
          {!showConfirm ? (
            <button className="btn-danger-outline" onClick={() => setShowConfirm(true)}>Delete Organization</button>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '8px', alignItems: 'flex-start' }}>
              <span className="info-sub">Type <strong>{organization.organization_name}</strong> to confirm</span>
              <input
                className="settings-select"
                style={{ background: '#fff' }}
                placeholder="Organization name"
                value={confirmName}
                onChange={e => setConfirmName(e.target.value)}
              />
              <input
                type="password"
                className="settings-select"
                style={{ background: '#fff' }}
                placeholder="Enter your password to confirm"
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <button className="btn-danger" onClick={handleDelete} disabled={deleting || !nameMatches || !password}>
                  {deleting ? 'Deleting...' : 'Yes, Permanently Delete'}
                </button>
                <button className="btn-change" onClick={closeConfirm}>Cancel</button>
              </div>
              {error && <span className="info-sub" style={{ color: '#ef4444' }}>{error}</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function DeleteAccountRow() {
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
    <div className="danger-row">
      <div className="settings-row">
        <div className="info-item">
          <span className="info-label">Delete account</span>
          <span className="info-sub">
            Permanently deletes your login. Past applicant/audit history stays visible to admins,
            exactly as it does today when a teammate is removed - only your ability to sign in is gone.
          </span>
          {!showConfirm ? (
            <button className="btn-danger-outline" onClick={() => setShowConfirm(true)}>Delete Account</button>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '8px', alignItems: 'flex-start' }}>
              <input
                type="password"
                className="settings-select"
                style={{ background: '#fff' }}
                placeholder="Enter your password to confirm"
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                <button className="btn-danger" onClick={handleDelete} disabled={deleting || !password}>
                  {deleting ? 'Deleting...' : 'Yes, Permanently Delete'}
                </button>
                <button className="btn-change" onClick={() => { setShowConfirm(false); setPassword(''); setError('') }}>Cancel</button>
              </div>
              {error && <span className="info-sub" style={{ color: '#ef4444' }}>{error}</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function DangerZoneCard() {
  const [adminOrganizations, setAdminOrganizations] = useState([])

  // Only whoever holds an organization's Admin seat can delete it, so this
  // lists just the memberships where the user is that Admin.
  const loadAdminOrganizations = () => {
    apiFetch('/api/memberships')
      .then(res => res.json())
      .then(data => setAdminOrganizations((data.memberships || []).filter(m => m.role === 'lgu_admin')))
      .catch(() => {})
  }

  useEffect(loadAdminOrganizations, [])

  return (
    <div className="settings-card">
      <h4 className="card-label">Danger Zone</h4>
      {adminOrganizations.map(organization => (
        <DeleteOrganizationRow
          key={organization.organization_id}
          organization={organization}
          onDeleted={loadAdminOrganizations}
        />
      ))}
      <DeleteAccountRow />
    </div>
  )
}

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
      setError(connectionErrorMessage())
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
            <span className="badge badge-purple">
              {user.role === 'admin' ? 'Super Admin' : user.role === 'lgu_admin' ? 'Admin' : 'LGU Member'}
            </span>
          </div>

          <div className="info-item">
            <span className="info-label">Account status</span>
            <span className="badge badge-green">Active</span>
          </div>
        </div>
      </div>

      {user.role !== 'admin' && <YourOrganizationsCard />}

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
                <span style={{ fontSize: '13px', color: '#4b5563' }}>Are you sure?</span>
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
  const user = getUser() || {}
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

      {user.role !== 'admin' && <DangerZoneCard />}
    </div>
  )
}

// ── SYSTEM TAB ──
// datetime-local inputs are naive "what you see is what you get" local time, with no
// timezone marker - these two helpers do the conversion to/from the naive-UTC string
// the backend stores (see are_results_visible() in app.py, compared against
// datetime.utcnow()), so a Philippine admin picking "2pm" means 2pm Manila time, not
// 2pm UTC.
function utcStringToLocalInputValue(utcStr) {
  if (!utcStr) return ''
  const d = new Date(utcStr.replace(' ', 'T') + 'Z')
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function localInputValueToUtcIso(localStr) {
  return localStr ? new Date(localStr).toISOString() : null
}

function SystemTab() {
  const currentUser = getUser() || {}
  const canResetProgram = isFullAccess(currentUser) || !!currentUser.permissions?.can_reset_program

  const [slots, setSlots] = useState(20)
  const [savedLimit, setSavedLimit] = useState(20)
  const [approvedCount, setApprovedCount] = useState(0)
  const [savingLimit, setSavingLimit] = useState(false)
  const [limitError, setLimitError] = useState('')
  const [topPercent, setTopPercent] = useState(30)
  const [savedTopPercent, setSavedTopPercent] = useState(30)
  const [topPercentChoices, setTopPercentChoices] = useState([])
  const [eligibilityCutoff, setEligibilityCutoff] = useState(null)
  const [exporting, setExporting] = useState(false)

  const [visibleAfter, setVisibleAfter] = useState('')
  const [savedVisibleAfter, setSavedVisibleAfter] = useState('')
  const [override, setOverride] = useState('auto')
  const [savedOverride, setSavedOverride] = useState('auto')
  const [resultsVisibleNow, setResultsVisibleNow] = useState(true)
  const [savingVisibility, setSavingVisibility] = useState(false)
  const [visibilityError, setVisibilityError] = useState('')

  const [currentCycle, setCurrentCycle] = useState(null)
  const [resetPasswordSet, setResetPasswordSet] = useState(false)
  const [newResetPassword, setNewResetPassword] = useState('')
  const [savingResetPassword, setSavingResetPassword] = useState(false)
  const [resetPasswordError, setResetPasswordError] = useState('')
  const [resetPasswordSuccess, setResetPasswordSuccess] = useState(false)
  const currentYear = new Date().getFullYear()
  const [startYear, setStartYear] = useState(currentYear)
  const [endYear, setEndYear] = useState(currentYear + 1)
  const [newCycleDeadline, setNewCycleDeadline] = useState('')
  const [resetConfirmPassword, setResetConfirmPassword] = useState('')
  const [resetting, setResetting] = useState(false)
  const [resetError, setResetError] = useState('')
  const [resetSuccess, setResetSuccess] = useState('')

  const [updatingDeadline, setUpdatingDeadline] = useState(false)
  const [updateDeadlineError, setUpdateDeadlineError] = useState('')
  const [updateDeadlineSuccess, setUpdateDeadlineSuccess] = useState('')

  const [exportCycles, setExportCycles] = useState([])
  const [exportRangePreset, setExportRangePreset] = useState('all')
  const [exportFrom, setExportFrom] = useState('')
  const [exportTo, setExportTo] = useState('')

  useEffect(() => {
    apiFetch('/api/program-cycles')
      .then(res => res.json())
      .then(data => setExportCycles(data.cycles || []))
      .catch(() => {})
  }, [])

  const loadSettings = () => {
    apiFetch('/api/settings')
      .then(res => res.json())
      .then(data => {
        if (typeof data.max_accepted === 'number') { setSlots(data.max_accepted); setSavedLimit(data.max_accepted) }
        if (typeof data.approved_count === 'number') setApprovedCount(data.approved_count)
        if (typeof data.eligibility_top_percent === 'number') {
          setTopPercent(data.eligibility_top_percent)
          setSavedTopPercent(data.eligibility_top_percent)
        }
        setTopPercentChoices(data.eligibility_top_percent_choices || [])
        setEligibilityCutoff(data.eligibility_cutoff ?? null)

        const localValue = utcStringToLocalInputValue(data.results_visible_after)
        setVisibleAfter(localValue)
        setSavedVisibleAfter(localValue)
        const overrideValue = data.results_visible_override === true ? 'show'
          : data.results_visible_override === false ? 'hide' : 'auto'
        setOverride(overrideValue)
        setSavedOverride(overrideValue)
        if (typeof data.results_visible_now === 'boolean') setResultsVisibleNow(data.results_visible_now)

        setResetPasswordSet(!!data.reset_password_set)
        setCurrentCycle(data.current_cycle || null)
        // Pre-fill the shared deadline field with the live cycle's current
        // deadline, so "Update Deadline" has something sensible to start from.
        if (data.current_cycle && !data.current_cycle.closed_at) {
          setNewCycleDeadline(utcStringToLocalInputValue(data.current_cycle.deadline))
        }
      })
      .catch(() => {})
  }

  useEffect(loadSettings, [])

  const handleSaveResetPassword = async () => {
    setResetPasswordError('')
    setResetPasswordSuccess(false)
    setSavingResetPassword(true)
    try {
      const res = await apiFetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reset_password: newResetPassword })
      })
      const data = await res.json()
      if (!res.ok) { setResetPasswordError(data.error || 'Failed to update the reset confirmation password'); return }
      setResetPasswordSet(data.reset_password_set)
      setNewResetPassword('')
      setResetPasswordSuccess(true)
    } catch {
      setResetPasswordError(connectionErrorMessage())
    } finally {
      setSavingResetPassword(false)
    }
  }

  const isFirstSetup = !currentCycle

  const handleProgramReset = async () => {
    setResetError('')
    setResetSuccess('')

    if (!window.confirm(
      isFirstSetup
        ? "Start this scholarship program now?"
        : "This archives every current applicant record (nothing is deleted - it stays " +
          "visible in Reports) and starts a brand new program. Students will see a fresh, " +
          "empty application state. Are you sure?"
    )) return

    setResetting(true)
    try {
      const deadlineIso = localInputValueToUtcIso(newCycleDeadline)
      const res = await apiFetch('/api/program-reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          password: resetConfirmPassword,
          label: `Batch ${startYear}-${endYear}`,
          deadline: deadlineIso || undefined,
          eligibility_top_percent: topPercent,
        })
      })
      const data = await res.json()
      if (!res.ok) { setResetError(data.error || 'Failed to reset the program'); return }

      setSavedTopPercent(data.eligibility_top_percent)
      setEligibilityCutoff(data.eligibility_cutoff ?? null)

      setResetSuccess(`Done - ${data.archived_applicant_count} applicant(s) archived. "${data.current_cycle.label}" has started.`)
      setResetConfirmPassword('')
      setCurrentCycle(data.current_cycle)
      setApprovedCount(data.approved_count)
    } catch {
      setResetError(connectionErrorMessage())
    } finally {
      setResetting(false)
    }
  }

  const handleUpdateDeadline = async () => {
    setUpdateDeadlineError('')
    setUpdateDeadlineSuccess('')
    setUpdatingDeadline(true)
    try {
      const res = await apiFetch('/api/program-cycles/current/deadline', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deadline: localInputValueToUtcIso(newCycleDeadline) })
      })
      const data = await res.json()
      if (!res.ok) { setUpdateDeadlineError(data.error || 'Failed to update the deadline'); return }
      setCurrentCycle(data)
      setUpdateDeadlineSuccess('Deadline updated.')
    } catch {
      setUpdateDeadlineError(connectionErrorMessage())
    } finally {
      setUpdatingDeadline(false)
    }
  }

  const visibilityDirty = visibleAfter !== savedVisibleAfter || override !== savedOverride

  const handleSaveVisibility = async () => {
    setVisibilityError('')
    setSavingVisibility(true)
    try {
      const res = await apiFetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          results_visible_after: localInputValueToUtcIso(visibleAfter),
          results_visible_override: override === 'show' ? true : override === 'hide' ? false : null,
        })
      })
      const data = await res.json()
      if (!res.ok) { setVisibilityError(data.error || 'Failed to update result visibility'); return }
      const localValue = utcStringToLocalInputValue(data.results_visible_after)
      setVisibleAfter(localValue)
      setSavedVisibleAfter(localValue)
      setSavedOverride(override)
      setResultsVisibleNow(data.results_visible_now)
    } catch {
      setVisibilityError(connectionErrorMessage())
    } finally {
      setSavingVisibility(false)
    }
  }

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
      setLimitError(connectionErrorMessage())
    } finally {
      setSavingLimit(false)
    }
  }

  // A cycle's start/end dates are just a convenient way to fill in the date
  // fields below - the actual filter always runs on submitted_at, so picking
  // "Custom range" and typing dates works exactly the same way.
  const handleExportRangePreset = (value) => {
    setExportRangePreset(value)
    if (value === 'all') { setExportFrom(''); setExportTo(''); return }
    if (value === 'custom') return
    const cycle = exportCycles.find(c => (c.id || 'legacy') === value)
    if (cycle) {
      setExportFrom(cycle.started_at ? cycle.started_at.slice(0, 10) : '')
      setExportTo(cycle.closed_at ? cycle.closed_at.slice(0, 10) : '')
    }
  }

  const handleExportExcel = async () => {
    setExporting(true)
    try {
      const res = await apiFetch('/api/applicants/export')
      const data = await res.json()
      if (!res.ok) { alert(data.error || 'Failed to export applicants'); return }
      let applicants = data.applicants || []
      if (exportFrom) applicants = applicants.filter(a => a.submitted_at && a.submitted_at.slice(0, 10) >= exportFrom)
      if (exportTo) applicants = applicants.filter(a => a.submitted_at && a.submitted_at.slice(0, 10) <= exportTo)

      const headerRow = [
        'Full Name', 'Email', 'City', 'Course', 'GWA', 'ML Score', 'ML Status', 'Application Status', 'Submitted At',
        // Eligibility model input features (see build_feature_row on the backend) -
        // included so an export can be reviewed/audited alongside the ML decision.
        'Monthly Household Income', 'Family Size', 'Number of Siblings', 'Siblings Studying',
        "Father's Occupation", "Father's Education", "Mother's Occupation", "Mother's Education",
        'Housing Situation',
      ]
      const sheetData = [
        headerRow,
        ...applicants.map(a => ([
          a.full_name || '',
          a.email || '',
          a.city || '',
          a.course || '',
          a.gpa != null ? Number(a.gpa) : '',
          a.ml_score != null ? Number(a.ml_score) : '',
          a.ml_status || '',
          a.application_status || '',
          a.submitted_at || '',
          a.household_income != null ? Number(a.household_income) : '',
          a.family_size != null ? Number(a.family_size) : '',
          a.num_siblings != null ? Number(a.num_siblings) : '',
          a.num_siblings_studying != null ? Number(a.num_siblings_studying) : '',
          a.father_occupation || '',
          a.father_education || '',
          a.mother_occupation || '',
          a.mother_education || '',
          a.housing_situation || '',
        ]))
      ]

      let rangeLabel = 'all'
      if (exportFrom || exportTo) {
        const submittedYears = applicants.map(a => a.submitted_at?.slice(0, 4)).filter(Boolean)
        const fromYear = exportFrom ? exportFrom.slice(0, 4) : submittedYears.sort()[0]
        const toYear = exportTo ? exportTo.slice(0, 4) : submittedYears.sort().slice(-1)[0]
        rangeLabel = fromYear && toYear ? (fromYear === toYear ? fromYear : `${fromYear}-${toYear}`) : 'filtered'
      }

      await writeExcelFile(sheetData).toFile(`ecoscholar-applicants-${rangeLabel}.xlsx`)
    } catch {
      alert('Failed to export applicants')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="tab-content">
      {canResetProgram && (
      <div className="settings-card">
        <h4 className="card-label">Scholarship Program Creation</h4>
        <p className="info-sub" style={{ marginBottom: '14px' }}>
          These settings together define how a scholarship program runs - how many
          applicants it accepts, when students find out the results, and the program
          itself (its name, deadline, and starting it).
        </p>

        <div className="settings-subcard">
          <h5 className="settings-subcard-title">Accepted Applicant Limit</h5>
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

        <div className="settings-subcard">
          <h5 className="settings-subcard-title">Eligibility Bar</h5>
          <p className="info-sub" style={{ marginBottom: '10px' }}>
            Who qualifies at all: an applicant must be within the top {savedTopPercent}% of need
            {eligibilityCutoff != null && <> (a Total Score of about {eligibilityCutoff} or higher)</>}.
            The Accepted Applicant Limit above then decides how many qualifying applicants are
            funded.
          </p>
          <p className="info-sub">
            {currentCycle
              ? <>The bar is <strong>fixed for this program</strong>, so every applicant is judged by the
                same standard. You can choose a different bar when you start the next program
                (Reset &amp; Start New Program, below).</>
              : 'Choose the bar when you set up the program below. Once the program starts, it stays fixed until the next one.'}
          </p>
        </div>

        <div className="settings-subcard">
          <h5 className="settings-subcard-title">Result Visibility</h5>
          <p className="info-sub" style={{ marginBottom: '14px' }}>
            Controls when students can see an Approved/Rejected decision (and, once
            ranking is shown to students, their rank). Applications still in review are
            always visible to the applicant regardless of this setting.
            {' '}Students currently{resultsVisibleNow ? ' CAN ' : ' CANNOT '}see decisions.
          </p>
          <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '10px' }}>
            <div>
              <label className="info-label" style={{ display: 'block', marginBottom: '6px' }}>
                Show results after
              </label>
              <input
                type="datetime-local"
                className="settings-select"
                style={{ background: '#fff' }}
                value={visibleAfter}
                onChange={e => setVisibleAfter(e.target.value)}
              />
              {visibleAfter && (
                <button className="btn-change" style={{ marginLeft: '8px' }}
                  onClick={() => setVisibleAfter('')}>
                  Clear
                </button>
              )}
            </div>
            <div>
              <label className="info-label" style={{ display: 'block', marginBottom: '6px' }}>
                Manual override
              </label>
              <select className="settings-select" style={{ background: '#fff' }}
                value={override} onChange={e => setOverride(e.target.value)}>
                <option value="auto">Automatic (use date/time above)</option>
                <option value="show">Force visible now</option>
                <option value="hide">Force hidden</option>
              </select>
            </div>
            <div>
              <button className="btn-primary" onClick={handleSaveVisibility}
                disabled={savingVisibility || !visibilityDirty}>
                {savingVisibility ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
          {visibilityError && <div className="security-error" style={{ marginTop: '10px' }}>{visibilityError}</div>}
        </div>

        <div className="settings-subcard">
          <h5 className="settings-subcard-title">{isFirstSetup ? 'Set Up Scholarship Program' : 'Reset & Start New Program'}</h5>
          <p className="info-sub" style={{ marginBottom: '14px' }}>
            {isFirstSetup
              ? "Students can't apply until a scholarship program is open. Set a " +
                "deadline (applications close automatically once it passes), then start the program."
              : "Archives every current applicant record and starts a brand new program. Nothing " +
                "is deleted - past programs stay fully visible in Reports - but student " +
                "dashboards and the live Applications queue show a clean slate, and past " +
                "applicants can submit a new application under the new program."}
          </p>

          {currentCycle && (
            <p className="info-sub" style={{ marginBottom: '14px' }}>
              Current program: <strong>{currentCycle.label}</strong>
              {currentCycle.started_at && ` — started ${new Date(currentCycle.started_at).toLocaleDateString('en-PH', {
                month: 'long', day: 'numeric', year: 'numeric'
              })}`}
              {currentCycle.deadline && `, deadline ${new Date(currentCycle.deadline).toLocaleString('en-PH', {
                month: 'long', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit'
              })}`}
              {' '}— {currentCycle.is_open ? <span style={{ color: '#059669' }}>open</span> : <span style={{ color: '#DC2626' }}>closed</span>}
            </p>
          )}

          <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '10px', marginBottom: '14px' }}>
            <div>
              <label className="info-label" style={{ display: 'block', marginBottom: '6px' }}>
                Reset confirmation password {resetPasswordSet ? '(already set — enter a new one to change it)' : '(not set yet — required before resetting)'}
              </label>
              <input
                type="password"
                className="settings-select"
                style={{ background: '#fff', width: '260px' }}
                placeholder="At least 6 characters"
                value={newResetPassword}
                onChange={e => setNewResetPassword(e.target.value)}
              />
              <button className="btn-primary" style={{ marginLeft: '8px' }}
                onClick={handleSaveResetPassword} disabled={savingResetPassword || !newResetPassword}>
                {savingResetPassword ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
          {resetPasswordError && <div className="security-error" style={{ marginBottom: '10px' }}>{resetPasswordError}</div>}
          {resetPasswordSuccess && <div className="info-sub" style={{ color: '#059669', marginBottom: '10px' }}>Reset confirmation password updated.</div>}

          <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '10px' }}>
            <div>
              <label className="info-label" style={{ display: 'block', marginBottom: '6px' }}>
                Batch
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <input
                  type="number"
                  className="settings-select"
                  style={{ width: '80px', background: '#fff' }}
                  value={startYear}
                  onChange={e => {
                    const year = Number(e.target.value)
                    setStartYear(year)
                    setEndYear(year + 1)
                  }}
                />
                <span>-</span>
                <input
                  type="number"
                  className="settings-select"
                  style={{ width: '80px', background: '#fff' }}
                  value={endYear}
                  onChange={e => setEndYear(Number(e.target.value))}
                />
              </div>
            </div>
            <div>
              <label className="info-label" style={{ display: 'block', marginBottom: '6px' }}>
                Application deadline <span style={{ color: '#DC2626' }}>*</span>
              </label>
              <input
                type="datetime-local"
                className="settings-select"
                style={{ background: '#fff' }}
                value={newCycleDeadline}
                onChange={e => setNewCycleDeadline(e.target.value)}
              />
              <p className="info-sub" style={{ marginTop: '4px' }}>
                Applications close automatically once this passes.{' '}
                {currentCycle && !currentCycle.closed_at
                  ? 'Click "Update Deadline" to change it for the program that\'s currently running, or "Reset & Start New Program" to archive everything and start fresh with this date.'
                  : 'Required to start the program.'}
              </p>
            </div>
            <div>
              <label className="info-label" style={{ display: 'block', marginBottom: '6px' }}>
                Eligibility bar for {isFirstSetup ? 'this' : 'the new'} program
              </label>
              <select
                className="settings-select"
                style={{ width: '170px', background: '#fff' }}
                value={topPercent}
                onChange={e => setTopPercent(Number(e.target.value))}
              >
                {topPercentChoices.map(p => (
                  <option key={p} value={p}>Top {p}% of need</option>
                ))}
              </select>
              <p className="info-sub" style={{ marginTop: '4px' }}>
                Fixed once the program starts; it can only be changed when the next program is started.
                {topPercent <= 10 && ' A very strict bar leaves the model few examples to learn from, so its '
                  + 'decisions near the cutoff are less reliable. Review borderline applicants manually.'}
              </p>
            </div>
            <div>
              <label className="info-label" style={{ display: 'block', marginBottom: '6px' }}>
                Reset confirmation password
              </label>
              <input
                type="password"
                className="settings-select"
                style={{ background: '#fff', width: '260px' }}
                value={resetConfirmPassword}
                onChange={e => setResetConfirmPassword(e.target.value)}
              />
            </div>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {currentCycle && !currentCycle.closed_at && (
                <button className="btn-primary" onClick={handleUpdateDeadline}
                  disabled={updatingDeadline || !newCycleDeadline}>
                  {updatingDeadline ? 'Updating...' : 'Update Deadline'}
                </button>
              )}
              <button className="btn-danger" onClick={handleProgramReset}
                disabled={resetting || !resetConfirmPassword || !resetPasswordSet || !newCycleDeadline}>
                {resetting ? 'Setting up...' : isFirstSetup ? 'Set Up Scholarship Program' : 'Reset & Start New Program'}
              </button>
            </div>
          </div>
          {updateDeadlineError && <div className="security-error" style={{ marginTop: '10px' }}>{updateDeadlineError}</div>}
          {updateDeadlineSuccess && <div className="info-sub" style={{ color: '#059669', marginTop: '10px' }}>{updateDeadlineSuccess}</div>}
          {resetError && <div className="security-error" style={{ marginTop: '10px' }}>{resetError}</div>}
          {resetSuccess && <div className="info-sub" style={{ color: '#059669', marginTop: '10px' }}>{resetSuccess}</div>}
        </div>
      </div>
      )}

      {canResetProgram && (
      <div className="settings-card">
        <h4 className="card-label">Data Export</h4>
        <p className="info-sub" style={{ marginBottom: '14px' }}>
          Download applicants as an Excel (.xlsx) file, including the eligibility model's
          input features (household income, family size, parents' education/occupation,
          housing situation, etc.), optionally narrowed to a submission date range - pick a
          past program for a quick range, or set custom dates.
        </p>
        <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '10px' }}>
          <div>
            <label className="info-label" style={{ display: 'block', marginBottom: '6px' }}>
              Range
            </label>
            <select className="settings-select" style={{ background: '#fff' }}
              value={exportRangePreset} onChange={e => handleExportRangePreset(e.target.value)}>
              <option value="all">All applicants</option>
              <option value="custom">Custom date range</option>
              {exportCycles.map(c => (
                <option key={c.id || 'legacy'} value={c.id || 'legacy'}>
                  {c.label}{c.is_current ? ' (current)' : ''}
                </option>
              ))}
            </select>
          </div>
          {exportRangePreset !== 'all' && (
            <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap' }}>
              <div>
                <label className="info-label" style={{ display: 'block', marginBottom: '6px' }}>From</label>
                <input type="date" className="settings-select" style={{ background: '#fff' }}
                  value={exportFrom}
                  onChange={e => { setExportFrom(e.target.value); setExportRangePreset('custom') }} />
              </div>
              <div>
                <label className="info-label" style={{ display: 'block', marginBottom: '6px' }}>To</label>
                <input type="date" className="settings-select" style={{ background: '#fff' }}
                  value={exportTo}
                  onChange={e => { setExportTo(e.target.value); setExportRangePreset('custom') }} />
              </div>
            </div>
          )}
          <div>
            <button className="btn-primary" onClick={handleExportExcel} disabled={exporting}>
              {exporting ? 'Exporting...' : 'Export Excel'}
            </button>
          </div>
        </div>
      </div>
      )}

      {canResetProgram && <FormBuilder />}
      {canResetProgram && <GuidelinesEditor />}
    </div>
  )
}

// ── PENDING ADMIN REQUESTS ──
const EMPTY_APPROVAL_PERMISSIONS = { can_review_applicants: false, can_manage_members: false, can_reset_program: false }

function AdminRequestsSection({ onApproved }) {
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [actioningId, setActioningId] = useState(null)
  const [actionError, setActionError] = useState('')
  const [openingProofId, setOpeningProofId] = useState('')
  // Which request's inline permission-picker is expanded, and what's checked in it -
  // approving now needs to say what the account can do, not just admit it.
  const [approvingId, setApprovingId] = useState('')
  const [pendingPermissions, setPendingPermissions] = useState(EMPTY_APPROVAL_PERMISSIONS)

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

  const handleViewProof = async (req) => {
    setOpeningProofId(req.id)
    try {
      const res = await apiFetch(`/api/admin-requests/${req.id}/proof-of-employment`)
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        alert(data.error || 'Could not load this document')
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank')
    } catch {
      alert(connectionErrorMessage())
    }
    setOpeningProofId('')
  }

  const startApproval = (req) => {
    setActionError('')
    setApprovingId(req.id)
    setPendingPermissions(EMPTY_APPROVAL_PERMISSIONS)
  }

  const confirmApproval = async (req) => {
    const confirmMsg = req.request_kind === 'add_membership'
      ? `Add ${req.full_name} (${req.email}) to your team with the permissions selected below? They already have an account elsewhere - this just adds this organization to it.`
      : `Grant admin access to ${req.full_name} (${req.email}) with the permissions selected below? They already chose a password when applying, so they'll be able to sign in right away.`
    if (!window.confirm(confirmMsg)) return
    setActionError('')
    setActioningId(req.id)
    try {
      const res = await apiFetch(`/api/admin-requests/${req.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ permissions: pendingPermissions }),
      })
      const data = await res.json()
      if (!res.ok) { setActionError(data.error || 'Failed to approve request'); return }
      // Always finalizes on this one approval, whatever permissions were
      // granted. An "add_membership" request (an existing admin/staff account
      // joining this org) returns "membership" instead of "admin", since no
      // new login was created.
      setRequests(prev => prev.filter(r => r.id !== req.id))
      onApproved?.()
    } catch {
      setActionError(connectionErrorMessage())
    } finally {
      setActioningId(null)
    }
  }

  const handleFoundingApproval = async (req) => {
    if (!window.confirm(`Approve "${req.organization_name}" as a new organization and create ${req.full_name} (${req.email}) as its Admin?`)) return
    setActionError('')
    setActioningId(req.id)
    try {
      const res = await apiFetch(`/api/admin-requests/${req.id}/approve`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) { setActionError(data.error || 'Failed to approve request'); return }
      setRequests(prev => prev.filter(r => r.id !== req.id))
      onApproved?.()
    } catch {
      setActionError(connectionErrorMessage())
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
      setActionError(connectionErrorMessage())
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
        Submitted via "Apply as Admin" on the login page. Check their uploaded ID/proof of employment and verify
        the requester is a real LGU official before approving.
      </p>
      {actionError && <div className="security-error" style={{ marginBottom: '10px' }}>{actionError}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {requests.map(req => {
          return (
          <div key={req.id} style={{ border: '1px solid #F0F0F0', borderRadius: '12px', padding: '16px 18px' }}>
            {req.is_founding && (
              <div className="security-error" style={{ background: 'var(--accent-light)', color: 'var(--accent-dark)', marginBottom: '12px' }}>
                New Organization Request — <strong>{req.organization_name}</strong> has no team yet, so this is
                reviewed here as the platform Super Admin rather than by a peer admin.
              </div>
            )}
            {req.request_kind === 'add_membership' && (
              <div className="security-error" style={{ background: 'var(--accent-light)', color: 'var(--accent-dark)', marginBottom: '12px' }}>
                Existing Account — {req.full_name} already has an EcoScholar login elsewhere and is asking to
                join your team too, not create a new account.
              </div>
            )}
            <div className="settings-row" style={{ marginBottom: '10px' }}>
              <div className="info-item">
                <span className="info-label">Full Name</span>
                <span className="info-value">{req.full_name}</span>
              </div>
              <div className="info-item">
                <span className="info-label">Email</span>
                <span className="info-value">{req.email}</span>
              </div>
              <div className="info-item">
                <span className="info-label">Contact Number</span>
                <span className="info-value">{req.contact_number}</span>
              </div>
              <div className="info-item">
                <span className="info-label">Municipality</span>
                <span className="info-value">{req.municipality}</span>
              </div>
              <div className="info-item">
                <span className="info-label">Submitted</span>
                <span className="info-value">{req.created_at}</span>
              </div>
              <div className="info-item">
                <span className="info-label">ID / Proof of Employment</span>
                {req.proof_of_employment_filename ? (
                  <button className="btn-change" disabled={openingProofId === req.id} onClick={() => handleViewProof(req)}>
                    {openingProofId === req.id ? 'Opening...' : 'View Document'}
                  </button>
                ) : (
                  <span className="info-value" style={{ color: '#991b1b' }}>None on file</span>
                )}
              </div>
            </div>
            {req.message && (
              <div className="info-item" style={{ marginBottom: '12px' }}>
                <span className="info-label">Reason for Request</span>
                <span className="info-sub" style={{ fontStyle: 'italic' }}>"{req.message}"</span>
              </div>
            )}

            {req.is_founding ? (
              <div style={{ display: 'flex', gap: '8px' }}>
                <button className="btn-primary" onClick={() => handleFoundingApproval(req)} disabled={actioningId === req.id}>
                  {actioningId === req.id ? 'Working...' : 'Approve New Organization'}
                </button>
                <button className="btn-danger-outline" onClick={() => handleReject(req)} disabled={actioningId === req.id}>
                  Reject
                </button>
              </div>
            ) : approvingId === req.id ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <span className="info-label">Grant permissions</span>
                <div style={{ display: 'flex', gap: '18px', flexWrap: 'wrap' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12.5px', color: 'var(--text-secondary, #4b5563)' }}>
                    <input type="checkbox" checked={pendingPermissions.can_review_applicants}
                      onChange={e => setPendingPermissions(p => ({ ...p, can_review_applicants: e.target.checked }))} />
                    Review applicants
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12.5px', color: 'var(--text-secondary, #4b5563)' }}>
                    <input type="checkbox" checked={pendingPermissions.can_manage_members}
                      onChange={e => setPendingPermissions(p => ({ ...p, can_manage_members: e.target.checked }))} />
                    Manage team members
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12.5px', color: 'var(--text-secondary, #4b5563)' }}>
                    <input type="checkbox" checked={pendingPermissions.can_reset_program}
                      onChange={e => setPendingPermissions(p => ({ ...p, can_reset_program: e.target.checked }))} />
                    Manage the program (settings, reset, form, guidelines)
                  </label>
                </div>
                {pendingPermissions.can_manage_members && (
                  <p className="info-sub" style={{ color: '#92400E' }}>
                    "Manage team members" lets this account invite, remove, and approve future admins - make sure
                    you trust whoever you're granting this to.
                  </p>
                )}
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button className="btn-primary" onClick={() => confirmApproval(req)} disabled={actioningId === req.id}>
                    {actioningId === req.id ? 'Working...' : 'Confirm Approval'}
                  </button>
                  <button className="btn-change" onClick={() => setApprovingId('')} disabled={actioningId === req.id}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', gap: '8px' }}>
                <button className="btn-primary" onClick={() => startApproval(req)} disabled={actioningId === req.id}>
                  Approve
                </button>
                <button className="btn-danger-outline" onClick={() => handleReject(req)} disabled={actioningId === req.id}>
                  Reject
                </button>
              </div>
            )}
          </div>
          )
        })}
      </div>
    </div>
  )
}

const EMPTY_TEAM_FORM = {
  full_name: '', email: '',
  permissions: { can_review_applicants: false, can_manage_members: false, can_reset_program: false },
}

// ── TEAM TAB ──
function JoinCodeCard() {
  const [org, setOrg] = useState(null)
  const [loadError, setLoadError] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    apiFetch('/api/organizations/mine')
      .then(async res => {
        if (!res.ok) { setLoadError(true); return }
        const data = await res.json()
        setOrg(data.organization)
      })
      .catch(() => setLoadError(true))
  }, [])

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(org.join_code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard access can be denied - the code is still shown on screen either way.
    }
  }

  if (loadError || !org) return null

  return (
    <div className="settings-card" style={{ marginBottom: '20px' }}>
      <h4 className="card-label" style={{ marginBottom: '4px' }}>Your LGU's Join Code</h4>
      <p className="info-sub" style={{ marginBottom: '14px' }}>
        Share this with anyone who needs to register a student account or apply for admin access
        under <strong>{org.name}</strong> - they'll enter it before filling out the rest of their form.
      </p>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span style={{
          fontFamily: 'monospace', fontSize: '20px', fontWeight: 700, letterSpacing: '2px',
          background: '#F9FAFB', border: '1px solid #E5E7EB', borderRadius: '8px', padding: '8px 16px',
        }}>
          {org.join_code}
        </span>
        <button className="btn-change" onClick={handleCopy}>{copied ? 'Copied!' : 'Copy'}</button>
      </div>
    </div>
  )
}

function TeamTab() {
  const currentUser = getUser() || {}
  const canPassAdminRole = isFullAccess(currentUser)
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
  const [transferringId, setTransferringId] = useState(null)

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
      setFormError(connectionErrorMessage())
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
        body: JSON.stringify({ permissions: nextPermissions })
      })
      const data = await res.json()
      if (!res.ok) { setPermissionsError(data.error || 'Failed to update permissions'); return }
      setAdmins(prev => prev.map(a => a.id === admin.id ? data.admin : a))
    } catch {
      setPermissionsError(connectionErrorMessage())
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
      alert(connectionErrorMessage())
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
      alert(connectionErrorMessage())
    } finally {
      setRemovingId(null)
    }
  }

  const handleTransferAdmin = async (admin) => {
    if (!window.confirm(
      `Pass the Admin role to ${admin.full_name} (${admin.email})?\n\n` +
      `This is a significant change: whoever currently holds Admin will be switched ` +
      `back to a plain LGU Member with no permissions, and ${admin.full_name} will get ` +
      `full control of this LGU's account (manage members, review applicants, and ` +
      `reset the program). This can be undone later the same way, but not automatically.`
    )) return
    setTransferringId(admin.id)
    try {
      const res = await apiFetch(`/api/admins/${admin.id}/transfer-admin`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) { alert(data.error || 'Failed to pass on the Admin role'); return }
      await loadAdmins()
    } catch {
      alert(connectionErrorMessage())
    } finally {
      setTransferringId(null)
    }
  }

  return (
    <div className="tab-content">
      <JoinCodeCard />
      <AdminRequestsSection onApproved={loadAdmins} />
      <div className="settings-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <h4 className="card-label" style={{ marginBottom: 0 }}>Admin Accounts</h4>
          {!showForm && (
            <button className="btn-primary" onClick={() => setShowForm(true)}>+ Add Admin</button>
          )}
        </div>
        <p className="info-sub" style={{ marginBottom: '14px' }}>
          New accounts are added as LGU Members with the permissions you choose below.
          Exactly one member holds the Admin seat (full access) at a time - see their row
          below to pass it on.
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
              <label>Permissions</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 400, fontSize: '13.5px', marginBottom: '6px' }}>
                <input
                  type="checkbox"
                  checked={form.permissions.can_review_applicants}
                  onChange={e => setForm(p => ({ ...p, permissions: { ...p.permissions, can_review_applicants: e.target.checked } }))}
                />
                Review applicants (view/decide applications, ranking, reports)
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 400, fontSize: '13.5px', marginBottom: '6px' }}>
                <input
                  type="checkbox"
                  checked={form.permissions.can_manage_members}
                  onChange={e => setForm(p => ({ ...p, permissions: { ...p.permissions, can_manage_members: e.target.checked } }))}
                />
                Manage team members (add/remove, approve admin requests)
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 400, fontSize: '13.5px' }}>
                <input
                  type="checkbox"
                  checked={form.permissions.can_reset_program}
                  onChange={e => setForm(p => ({ ...p, permissions: { ...p.permissions, can_reset_program: e.target.checked } }))}
                />
                Manage the program (applicant limit, result visibility, reset/start it, application form, and guidelines)
              </label>
            </div>

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
              const isAdminSeat = admin.role === 'lgu_admin'
              return (
              <div key={admin.id} className="info-item" style={{ flexDirection: 'column', alignItems: 'stretch', padding: '12px 0', borderBottom: '1px solid #F0F0F0', gap: '8px', minWidth: 0, width: '100%' }}>
                <div className="team-row">
                  <div className="team-row-info">
                    <span className="info-value" style={{ display: 'inline-flex', flexWrap: 'wrap', alignItems: 'center', gap: '0 4px' }}>
                      {admin.full_name} {admin.id === currentUser.id && <span className="badge badge-purple" style={{ marginLeft: '8px' }}>You</span>}
                      <span className="badge" style={{ marginLeft: '8px', background: isAdminSeat ? 'var(--accent-light)' : '#E0F2FE', color: isAdminSeat ? 'var(--accent-dark)' : '#075985' }}>
                        {isAdminSeat ? 'Admin' : 'LGU Member'}
                      </span>
                      {!admin.password_set && <span className="badge" style={{ marginLeft: '8px', background: '#FEF3C7', color: '#92400E' }}>Setup pending</span>}
                    </span>
                    <span className="info-sub" style={{ display: 'block' }}>{admin.email}</span>
                    {admin.municipality && (
                      <span className="info-sub" style={{ display: 'block' }}>{admin.municipality}</span>
                    )}
                  </div>
                  <div className="team-row-actions">
                    {!admin.password_set && (
                      <button
                        className="btn-change"
                        onClick={() => handleResendInvite(admin)}
                        disabled={resendingId === admin.id}>
                        {resendingId === admin.id ? 'Sending...' : 'Resend Invite'}
                      </button>
                    )}
                    {!isAdminSeat && canPassAdminRole && admin.id !== currentUser.id && (
                      <button
                        className="btn-change"
                        onClick={() => handleTransferAdmin(admin)}
                        disabled={transferringId === admin.id}>
                        {transferringId === admin.id ? 'Passing role...' : 'Pass Admin Role'}
                      </button>
                    )}
                    {admin.id !== currentUser.id && !isAdminSeat && (
                      <button
                        className="btn-danger-outline"
                        onClick={() => handleRemove(admin)}
                        disabled={removingId === admin.id}>
                        {removingId === admin.id ? 'Removing...' : 'Remove'}
                      </button>
                    )}
                  </div>
                </div>
                {isAdminSeat ? (
                  <p className="info-sub" style={{ paddingLeft: '2px' }}>
                    Holds the Admin seat: full access to review applicants, manage the
                    team, and reset the program. Use "Pass Admin Role" on another
                    member's row to hand it off - this account can't be removed while
                    it holds the seat.
                  </p>
                ) : (
                  <div style={{ display: 'flex', gap: '18px', paddingLeft: '2px', flexWrap: 'wrap' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12.5px', color: 'var(--text-secondary, #4b5563)' }}>
                      <input
                        type="checkbox"
                        checked={admin.permissions.can_review_applicants}
                        disabled={admin.id === currentUser.id || savingPermissionsId === admin.id}
                        onChange={() => handleTogglePermission(admin, 'can_review_applicants')}
                      />
                      Review applicants
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12.5px', color: 'var(--text-secondary, #4b5563)' }}>
                      <input
                        type="checkbox"
                        checked={admin.permissions.can_manage_members}
                        disabled={admin.id === currentUser.id || savingPermissionsId === admin.id}
                        onChange={() => handleTogglePermission(admin, 'can_manage_members')}
                      />
                      Manage team members
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12.5px', color: 'var(--text-secondary, #4b5563)' }}>
                      <input
                        type="checkbox"
                        checked={admin.permissions.can_reset_program}
                        disabled={admin.id === currentUser.id || savingPermissionsId === admin.id}
                        onChange={() => handleTogglePermission(admin, 'can_reset_program')}
                      />
                      Manage program (settings, reset, form, guidelines)
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
  const canManageMembers = isFullAccess(currentUser) || !!currentUser.permissions?.can_manage_members

  // System (eligibility/reset/export settings) is Super Admin + Admin only. Profile (which
  // includes Security) and Team are available to everyone: Team always shows the guide, and
  // its team-management part only to those with can_manage_members.
  const tabs = ALL_TABS.filter(tab =>
    tab !== 'System' || isFullAccess(currentUser) || !!currentUser.permissions?.can_reset_program
  )

  return (
    <div className="settings-page page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>
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

      <Reveal key={activeTab}>
        {activeTab === 'Profile' && (
          <div className="tab-content">
            <ProfileTab />
            <h3 className="settings-section-title">Security</h3>
            <SecurityTab />
          </div>
        )}
        {activeTab === 'System' && <SystemTab />}
        {activeTab === 'Team' && (
          <div className="tab-content">
            {canManageMembers && <TeamTab />}
            <h3 className="settings-section-title">How EcoScholar Works</h3>
            <AdminGuide />
          </div>
        )}
        {activeTab === 'Credits' && <Credits />}
      </Reveal>
    </div>
  )
}

export default Settings
