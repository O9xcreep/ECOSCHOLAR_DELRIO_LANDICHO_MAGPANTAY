import { useState, useEffect, useRef } from 'react'
import { apiFetch, connectionErrorMessage } from '../../api'
import './FormBuilder.css'

// Friendly, Google Forms-style names for the backend field types.
const FIELD_TYPES = [
  { value: 'text', label: 'Short answer' },
  { value: 'textarea', label: 'Paragraph' },
  { value: 'number', label: 'Number' },
  { value: 'date', label: 'Date' },
  { value: 'select', label: 'Dropdown' },
  { value: 'checkbox', label: 'Checkboxes' },
]
const typeLabel = (type) => FIELD_TYPES.find(t => t.value === type)?.label || type
const hasOptions = (type) => type === 'select' || type === 'checkbox'
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

// Admins only type the question; the storage key is derived from it so they
// never have to think about snake_case identifiers.
function slugifyKey(label) {
  let key = label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40)
  if (!key) key = 'field'
  if (!/^[a-z]/.test(key)) key = `q_${key}`
  return key
}

function uniqueKey(label, takenKeys) {
  const base = slugifyKey(label)
  let key = base
  for (let n = 2; takenKeys.includes(key); n++) key = `${base}_${n}`
  return key
}

const emptyQuestion = (section) => ({
  label: '', type: 'text', options: [''], required: false, section,
})

