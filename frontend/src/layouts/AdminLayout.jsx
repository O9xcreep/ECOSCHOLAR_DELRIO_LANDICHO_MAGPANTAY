import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { getUser, logout, isFullAccess } from '../api'
import NotificationBell from '../components/NotificationBell'
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
  const initial = user.full_name ? user.full_name.charAt(0).toUpperCase() : 'A'

  const canReview = isFullAccess(user) || !!user.permissions?.can_review_applicants
  const roleLabel = user.role === 'admin' ? 'Super Admin' : user.role === 'lgu_admin' ? 'Admin' : 'LGU Member'

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
              <div className="admin-avatar">{initial}</div>
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
