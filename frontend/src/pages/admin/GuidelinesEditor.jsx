import { useState, useEffect, useRef, useCallback } from 'react'
import { apiFetch, connectionErrorMessage } from '../../api'
import './GuidelinesEditor.css'

// A dependency-free rich text editor: a contentEditable region driven by
// document.execCommand, the same technique browsers have supported natively
// for years - avoids pulling in a WYSIWYG library just for a handful of
// buttons (bold/italic/lists/headings/table/link) on one settings page.
const TOOLBAR = [
  { label: 'B', title: 'Bold', cmd: 'bold', style: { fontWeight: 700 } },
  { label: 'I', title: 'Italic', cmd: 'italic', style: { fontStyle: 'italic' } },
  { label: 'U', title: 'Underline', cmd: 'underline', style: { textDecoration: 'underline' } },
  { label: 'H2', title: 'Heading', cmd: 'formatBlock', arg: '<h2>' },
  { label: 'H3', title: 'Subheading', cmd: 'formatBlock', arg: '<h3>' },
  { label: 'P', title: 'Paragraph', cmd: 'formatBlock', arg: '<p>' },
  { label: '• List', title: 'Bullet list', cmd: 'insertUnorderedList' },
  { label: '1. List', title: 'Numbered list', cmd: 'insertOrderedList' },
  { label: '" Quote', title: 'Callout / quote', cmd: 'formatBlock', arg: '<blockquote>' },
]

function GuidelinesEditor() {
  const editorRef = useRef(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [saved, setSaved] = useState(false)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    apiFetch('/api/guidelines')
      .then(res => { if (!res.ok) throw new Error(); return res.json() })
      .then(data => {
        if (editorRef.current) editorRef.current.innerHTML = data.html || ''
      })
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false))
  }, [])

  const runCommand = (cmd, arg) => {
    editorRef.current?.focus()
    document.execCommand(cmd, false, arg)
    setDirty(true)
    setSaved(false)
  }

  const handleLink = () => {
    const url = window.prompt('Link URL (e.g. https://example.com or mailto:office@lgu.gov.ph)')
    if (url) runCommand('createLink', url)
  }

  const handleInsertTable = () => {
    const rows = parseInt(window.prompt('Number of rows?', '3'), 10)
    const cols = parseInt(window.prompt('Number of columns?', '3'), 10)
    if (!rows || !cols) return
    let html = '<table><tbody>'
    for (let r = 0; r < rows; r++) {
      html += '<tr>'
      for (let c = 0; c < cols; c++) html += r === 0 ? '<th>Header</th>' : '<td>Cell</td>'
      html += '</tr>'
    }
    html += '</tbody></table><p><br></p>'
    editorRef.current?.focus()
    document.execCommand('insertHTML', false, html)
    setDirty(true)
    setSaved(false)
  }

  const handleSave = useCallback(async () => {
    setSaving(true)
    setSaveError('')
    try {
      const html = editorRef.current?.innerHTML || ''
      const res = await apiFetch('/api/guidelines', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html })
      })
      const data = await res.json()
      if (!res.ok) { setSaveError(data.error || 'Failed to save guidelines'); return }
      setDirty(false)
      setSaved(true)
    } catch {
      setSaveError(connectionErrorMessage())
    } finally {
      setSaving(false)
    }
  }, [])

  return (
    <div className="ge-card">
      <h3 className="ge-card-title">Application Guidelines</h3>
      <p className="ge-card-sub">
        Shown to students on the Guidelines page. Edit the text directly below, then Save -
        no code or HTML knowledge needed.
      </p>

      {loadError && <div className="ge-error">Couldn't load the current guidelines. Try refreshing the page.</div>}
      {saveError && <div className="ge-error">{saveError}</div>}

      <div className="ge-toolbar">
        {TOOLBAR.map(btn => (
          <button
            key={btn.label}
            type="button"
            className="ge-tool-btn"
            style={btn.style}
            title={btn.title}
            onMouseDown={e => e.preventDefault()}
            onClick={() => runCommand(btn.cmd, btn.arg)}>
            {btn.label}
          </button>
        ))}
        <button type="button" className="ge-tool-btn" title="Insert link"
          onMouseDown={e => e.preventDefault()} onClick={handleLink}>Link</button>
        <button type="button" className="ge-tool-btn" title="Insert table"
          onMouseDown={e => e.preventDefault()} onClick={handleInsertTable}>Table</button>
      </div>

      {loading ? (
        <div className="ge-loading">Loading guidelines...</div>
      ) : (
        <div
          ref={editorRef}
          className="ge-editor"
          contentEditable
          suppressContentEditableWarning
          onInput={() => { setDirty(true); setSaved(false) }}
        />
      )}

      <div className="ge-footer">
        <button className="ge-btn-save" onClick={handleSave} disabled={saving || loading || !dirty}>
          {saving ? 'Saving...' : 'Save Guidelines'}
        </button>
        {saved && !dirty && <span className="ge-saved-msg">Saved</span>}
        {dirty && <span className="ge-dirty-msg">Unsaved changes</span>}
      </div>
    </div>
  )
}

export default GuidelinesEditor