// One Google Forms-style question card, used both for adding a new question
// and for editing an existing one (type can't change after creation since
// applicants may already have answered it).
function QuestionEditor({ initial, isNew, saving, error, onSave, onCancel }) {
  const [q, setQ] = useState(initial)
  const optionRefs = useRef([])
  // Option to focus after the next render (newly added or the one before a removed one).
  const pendingFocus = useRef(null)

  useEffect(() => {
    if (pendingFocus.current !== null) {
      optionRefs.current[pendingFocus.current]?.focus()
      pendingFocus.current = null
    }
  })
  const setFocusIndex = (i) => { pendingFocus.current = i }

  const setOption = (i, value) => setQ(p => ({ ...p, options: p.options.map((o, j) => j === i ? value : o) }))
  const addOption = (afterIndex) => {
    setQ(p => {
      const options = [...p.options]
      options.splice(afterIndex + 1, 0, '')
      return { ...p, options }
    })
    setFocusIndex(afterIndex + 1)
  }
  const removeOption = (i) => setQ(p => ({ ...p, options: p.options.filter((_, j) => j !== i) }))

  const handleOptionKey = (e, i) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addOption(i)
    } else if (e.key === 'Backspace' && q.options[i] === '' && q.options.length > 1) {
      e.preventDefault()
      removeOption(i)
      setFocusIndex(Math.max(0, i - 1))
    }
  }

  return (
    <div className="fb-q-card">
      {error && <div className="fb-error">{error}</div>}
      <div className="fb-q-top">
        <input
          className="fb-q-title"
          type="text"
          placeholder="Question"
          autoFocus
          value={q.label}
          onChange={e => setQ(p => ({ ...p, label: e.target.value }))}
          onKeyDown={e => { if (e.key === 'Enter' && !hasOptions(q.type)) onSave(q) }}
        />
        <select
          className="fb-q-type"
          value={q.type}
          disabled={!isNew}
          title={isNew ? '' : "The answer type can't be changed after the question is created"}
          onChange={e => setQ(p => ({ ...p, type: e.target.value }))}>
          {FIELD_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
      </div>

      <div className="fb-q-body">
        {q.type === 'text' && <div className="fb-q-preview-line">Short answer text</div>}
        {q.type === 'textarea' && <div className="fb-q-preview-line fb-q-preview-long">Long answer text</div>}
        {q.type === 'number' && <div className="fb-q-preview-line">Number</div>}
        {q.type === 'date' && <div className="fb-q-preview-line">mm / dd / yyyy</div>}

        {hasOptions(q.type) && (
          <div className="fb-q-options">
            {q.options.map((opt, i) => (
              <div key={i} className="fb-q-option">
                <span className={`fb-q-option-icon${q.type === 'checkbox' ? ' fb-q-option-icon-box' : ''}`}>
                  {q.type === 'select' ? `${i + 1}.` : ''}
                </span>
                <input
                  type="text"
                  placeholder={`Option ${i + 1}`}
                  value={opt}
                  ref={el => { optionRefs.current[i] = el }}
                  onChange={e => setOption(i, e.target.value)}
                  onKeyDown={e => handleOptionKey(e, i)}
                />
                {q.options.length > 1 && (
                  <button type="button" className="fb-q-option-remove" title="Remove option" onClick={() => removeOption(i)}>
                    &times;
                  </button>
                )}
              </div>
            ))}
            <div className="fb-q-option">
              <span className={`fb-q-option-icon${q.type === 'checkbox' ? ' fb-q-option-icon-box' : ''}`}>
                {q.type === 'select' ? `${q.options.length + 1}.` : ''}
              </span>
              <button type="button" className="fb-q-option-add" onClick={() => addOption(q.options.length - 1)}>
                Add option
              </button>
            </div>
            <span className="fb-hint">
              Tip: press Enter to add the next option.
              {q.type === 'checkbox' && ' Leave the options empty for a single Yes/No checkbox.'}
            </span>
          </div>
        )}
      </div>

      <div className="fb-q-footer">
        <label className="fb-q-required">
          Required
          <span className="toggle toggle-inline">
            <input
              type="checkbox"
              checked={q.required}
              onChange={e => setQ(p => ({ ...p, required: e.target.checked }))}
            />
            <span className="slider" />
          </span>
        </label>
        <div className="fb-q-footer-actions">
          <button type="button" className="fb-btn-cancel" onClick={onCancel}>Cancel</button>
          <button type="button" className="fb-btn-add" onClick={() => onSave(q)} disabled={saving}>
            {saving ? 'Saving...' : isNew ? 'Add question' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

const EMPTY_NEW_DOC = { label: '', required: true }

function FormBuilder() {
  const [fields, setFields] = useState([])
  const [hiddenBuiltins, setHiddenBuiltins] = useState([])
  const [hideableBuiltins, setHideableBuiltins] = useState({})
  const [loading, setLoading] = useState(true)
  // Which question card is open: { section, id }, where id is null for a new question.
  const [editing, setEditing] = useState(null)
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

  const openEditor = (section, id = null) => {
    if (formLocked) return
    setError('')
    setEditing({ section, id })
  }

  const closeEditor = () => {
    setEditing(null)
    setError('')
  }

  const saveQuestion = async (q) => {
    setError('')
    const label = q.label.trim()
    if (!label) {
      setError('Please enter the question')
      return
    }
    const options = hasOptions(q.type) ? q.options.map(o => o.trim()).filter(Boolean) : []
    if (q.type === 'select' && options.length === 0) {
      setError('Dropdown questions need at least one option')
      return
    }
    if (new Set(options.map(o => o.toLowerCase())).size !== options.length) {
      setError('Each option must be different')
      return
    }

    setSaving(true)
    try {
      if (editing.id) {
        const res = await apiFetch(`/api/form-fields/${editing.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label, required: q.required, ...(hasOptions(q.type) ? { options } : {}) })
        })
        const data = await res.json()
        if (!res.ok) {
          setError(data.error || 'Failed to save question')
          return
        }
        setFields(prev => prev.map(f => f.id === editing.id ? data.field : f))
      } else {
        const takenKeys = fields.map(f => f.key)
        const post = (key) => apiFetch('/api/form-fields', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key, label, type: q.type, section: q.section, required: q.required, options })
        })
        let res = await post(uniqueKey(label, takenKeys))
        let data = await res.json()
        // The generated key can collide with a built-in field name the
        // frontend doesn't know about - retry once under a custom_ prefix.
        if (!res.ok && /built-in/i.test(data.error || '')) {
          res = await post(uniqueKey(`custom ${label}`, takenKeys))
          data = await res.json()
        }
        if (!res.ok) {
          setError(data.error || 'Failed to add question')
          return
        }
        setFields(prev => [...prev, data.field])
      }
      setEditing(null)
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

          <details className="fb-core-details">
          <summary className="fb-subheading">
            Standard questions (always shown) · {CORE_FIELDS[section.key].length}
          </summary>
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
          </details>

          <p className="fb-subheading">Your Questions</p>
          {fields.filter(f => f.section === section.key).length === 0 && editing?.section !== section.key && (
            <p className="fb-empty">No custom questions yet.</p>
          )}
          <div className="fb-field-list">
            {fields.filter(f => f.section === section.key).map(field => (
              editing?.id === field.id ? (
                <QuestionEditor
                  key={field.id}
                  initial={{
                    label: field.label,
                    type: field.type,
                    options: field.options.length ? field.options : [''],
                    required: field.required,
                    section: field.section,
                  }}
                  isNew={false}
                  saving={saving}
                  error={error}
                  onSave={saveQuestion}
                  onCancel={closeEditor}
                />
              ) : (
                <div
                  key={field.id}
                  className={`fb-field-row${formLocked ? '' : ' fb-q-row-clickable'}${field.enabled ? '' : ' fb-q-row-hidden'}`}
                  onClick={() => openEditor(section.key, field.id)}
                  title={formLocked ? '' : 'Click to edit'}>
                  <div className="fb-field-info">
                    <p className="fb-field-label">
                      {field.label}
                      {field.required && <span className="fb-required-star"> *</span>}
                    </p>
                    <p className="fb-field-meta">
                      {typeLabel(field.type)}{hasOptions(field.type) && field.options.length > 0
                        ? ` · ${field.options.join(', ')}` : ''}
                    </p>
                  </div>
                  <label
                    className="toggle"
                    title={field.enabled ? 'Shown on the form' : 'Hidden from the form'}
                    onClick={e => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={field.enabled}
                      onChange={() => toggleFieldEnabled(field)}
                      disabled={formLocked}
                    />
                    <span className="slider" />
                  </label>
                  <button
                    className="fb-btn-delete"
                    onClick={e => { e.stopPropagation(); deleteField(field) }}
                    disabled={formLocked}>
                    Delete
                  </button>
                </div>
              )
            ))}

            {editing?.section === section.key && editing.id === null && (
              <QuestionEditor
                initial={emptyQuestion(section.key)}
                isNew
                saving={saving}
                error={error}
                onSave={saveQuestion}
                onCancel={closeEditor}
              />
            )}
          </div>

          {!(editing?.section === section.key && editing.id === null) && (
            <button
              className="fb-btn-add fb-btn-add-question"
              onClick={() => openEditor(section.key)}
              disabled={formLocked}>
              + Add question
            </button>
          )}
        </div>
      ))}

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
