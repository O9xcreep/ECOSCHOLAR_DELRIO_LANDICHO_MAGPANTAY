import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getUser, logout } from '../api'
import NotificationBell from '../components/NotificationBell'
import { GraduationCapIcon, HomeIcon, ApplicationsIcon, GuidelinesIcon, SettingsIcon } from '../components/NavIcons'
import './StudentLayout.css'

function StudentLayout() {
  const navigate = useNavigate()
  const user = getUser() || {}

  const initial = user.full_name ? user.full_name.charAt(0).toUpperCase() : 'S'

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const navItems = [
    { to: '/student/dashboard', label: 'Dashboard', Icon: HomeIcon },
    { to: '/student/applicant-details', label: 'Applicant Details', Icon: ApplicationsIcon },
    { to: '/student/guidelines', label: 'Guidelines', Icon: GuidelinesIcon },
    { to: '/student/settings', label: 'Settings', Icon: SettingsIcon },
  ]

  return (
    <div className="student-container">

      {/* SIDEBAR (desktop) */}
      <aside className="student-sidebar">
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

      {/* MAIN */}
      <div className="student-main-wrapper">

        {/* MOBILE HEADER */}
        <header className="mobile-header">
          <div className="mobile-header-brand">
            <GraduationCapIcon />
            <span>EcoScholar</span>
          </div>
          <NotificationBell />
        </header>

        {/* TOPBAR (desktop) */}
        <header className="student-topbar">
          <div className="topbar-left">
            <h1 className="topbar-title">{user.organization_name || 'EcoScholar'}</h1>
          </div>
          <div className="topbar-right">
            <NotificationBell />
            <div className="student-profile">
              <div className="student-avatar">{initial}</div>
              <div>
                <p className="student-name">{user.full_name || 'Student'}</p>
                <p className="student-role">Applicant</p>
              </div>
            </div>
            <button className="btn-logout" onClick={handleLogout} title="Log out">Log out</button>
          </div>
        </header>

        {/* PAGE CONTENT */}
        <main className="student-main-content">
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

export default StudentLayout
