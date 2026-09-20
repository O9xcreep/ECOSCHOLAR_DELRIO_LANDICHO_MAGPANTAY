import { useState, useEffect } from 'react'
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { apiFetch, getUser, setSession, logout, isFullAccess } from '../api'
import NotificationBell from '../components/NotificationBell'
import DisbandedStaffPrompt from '../components/DisbandedStaffPrompt'
import { GraduationCapIcon, HomeIcon, RankingIcon, ApplicationsIcon, SettingsIcon } from '../components/NavIcons'
import './AdminLayout.css'

// Page enter/leave: fades + a small vertical slide, keyed by pathname so
// switching between Dashboard/Ranking/Applications/Settings crossfades
// instead of a hard cut - the sidebar/topbar stay mounted throughout, only
// this inner content remounts.
const pageVariants = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.28, ease: [0.4, 0, 0.2, 1] } },
  exit: { opacity: 0, y: -10, transition: { duration: 0.18, ease: [0.4, 0, 1, 1] } },
}

function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = getUser() || {}

  const canReview = isFullAccess(user) || !!user.permissions?.can_review_applicants
  const roleLabel = user.role === 'admin' ? 'Super Admin' : user.role === 'lgu_admin' ? 'Admin' : 'LGU Member'

  // Set when this account belongs to no organization: null while fine or unchecked,
  // { disbandedName } otherwise (name is null for an account that never had one).
  const [noOrg, setNoOrg] = useState(null)

  // An LGU's Admin can delete their organization while staff are signed in. The
  // server has already moved or cleared those accounts, but this session's token
  // still names the deleted org, so ask the server where the account really stands.
  // (The Super Admin belongs to no organization by design, so it's skipped.)
  useEffect(() => {
    if (getUser()?.role === 'admin') return
    let cancelled = false
    ;(async () => {
      try {
        const res = await apiFetch('/api/memberships')
        if (!res.ok || cancelled) return
        const { memberships, disbanded_organization_name } = await res.json()
        if (memberships.some(m => m.is_active)) return

        if (memberships.length === 0) {
          // A session that still names an org but has no notice or memberships is an
          // older account the server hasn't back-filled yet, not a disbanded one.
          if (disbanded_organization_name || !getUser()?.organization_id) {
            setNoOrg({ disbandedName: disbanded_organization_name })
          }
          return
        }

        // Moved into another org they belong to (or just approved into one): switch
        // this session over to it.
        const target = memberships[0]
        const switchRes = await apiFetch('/api/organizations/switch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ organization_id: target.organization_id })
        })
        if (!switchRes.ok) return
        const data = await switchRes.json()
        setSession(data.user, data.token)
        window.alert(`Your previous organization is no longer available. You've been moved to ${target.organization_name}.`)
        window.location.href = data.user.role === 'student' ? '/student/dashboard' : '/admin/dashboard'
      } catch {
        // Best-effort: if the check fails the pages behave exactly as they did before it.
      }
    })()
    return () => { cancelled = true }
  }, [])

  // Settings stays reachable without an org - that's where the request to join
  // another one is made - and shows the notice above it.
  const onSettings = location.pathname === '/admin/settings'

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const navItems = [
    { to: '/admin/dashboard', label: 'Dashboard', Icon: HomeIcon, show: canReview },
    { to: '/admin/ranking', label: 'Ranking', Icon: RankingIcon, show: canReview },
    { to: '/admin/applications', label: 'Applications', Icon: ApplicationsIcon, show: canReview },
    { to: '/admin/settings', label: 'Settings', Icon: SettingsIcon, show: true },
  ].filter(item => item.show)

  return (
    <div className="admin-container">

      {/* SIDEBAR (desktop) */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <GraduationCapIcon />
          <span className="logo-text">EcoScholar</span>
        </div>

        <nav className="sidebar-nav">
          {navItems.map(({ to, label, Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
              <Icon className="nav-icon" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* MAIN CONTENT */}
      <div className="main-wrapper">

        {/* MOBILE HEADER */}
        <header className="mobile-header">
          <div className="mobile-header-brand">
            <GraduationCapIcon />
            <span>EcoScholar</span>
          </div>
          <NotificationBell />
        </header>

        {/* TOP NAVBAR (desktop) */}
        <header className="topbar">
          <div className="topbar-left">
            <h1 className="page-title">{user.organization_name || 'EcoScholar'}</h1>
          </div>
          <div className="topbar-right">
            <NotificationBell />
            <div className="admin-profile">
              <div>
                <p className="admin-name">{user.full_name || 'Admin'}</p>
                <p className="admin-role">{roleLabel}</p>
              </div>
            </div>
            <button className="btn-logout" onClick={handleLogout} title="Log out">Log out</button>
          </div>
        </header>

        {/* PAGE CONTENT */}
        <main className="main-content">
          {noOrg && <DisbandedStaffPrompt disbandedName={noOrg.disbandedName} onSettings={onSettings} />}
          {(!noOrg || onSettings) && (
            <AnimatePresence mode="wait">
              <motion.div
                key={location.pathname}
                variants={pageVariants}
                initial="initial"
                animate="animate"
                exit="exit"
              >
                <Outlet />
              </motion.div>
            </AnimatePresence>
          )}
        </main>

        {/* BOTTOM NAV (mobile) */}
        <nav className="bottom-nav">
          {navItems.map(({ to, label, Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => isActive ? 'bottom-nav-item active' : 'bottom-nav-item'}>
              <Icon />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

      </div>
    </div>
  )
}

export default AdminLayout
