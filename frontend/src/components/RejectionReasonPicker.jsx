import { useState, useEffect } from 'react'
import { apiFetch, connectionErrorMessage } from '../api'

// Multiple-choice reasons for an application the eligibility model rejected. They
// explain the decision to the student; they don't change it.
function RejectionReasonPicker({ applicant, onSaved }) {
  const [choices, setChoices] = useState([])
  const [selected, setSelected] = useState(applicant.rejection_reasons || [])
  const [note, setNote] = useState(applicant.rejection_note || '')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    apiFetch('/api/rejection-reasons')
      .then(res => (res.ok ? res.json() : null))
      .then(data => { if (data) setChoices(data.reasons) })
      .catch(() => {})
  }, [])

  const toggle = reason => {
    setMessage('')
    setSelected(prev => prev.includes(reason) ? prev.filter(r => r !== reason) : [...prev, reason])
  }

  const save = async () => {
    setSaving(true)
    setMessage('')
    try {
      const res = await apiFetch(`/api/applications/${applicant.id}/rejection-reasons`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reasons: selected, note })
      })
      const data = await res.json().catch(() => ({}))
      setMessage(res.ok ? 'Reasons saved.' : data.error || 'Could not save the reasons')
      if (res.ok && onSaved) await onSaved()
    } catch {
      setMessage(connectionErrorMessage())
    } finally {
      setSaving(false)
    }
  }

  return (
    <fieldset className="rejection-reasons">
      <legend>Reasons for rejection (shown to the applicant)</legend>
      <div className="rejection-reasons-list">
        {choices.map(reason => (
          <label key={reason}>
            <input type="checkbox" checked={selected.includes(reason)} onChange={() => toggle(reason)} />
            <span>{reason}</span>
          </label>
        ))}
      </div>
      <div className="rejection-reasons-row">
        <input
          type="text"
          maxLength={300}
          placeholder="Other reason (optional)"
          aria-label="Other reason"
          value={note}
          onChange={e => { setNote(e.target.value); setMessage('') }}
        />
        <button type="button" className="btn-close-modal" onClick={save}
          disabled={saving || (selected.length === 0 && !note.trim())}>
          {saving ? 'Saving...' : 'Save Reasons'}
        </button>
      </div>
      {message && <p role="status">{message}</p>}
    </fieldset>
  )
}

export default RejectionReasonPicker
