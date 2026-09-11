import './Credits.css'

// Static, not admin-editable (unlike Guidelines) - this describes the platform
// itself, which is identical for every LGU, not something each org customizes.
// `logo` is a Simple Icons (simpleicons.org) slug, served as a colored SVG via
// their public CDN - https://cdn.simpleicons.org/<slug>. Left out for tools
// that don't have a brand mark there (a small library, an internal script);
// those fall back to a plain generic icon instead of a missing/broken image.
const CREDITS = [
  {
    group: 'Frontend',
    items: [
      { name: 'React 19 + React Router', desc: 'UI and page routing', logo: 'react' },
      { name: 'Vite', desc: 'Build tool and dev server', logo: 'vite' },
      { name: 'Recharts', desc: 'Dashboard charts and analytics', icon: 'chart' },
      { name: 'Framer Motion', desc: 'Page transitions and scroll animations', logo: 'framer' },
      { name: 'jsPDF + jsPDF-AutoTable', desc: 'Ranking and report PDF exports', icon: 'pdf' },
      { name: 'write-excel-file', desc: 'Applicant data Excel exports', icon: 'sheet' },
    ],
  },
  {
    group: 'Backend',
    items: [
      { name: 'Flask', desc: 'Web framework and REST API', logo: 'flask' },
      { name: 'MongoDB (via PyMongo)', desc: 'Database', logo: 'mongodb' },
      { name: 'scikit-learn + XGBoost', desc: 'The eligibility scoring model (Random Forest Regressor + XGBoost Classifier)', logo: 'scikitlearn' },
      { name: 'Tesseract OCR', desc: 'Document text extraction for admin verification (via pytesseract, pdf2image, Pillow)', icon: 'scan' },
      { name: 'ImageHash', desc: 'Perceptual hashing for duplicate-document detection', icon: 'fingerprint' },
      { name: 'Flask-Limiter', desc: 'API rate limiting', icon: 'gauge' },
    ],
  },
  {
    group: 'Infrastructure',
    items: [
      { name: 'Vercel', desc: 'Frontend hosting', logo: 'vercel' },
      { name: 'Render', desc: 'Backend hosting', logo: 'render' },
      { name: 'MongoDB Atlas', desc: 'Managed database hosting', logo: 'mongodb' },
      { name: 'Resend / Mailjet', desc: 'Transactional email delivery (OTPs, notifications, password resets)', logo: 'resend' },
    ],
  },
]

// Hand-drawn, single-color fallbacks for tools with no brand mark on Simple
// Icons - kept intentionally plain so they read as "generic", not a knockoff
// logo, and inherit currentColor so they follow the badge's own styling.
const GENERIC_ICONS = {
  chart: (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="4" y="12" width="3.4" height="8" rx="1" fill="currentColor" />
      <rect x="10.3" y="7" width="3.4" height="13" rx="1" fill="currentColor" />
      <rect x="16.6" y="3" width="3.4" height="17" rx="1" fill="currentColor" />
    </svg>
  ),
  pdf: (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M6 2.5h9l4.5 4.5V21a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1Z" fill="currentColor" opacity=".16" />
      <path d="M6 2.5h9l4.5 4.5V21a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M15 2.5V7h4.5" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M8 13.5h8M8 16.7h5.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
  sheet: (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3.5" y="4" width="17" height="16" rx="1.5" fill="currentColor" opacity=".14" />
      <rect x="3.5" y="4" width="17" height="16" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
      <path d="M3.5 9h17M9 9v11M14.5 9v11" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  ),
  scan: (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M7.5 9.5h9M7.5 12.5h6M7.5 15.5h4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
  fingerprint: (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 3.5c-4.7 0-8.5 3.8-8.5 8.5 0 1.7.3 3 .8 4M12 3.5c4.7 0 8.5 3.8 8.5 8.5 0 1.1-.1 2-.3 2.8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <path d="M12 7a5 5 0 0 0-5 5c0 3-1 5-1.8 6M12 7a5 5 0 0 1 5 5c0 1.7.3 4 1.1 5.7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <path d="M12 10.3a1.7 1.7 0 0 0-1.7 1.7c0 3.6-.8 6-2 7.7M12 10.3A1.7 1.7 0 0 1 13.7 12c0 2 .3 4.6 1.4 6.7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
  gauge: (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 15a8 8 0 1 1 16 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M12 15 15.2 9.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="12" cy="15" r="1.4" fill="currentColor" />
    </svg>
  ),
}

function LogoBadge({ logo, icon, name }) {
  if (logo) {
    return (
      <span className="credits-logo">
        <img
          src={`https://cdn.simpleicons.org/${logo}`}
          alt=""
          width="18"
          height="18"
          loading="lazy"
          onError={e => { e.currentTarget.style.display = 'none' }}
        />
      </span>
    )
  }
  return (
    <span className="credits-logo credits-logo-generic" aria-hidden="true">
      {GENERIC_ICONS[icon]}
    </span>
  )
}

function Credits() {
  return (
    <div className="tab-content">
      <div className="settings-card">
        <h4 className="card-label">About EcoScholar</h4>
        <p className="info-sub">
          EcoScholar is a centralized scholarship allocation system for local government
          units (LGUs) - each LGU manages its own scholarship program independently: a
          customizable application form, document verification, an ML-based eligibility
          model, and a full review workflow, all scoped to that LGU's own organization.
        </p>
      </div>

      <div className="settings-card">
        <h4 className="card-label">Built With</h4>
        <div className="credits-grid">
          {CREDITS.map(({ group, items }) => (
            <div key={group} className="credits-group">
              <h5>{group}</h5>
              <ul>
                {items.map(({ name, desc, logo, icon }) => (
                  <li key={name}>
                    <LogoBadge logo={logo} icon={icon} name={name} />
                    <div className="credits-text">
                      <strong>{name}</strong>
                      <span>{desc}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default Credits
