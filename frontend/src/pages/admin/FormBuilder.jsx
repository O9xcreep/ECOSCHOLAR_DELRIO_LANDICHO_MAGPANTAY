import { useState, useEffect } from 'react'
import { apiFetch } from '../../api'
import './FormBuilder.css'

const FIELD_TYPES = ['text', 'textarea', 'number', 'date', 'select', 'checkbox']
const SECTIONS = [
  { key: 'personal', label: 'Personal Information (Step 1)' },
  { key: 'school', label: 'School Information (Step 2)' },
]

const EMPTY_NEW_FIELD = {
  key: '', label: '', type: 'text', options: '', required: false, section: 'personal',
}

function FormBuilder() {
  const [fields, setFields] = useState([])
  const [hiddenBuiltins, setHiddenBuiltins] = useState([])
  const [hideableBuiltins, setHideableBuiltins] = useState({})
  const [loading, setLoading] = useState(true)
  const [showAddForm, setShowAddForm] = useState(false)
  const [newField, setNewField] = useState(EMPTY_NEW_FIELD)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const fetchFields = async () => {
    try {
      const res = await apiFetch('/api/form-fields')
      const data = await res.json()
      setFields(data.fields || [])
      setHiddenBuiltins(data.hidden_builtin_fields || [])
      setHideableBuiltins(data.hideable_builtin_fields || {})
    } catch (err) {
      console.error('Error:', err)
    }
    setLoading(false)
  }

  useEffect(() => { fetchFields() }, [])

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
    await apiFetch(`/api/form-fields/${field.id}`, { method: 'DELETE' })
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
          options: newField.type === 'select'
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
      setError('Cannot connect to server. Please try again.')
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
                />
                <span className="slider" />
              </label>
            </div>
          ))}
        </div>
      </div>

      {/* Custom fields per section */}
      {SECTIONS.map(section => (
        <div key={section.key} className="fb-card">
          <h3 className="fb-card-title">{section.label}</h3>
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
                      {field.type}{field.type === 'select' && field.options.length > 0
                        ? ` · ${field.options.join(', ')}` : ''}
                    </p>
                  </div>
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={field.enabled}
                      onChange={() => toggleFieldEnabled(field)}
                    />
                    <span className="slider" />
                  </label>
                  <button className="fb-btn-delete" onClick={() => deleteField(field)}>Delete</button>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {/* Add new field */}
      <div className="fb-card">
        {!showAddForm ? (
          <button className="fb-btn-add" onClick={() => setShowAddForm(true)}>
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
                  placeholder="e.g. facebook_account"
                  value={newField.key}
                  onChange={e => setNewField(p => ({ ...p, key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') }))}
                />
                <span className="fb-hint">Lowercase, letters/numbers/underscores only</span>
              </div>

              <div className="fb-form-field">
                <label>Label (shown to applicants)</label>
                <input
                  type="text"
                  placeholder="e.g. Facebook Account Name"
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

              {newField.type === 'select' && (
                <div className="fb-form-field fb-form-field-wide">
                  <label>Options (comma-separated)</label>
                  <input
                    type="text"
                    placeholder="e.g. Yes, No, Not Applicable"
                    value={newField.options}
                    onChange={e => setNewField(p => ({ ...p, options: e.target.value }))}
                  />
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
    </div>
  )
}

export default FormBuilder
