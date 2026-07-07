import { useState, useEffect } from 'react'
import { apiFetch, getUser } from '../../api'
import './Documents.css'

const DEFAULT_DOCS = [
  { id: 1, document_name: 'Copy of Enrollment Form', required: true, status: 'Missing', file: null },
  { id: 2, document_name: 'Copy of Barangay Endorsement', required: true, status: 'Missing', file: null },
  { id: 3, document_name: 'School ID', required: true, status: 'Missing', file: null },
  { id: 4, document_name: 'Grade 12 Grades', required: true, status: 'Missing', file: null },
  { id: 5, document_name: '4Ps Certificate', required: false, status: 'Not Required', file: null },
  { id: 6, document_name: 'Proof of Income (Certificate of Indigency)', required: true, status: 'Missing', file: null },
]

function Documents() {
  const [docs, setDocs] = useState(DEFAULT_DOCS)
  const [applicantId, setApplicantId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [dragOver, setDragOver] = useState(null)

  const user = getUser() || {}

  useEffect(() => {
    if (!user.email) { setLoading(false); return }

    apiFetch(`/api/student/application?email=${encodeURIComponent(user.email)}`)
      .then(res => res.json())
      .then(data => {
        if (data.application) {
          setApplicantId(data.application.id)

          if (data.documents && data.documents.length > 0) {
            // Merge real DB docs with default list
            const merged = DEFAULT_DOCS.map(defaultDoc => {
              const found = data.documents.find(d =>
                d.document_name?.toLowerCase().includes(
                  defaultDoc.document_name.toLowerCase().split(' ')[0]
                )
              )
              return found
                ? { ...defaultDoc, status: found.status }
                : defaultDoc
            })
            setDocs(merged)
          }
        }
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const uploaded = docs.filter(d => d.status === 'Uploaded').length
  const missing = docs.filter(d => d.status === 'Missing').length
  const total = docs.filter(d => d.required).length

  const handleUpload = async (id, file) => {
    if (!file) return

    // Update UI immediately
    setDocs(prev => prev.map(d =>
      d.id === id ? { ...d, file, status: 'Uploaded' } : d
    ))

    // Upload to server if we have applicant ID
    if (applicantId) {
      const doc = docs.find(d => d.id === id)
      const formData = new FormData()
      formData.append('file', file)
      formData.append('applicant_id', applicantId)
      formData.append('document_name', doc.document_name)

      try {
        const res = await apiFetch('/api/upload', {
          method: 'POST',
          body: formData
        })
        if (!res.ok) throw new Error('Upload failed')
      } catch (err) {
        console.error('Upload error:', err)
        setDocs(prev => prev.map(d =>
          d.id === id ? { ...d, file: null, status: d.required ? 'Missing' : 'Not Required' } : d
        ))
      }
    }
  }

  const handleRemove = (id) => {
    setDocs(prev => prev.map(d =>
      d.id === id
        ? { ...d, file: null, status: d.required ? 'Missing' : 'Not Required' }
        : d
    ))
  }

  const handleDrop = (id, e) => {
    e.preventDefault()
    setDragOver(null)
    const file = e.dataTransfer.files[0]
    if (file) handleUpload(id, file)
  }

  const getStatusClass = (status) => {
    if (status === 'Uploaded') return 'badge-uploaded'
    if (status === 'Missing') return 'badge-missing'
    return 'badge-not-required'
  }

  return (
    <div className="documents-page">

      {/* Header */}
      <div className="doc-header">
        <div>
          <h2 className="page-title">Documents</h2>
          <p className="page-sub">
            Upload and manage your required scholarship documents
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="doc-stats">
        <div className="doc-stat green">
          <div><h3>{uploaded}</h3><p>Uploaded</p></div>
        </div>
        <div className="doc-stat red">
          <div><h3>{missing}</h3><p>Missing</p></div>
        </div>
        <div className="doc-stat purple">
          <div><h3>{total}</h3><p>Total Required</p></div>
        </div>
        <div className="doc-stat blue">
          <div>
            <h3>{total > 0 ? Math.round((uploaded / total) * 100) : 0}%</h3>
            <p>Completion</p>
          </div>
        </div>
      </div>

      {/* Progress */}
      <div className="doc-progress-card">
        <div className="doc-progress-header">
          <span>Document Completion</span>
          <span className="doc-progress-count">
            {uploaded} of {total} required documents uploaded
          </span>
        </div>
        <div className="doc-progress-track">
          <div className="doc-progress-fill"
            style={{ width: `${total > 0 ? (uploaded / total) * 100 : 0}%` }} />
        </div>
      </div>

      {/* Documents List */}
      <div className="doc-list-card">
        <h3>Required Documents</h3>
        <p className="doc-list-sub">
          Accepted formats: PDF, JPG, PNG — Max size: 5MB per file
        </p>

        {loading ? (
          <div style={{ textAlign: 'center', padding: '40px', color: '#888' }}>
            Loading your documents...
          </div>
        ) : (
          <div className="doc-list">
            {docs.map(doc => (
              <div
                key={doc.id}
                className={`doc-item ${dragOver === doc.id ? 'drag-over' : ''}`}
                onDragOver={e => { e.preventDefault(); setDragOver(doc.id) }}
                onDragLeave={() => setDragOver(null)}
                onDrop={e => handleDrop(doc.id, e)}>

                <div className="doc-info">
                  <div>
                    <p className="doc-name">
                      {doc.document_name}
                      {doc.required && <span className="required-star"> *</span>}
                    </p>
                    {doc.file && (
                      <p className="doc-filename">{doc.file.name}</p>
                    )}
                    {doc.status === 'Uploaded' && !doc.file && (
                      <p className="doc-filename">Previously uploaded</p>
                    )}
                    {doc.status === 'Missing' && (
                      <p className="doc-hint">Drag & drop or click Upload</p>
                    )}
                    {doc.status === 'Not Required' && (
                      <p className="doc-hint">Only required for specific applicants</p>
                    )}
                  </div>
                </div>

                <div className="doc-actions">
                  <span className={`badge ${getStatusClass(doc.status)}`}>
                    {doc.status}
                  </span>
                  {doc.status === 'Uploaded' ? (
                    <button className="btn-remove" onClick={() => handleRemove(doc.id)}>
                      Remove
                    </button>
                  ) : (
                    <div>
                      <button className="btn-upload"
                        onClick={() => document.getElementById(`file-${doc.id}`).click()}>
                        Upload
                      </button>
                      <input
                        type="file"
                        id={`file-${doc.id}`}
                        style={{ display: 'none' }}
                        accept=".pdf,.jpg,.jpeg,.png"
                        onChange={e => handleUpload(doc.id, e.target.files[0])}
                      />
                    </div>
                  )}
                </div>

              </div>
            ))}
          </div>
        )}

        <div className="doc-note">
          <p>Fields marked with <strong>*</strong> are required. Make sure all required documents are uploaded before submitting.</p>
        </div>
      </div>

    </div>
  )
}

export default Documents