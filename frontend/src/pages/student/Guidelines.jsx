import { useState, useEffect } from 'react'
import { apiFetch } from '../../api'
import Reveal from '../../components/Reveal'
import pageBg from '../../assets/bg2.jpg'
import './Guidelines.css'

function Guidelines() {
  const [html, setHtml] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)

  const load = () => {
    setLoading(true)
    setLoadError(false)
    apiFetch('/api/guidelines')
      .then(res => { if (!res.ok) throw new Error(); return res.json() })
      .then(data => setHtml(data.html || ''))
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  return (
    <div className="guidelines-page page-bg" style={{ '--page-bg-image': `url(${pageBg})` }}>

      {/* Header */}
      <div className="gl-header">
        <h2 className="page-title">Application Guidelines</h2>
        <p className="page-sub">
          Please read the rules and instructions carefully before submitting.
        </p>
      </div>

      <Reveal className="gl-card">
        {loading ? (
          <p className="info-sub">Loading guidelines...</p>
        ) : loadError ? (
          <div>
            <p className="info-sub" style={{ marginBottom: '10px' }}>Couldn't load guidelines. Check your connection and try again.</p>
            <button className="btn-retry" onClick={load}>Retry</button>
          </div>
        ) : (
          <div className="gl-html-content" dangerouslySetInnerHTML={{ __html: html }} />
        )}
      </Reveal>

    </div>
  )
}

export default Guidelines
