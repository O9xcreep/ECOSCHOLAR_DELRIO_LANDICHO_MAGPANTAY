import './Credits.css'

// Static, not admin-editable (unlike Guidelines) - this describes the platform
// itself, which is identical for every LGU, not something each org customizes.
const CREDITS = [
  {
    group: 'Frontend',
    items: [
      ['React 19 + React Router', 'UI and page routing'],
      ['Vite', 'Build tool and dev server'],
      ['Recharts', 'Dashboard charts and analytics'],
      ['Framer Motion', 'Page transitions and scroll animations'],
      ['jsPDF + jsPDF-AutoTable', 'Ranking and report PDF exports'],
      ['write-excel-file', 'Applicant data Excel exports'],
    ],
  },
  {
    group: 'Backend',
    items: [
      ['Flask', 'Web framework and REST API'],
      ['MongoDB (via PyMongo)', 'Database'],
      ['scikit-learn + XGBoost', 'The eligibility scoring model (Random Forest Regressor + XGBoost Classifier)'],
      ['Tesseract OCR', 'Document text extraction for admin verification (via pytesseract, pdf2image, Pillow)'],
      ['ImageHash', 'Perceptual hashing for duplicate-document detection'],
      ['Flask-Limiter', 'API rate limiting'],
    ],
  },
  {
    group: 'Infrastructure',
    items: [
      ['Vercel', 'Frontend hosting'],
      ['Render', 'Backend hosting'],
      ['MongoDB Atlas', 'Managed database hosting'],
      ['Resend / Mailjet', 'Transactional email delivery (OTPs, notifications, password resets)'],
    ],
  },
]

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
                {items.map(([name, desc]) => (
                  <li key={name}>
                    <strong>{name}</strong>
                    <span>{desc}</span>
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
