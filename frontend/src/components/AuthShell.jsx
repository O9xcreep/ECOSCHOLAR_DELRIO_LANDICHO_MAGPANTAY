import { GraduationCapIcon } from './NavIcons'
import './AuthShell.css'

// Layout shared by every sign-in page: the dark photo panel on the left and the form panel on
// the right (accent strip, "Secure Access" label, footer). `wide` makes room for two-column
// forms; `after` renders inside the page but outside the form panel (e.g. a modal), so it still
// picks up the page's colors.
function AuthShell({ children, wide = false, after = null }) {
  return (
    <div className="lp-page">
      <div className="lp-left">
        <div className="lp-left-rule" />
        <div className="lp-dots" />
        <div className="lp-stripe s1" />
        <div className="lp-stripe s2" />

        <div className="lp-brand">
          <div className="lp-logo">
            <GraduationCapIcon width={24} height={24} />
          </div>
          <span className="lp-name">EcoScholar</span>
        </div>

        <div className="lp-hero">
          <h1 className="lp-headline">Fund Your <span>Future.</span></h1>
          <p className="lp-tagline">
            Centralized Scholarship Allocation System - connecting students with opportunities that matter.
          </p>
        </div>

        <div className="lp-mission">
          <p className="lp-mission-label">Core Mission</p>
          <p className="lp-quote">
            "Empowering students through fair and transparent scholarship distribution."
          </p>
        </div>
      </div>

      <div className={`lp-right${wide ? ' wide' : ''}`}>
        <p className="lp-eyebrow">Secure Access</p>

        <div className={`lp-card${wide ? ' lp-card-wide' : ''}`}>
          <div className="lp-mobile-logo">
            <GraduationCapIcon width={24} height={24} />
            <span>EcoScholar</span>
          </div>
          {children}
        </div>

        <footer className="lp-footer">
          © {new Date().getFullYear()} EcoScholar
          <span className="lp-footer-sep">·</span>
          <span className="lp-footer-item">Privacy Policy</span>
          <span className="lp-footer-sep">·</span>
          <span className="lp-footer-item">Terms of Use</span>
        </footer>
      </div>

      {after}
    </div>
  )
}

export default AuthShell
