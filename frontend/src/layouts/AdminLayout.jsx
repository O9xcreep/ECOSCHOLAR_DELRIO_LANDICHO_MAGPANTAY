import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getUser, logout, isFullAccess } from '../api'
import NotificationBell from '../components/NotificationBell'
import { GraduationCapIcon, HomeIcon, RankingIcon, ApplicationsIcon, ReportsIcon, SettingsIcon } from '../components/NavIcons'
import './AdminLayout.css'

function AdminLayout() {
  const navigate = useNavigate()
  const user = getUser() || {}
  const initial = user.full_name ? user.full_name.charAt(0).toUpperCase() : 'A'

  const canReview = isFullAccess(user) || !!user.permissions?.can_review_applicants
  const roleLabel = user.role === 'admin' ? 'Super Admin' : user.role === 'lgu_admin' ? 'Admin' : 'LGU Member'

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const navItems = [
    { to: '/admin/dashboard', label: 'Home', Icon: HomeIcon, show: canReview },
    { to: '/admin/ranking', label: 'Ranking', Icon: RankingIcon, show: canReview },
    { to: '/admin/applications', label: 'Applications', Icon: ApplicationsIcon, show: canReview },
    { to: '/admin/reports', label: 'Reports', Icon: ReportsIcon, show: canReview },
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
            <h1 className="page-title">EcoScholar</h1>
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
          <Outlet />
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
