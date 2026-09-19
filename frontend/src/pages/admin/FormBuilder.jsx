import { useState, useEffect } from 'react'
import { apiFetch, connectionErrorMessage } from '../../api'
import './FormBuilder.css'

const FIELD_TYPES = ['text', 'textarea', 'number', 'date', 'select', 'checkbox']
const SECTIONS = [
  { key: 'personal', label: 'Personal Information (Step 1)' },
  { key: 'school', label: 'School Information (Step 2)' },
]

// Always on the form for every LGU - these can't be hidden or removed here because
// they're either core record-keeping fields or read directly by the eligibility
// model's build_feature_row(). Shown so admins can see the whole form, not just
// what they've customized.
const CORE_FIELDS = {
  personal: [
    { label: 'Full Name', usedByModel: false },
    { label: 'Email Address', usedByModel: false },
    { label: 'Address', usedByModel: false },
    { label: 'Gender', usedByModel: true },
    { label: 'Date of Birth', usedByModel: false },
    { label: 'Contact Number', usedByModel: false },
    { label: "Father's Name", usedByModel: false },
    { label: "Father's Occupation", usedByModel: true },
    { label: "Father's Education Level", usedByModel: true },
    { label: "Mother's Name", usedByModel: false },
    { label: "Mother's Occupation", usedByModel: true },
    { label: "Mother's Education Level", usedByModel: true },
    { label: 'Monthly Household Income', usedByModel: true },
    { label: 'Housing Situation', usedByModel: true },
    { label: 'Family Size', usedByModel: true },
    { label: 'Number of Siblings', usedByModel: true },
    { label: 'Siblings Currently Studying', usedByModel: true },
    { label: 'Other Scholarship Status', usedByModel: false },
  ],
  school: [
    { label: 'College / University', usedByModel: false },
    { label: 'School Address', usedByModel: false },
    { label: 'Course', usedByModel: false },
    { label: 'Year Level', usedByModel: false },
    { label: 'GWA', usedByModel: true },
    { label: 'Academic Year', usedByModel: false },
    { label: 'Semester', usedByModel: false },
  ],
}

const EMPTY_NEW_FIELD = {
  key: '', label: '', type: 'text', options: '', required: false, section: 'personal',
}

const EMPTY_NEW_DOC = { label: '', required: true }

function FormBuilder() {
  const [fields, setFields] = useState([])
  const [hiddenBuiltins, setHiddenBuiltins] = useState([])
  const [hideableBuiltins, setHideableBuiltins] = useState({})
  const [loading, setLoading] = useState(true)
  const [showAddForm, setShowAddForm] = useState(false)
  const [newField, setNewField] = useState(EMPTY_NEW_FIELD)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const [docRequirements, setDocRequirements] = useState([])
  const [showAddDoc, setShowAddDoc] = useState(false)
  const [newDoc, setNewDoc] = useState(EMPTY_NEW_DOC)
  const [docError, setDocError] = useState('')
  const [savingDoc, setSavingDoc] = useState(false)

  // The form can only be edited before a program starts or after it ends -
  // changing what's expected of applicants mid-program would silently
  // invalidate submissions already in flight. See form_is_locked() in app.py.
  const [formLocked, setFormLocked] = useState(false)

  const fetchDocRequirements = async () => {
    try {
      const res = await apiFetch('/api/document-requirements')
      const data = await res.json()
      setDocRequirements(data.requirements || [])
    } catch (err) {
      console.error('Error:', err)
    }
  }

  const toggleDocEnabled = async (doc) => {
    setDocRequirements(prev => prev.map(d => d.id === doc.id ? { ...d, enabled: !d.enabled } : d))
    await apiFetch(`/api/document-requirements/${doc.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !doc.enabled })
    })
  }

  const toggleDocRequired = async (doc) => {
    setDocRequirements(prev => prev.map(d => d.id === doc.id ? { ...d, required: !d.required } : d))
    await apiFetch(`/api/document-requirements/${doc.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ required: !doc.required })
    })
  }

  const deleteDocRequirement = async (doc) => {
    if (!window.confirm(`Delete the "${doc.label}" document requirement? Applicants who already uploaded it will keep the file, but it will no longer appear on the checklist.`)) return
    const res = await apiFetch(`/api/document-requirements/${doc.id}`, { method: 'DELETE' })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      alert(data.error || 'Failed to delete document requirement')
      return
    }
    setDocRequirements(prev => prev.filter(d => d.id !== doc.id))
  }

  const handleAddDoc = async () => {
    setDocError('')
    if (!newDoc.label.trim()) {
      setDocError('Label is required')
      return
    }
    setSavingDoc(true)
    try {
      const res = await apiFetch('/api/document-requirements', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: newDoc.label.trim(), required: newDoc.required })
      })
      const data = await res.json()
      if (!res.ok) {
        setDocError(data.error || 'Failed to add document requirement')
        return
      }
      setDocRequirements(prev => [...prev, data.requirement])
      setNewDoc(EMPTY_NEW_DOC)
      setShowAddDoc(false)
    } catch {
      setDocError(connectionErrorMessage())
    } finally {
      setSavingDoc(false)
    }
  }

  const fetchFields = async () => {
    try {
      const res = await apiFetch('/api/form-fields')
      const data = await res.json()
      setFields(data.fields || [])
      setHiddenBuiltins(data.hidden_builtin_fields || [])
      setHideableBuiltins(data.hideable_builtin_fields || {})
      await fetchDocRequirements()
    } catch (err) {
      console.error('Error:', err)
    }
    setLoading(false)
  }

  const fetchLockStatus = async () => {
    try {
      const res = await apiFetch('/api/settings')
      if (!res.ok) return
      const data = await res.json()
      setFormLocked(!!data.current_cycle?.is_open)
    } catch (err) {
      console.error('Error:', err)
    }
  }

  useEffect(() => { fetchFields(); fetchLockStatus() }, [])

  const toggleBuiltin = async (key) => {
    const next = hiddenBuiltins.includes(key)
      ? hiddenBuiltins.filter(k => k !== key)
      : [...hiddenBuiltins, key]
    setHiddenBuiltins(next)
    await apiFetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hidden_builtin_fields: next })
    })
  }

  const toggleFieldEnabled = async (field) => {
    setFields(prev => prev.map(f => f.id === field.id ? { ...f, enabled: !f.enabled } : f))
    await apiFetch(`/api/form-fields/${field.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !field.enabled })
    })
  }

  const deleteField = async (field) => {
    if (!window.confirm(`Delete the "${field.label}" field? Existing applicants who filled it in will keep that data, but it will no longer appear on the form.`)) return
    const res = await apiFetch(`/api/form-fields/${field.id}`, { method: 'DELETE' })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      alert(data.error || 'Failed to delete field')
      return
    }
    setFields(prev => prev.filter(f => f.id !== field.id))
  }

  const handleAddField = async () => {
    setError('')
    if (!newField.key.trim() || !newField.label.trim()) {
      setError('Key and label are required')
      return
    }
    setSaving(true)
    try {
      const res = await apiFetch('/api/form-fields', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          key: newField.key.trim(),
          label: newField.label.trim(),
          type: newField.type,
          section: newField.section,
          required: newField.required,
          options: (newField.type === 'select' || newField.type === 'checkbox')
            ? newField.options.split(',').map(o => o.trim()).filter(Boolean)
            : []
        })
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.error || 'Failed to add field')
        return
      }
      setFields(prev => [...prev, data.field])
      setNewField(EMPTY_NEW_FIELD)
      setShowAddForm(false)
    } catch {
      setError(connectionErrorMessage())
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="fb-loading">Loading form configuration...</div>
  }

  return (
    <div className="fb-page">
      <div className="fb-header">
        <div>
          <h2 className="page-title">Form Builder</h2>
          <p className="page-sub">
            Customize the scholarship application form for this LGU. Custom fields are
            purely informational - they're stored and shown to admins, but never used by
            the eligibility model, so adding fields here can never introduce bias into
            scoring.
          </p>
        </div>
      </div>

      {formLocked && (
        <div className="fb-locked-banner">
          This form is locked while a program is open. It can be edited again once
          the current program ends.
        </div>
      )}

      {/* Built-in optional fields */}
      <div className="fb-card">
        <h3 className="fb-card-title">Optional Built-in Fields</h3>
        <p className="fb-card-sub">
          These fields already exist on the form and aren't used by the eligibility model,
          so they're safe to hide if this LGU doesn't need them.
        </p>
        <div className="fb-builtin-list">
          {Object.entries(hideableBuiltins).map(([key, label]) => (
            <div key={key} className="fb-builtin-row">
              <span>{label}</span>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={!hiddenBuiltins.includes(key)}
                  onChange={() => toggleBuiltin(key)}
                  disabled={formLocked}
                />
                <span className="slider" />
              </label>
            </div>
          ))}
        </div>
      </div>

      {/* Core + custom fields per section */}
      {SECTIONS.map(section => (
        <div key={section.key} className="fb-card">
          <h3 className="fb-card-title">{section.label}</h3>

          <p className="fb-subheading">Core Fields (always shown)</p>
          <div className="fb-field-list fb-field-list-core">
            {CORE_FIELDS[section.key].map(f => (
              <div key={f.label} className="fb-field-row fb-field-row-core">
                <div className="fb-field-info">
                  <p className="fb-field-label">{f.label}</p>
                </div>
                {f.usedByModel && <span className="fb-model-tag">Used by eligibility model</span>}
                <span className="fb-locked-tag">Locked</span>
              </div>
            ))}
          </div>

          <p className="fb-subheading">Custom Fields</p>
          {fields.filter(f => f.section === section.key).length === 0 ? (
            <p className="fb-empty">No custom fields added yet.</p>
          ) : (
            <div className="fb-field-list">
              {fields.filter(f => f.section === section.key).map(field => (
                <div key={field.id} className="fb-field-row">
                  <div className="fb-field-info">
                    <p className="fb-field-label">
                      {field.label}
                      {field.required && <span className="fb-required-star"> *</span>}
                    </p>
                    <p className="fb-field-meta">
                      {field.type}{(field.type === 'select' || field.type === 'checkbox') && field.options.length > 0
                        ? ` · ${field.options.join(', ')}` : ''}
                    </p>
                  </div>
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={field.enabled}
                      onChange={() => toggleFieldEnabled(field)}
                      disabled={formLocked}
                    />
                    <span className="slider" />
                  </label>
                  <button className="fb-btn-delete" onClick={() => deleteField(field)} disabled={formLocked}>Delete</button>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {/* Add new field */}
      <div className="fb-card">
        {!showAddForm ? (
          <button className="fb-btn-add" onClick={() => setShowAddForm(true)} disabled={formLocked}>
            + Add Custom Field
          </button>
        ) : (
          <div className="fb-add-form">
            <h3 className="fb-card-title">New Custom Field</h3>
            {error && <div className="fb-error">{error}</div>}

            <div className="fb-form-grid">
              <div className="fb-form-field">
                <label>Field Key</label>
                <input
                  type="text"
                  placeholder="Enter field key"
                  value={newField.key}
                  onChange={e => setNewField(p => ({ ...p, key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') }))}
                />
                <span className="fb-hint">Lowercase, letters/numbers/underscores only</span>
              </div>

              <div className="fb-form-field">
                <label>Label (shown to applicants)</label>
                <input
                  type="text"
                  placeholder="Enter Label"
                  value={newField.label}
                  onChange={e => setNewField(p => ({ ...p, label: e.target.value }))}
                />
              </div>

              <div className="fb-form-field">
                <label>Field Type</label>
                <select
                  value={newField.type}
                  onChange={e => setNewField(p => ({ ...p, type: e.target.value }))}>
                  {FIELD_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>

              <div className="fb-form-field">
                <label>Section</label>
                <select
                  value={newField.section}
                  onChange={e => setNewField(p => ({ ...p, section: e.target.value }))}>
                  {SECTIONS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
                </select>
              </div>

              {(newField.type === 'select' || newField.type === 'checkbox') && (
                <div className="fb-form-field fb-form-field-wide">
                  <label>Options (comma-separated)</label>
                  <input
                    type="text"
                    placeholder="Yes, No, Not Applicable"
                    value={newField.options}
                    onChange={e => setNewField(p => ({ ...p, options: e.target.value }))}
                  />
                  {newField.type === 'checkbox' && (
                    <span className="fb-hint">
                      Leave blank for a simple Yes/No checkbox, or list options to let
                      applicants select multiple (e.g. a checklist)
                    </span>
                  )}
                </div>
              )}

              <div className="fb-form-field">
                <label className="fb-checkbox-label">
                  <input
                    type="checkbox"
                    checked={newField.required}
                    onChange={e => setNewField(p => ({ ...p, required: e.target.checked }))}
                  />
                  Required field
                </label>
              </div>
            </div>

            <div className="fb-form-actions">
              <button className="fb-btn-cancel" onClick={() => { setShowAddForm(false); setNewField(EMPTY_NEW_FIELD); setError('') }}>
                Cancel
              </button>
              <button className="fb-btn-add" onClick={handleAddField} disabled={saving}>
                {saving ? 'Adding...' : 'Add Field'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Document requirements */}
      <div className="fb-card">
        <h3 className="fb-card-title">Document Requirements</h3>
        <p className="fb-card-sub">
          Which documents applicants must upload in Step 3. Disabling one hides it from the
          checklist entirely; unchecking "Required" keeps it visible but optional. These
          never feed the eligibility model either - documents only affect verification, not
          scoring.
        </p>
        {docRequirements.length === 0 ? (
          <p className="fb-empty">No document requirements configured.</p>
        ) : (
          <div className="fb-field-list">
            {docRequirements.map(doc => (
              <div key={doc.id} className="fb-field-row fb-doc-row">
                <div className="fb-field-info">
                  <p className="fb-field-label">
                    {doc.label}
                    {doc.required && <span className="fb-required-star"> *</span>}
                  </p>
                  <div className="fb-doc-controls">
                    <label className="fb-checkbox-label fb-required-toggle">
                      <input
                        type="checkbox"
                        checked={doc.required}
                        onChange={() => toggleDocRequired(doc)}
                        disabled={formLocked}
                      />
                      Required
                    </label>
                    <label className="toggle toggle-inline">
                      <input
                        type="checkbox"
                        checked={doc.enabled}
                        onChange={() => toggleDocEnabled(doc)}
                        disabled={formLocked}
                      />
                      <span className="slider" />
                    </label>
                  </div>
                </div>
                <div className="fb-doc-actions">
                  {doc.is_default ? (
                    <span className="fb-locked-tag" title="Default document requirements can't be deleted - disable it or uncheck &quot;Required&quot; instead.">Default</span>
                  ) : (
                    <button className="fb-btn-delete" onClick={() => deleteDocRequirement(doc)} disabled={formLocked}>Delete</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {!showAddDoc ? (
          <button className="fb-btn-add fb-btn-add-doc" onClick={() => setShowAddDoc(true)} disabled={formLocked}>
            + Add Document Requirement
          </button>
        ) : (
          <div className="fb-add-form fb-add-doc-form">
            {docError && <div className="fb-error">{docError}</div>}
            <div className="fb-form-grid">
              <div className="fb-form-field">
                <label>Document Label</label>
                <input
                  type="text"
                  placeholder="Certificate of Good Moral Character"
                  value={newDoc.label}
                  onChange={e => setNewDoc(p => ({ ...p, label: e.target.value }))}
                />
              </div>
              <div className="fb-form-field">
                <label className="fb-checkbox-label">
                  <input
                    type="checkbox"
                    checked={newDoc.required}
                    onChange={e => setNewDoc(p => ({ ...p, required: e.target.checked }))}
                  />
                  Required
                </label>
              </div>
            </div>
            <div className="fb-form-actions">
              <button className="fb-btn-cancel" onClick={() => { setShowAddDoc(false); setNewDoc(EMPTY_NEW_DOC); setDocError('') }}>
                Cancel
              </button>
              <button className="fb-btn-add" onClick={handleAddDoc} disabled={savingDoc}>
                {savingDoc ? 'Adding...' : 'Add Document'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default FormBuilder
