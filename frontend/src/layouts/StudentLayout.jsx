import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getUser, clearSession } from '../api'
import NotificationBell from '../components/NotificationBell'
import './StudentLayout.css'

function StudentLayout() {
  const navigate = useNavigate()
  const user = getUser() || {}

  const initial = user.full_name ? user.full_name.charAt(0).toUpperCase() : 'S'

  const handleLogout = () => {
    clearSession()
    navigate('/login')
  }

  return (
    <div className="student-container">

      {/* SIDEBAR */}
      <aside className="student-sidebar">
        <div className="sidebar-logo">
          <span className="logo-text">EcoScholar</span>
        </div>

        <nav className="sidebar-nav">
          <NavLink to="/student/dashboard"
            className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <span>Dashboard</span>
          </NavLink>
          <NavLink to="/student/view-application"
            className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <span>My Application</span>
          </NavLink>
          <NavLink to="/student/documents"
            className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <span>Documents</span>
          </NavLink>
          <NavLink to="/student/guidelines"
            className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <span>Guidelines</span>
          </NavLink>
          <NavLink to="/student/settings"
            className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <span>Settings</span>
          </NavLink>
        </nav>

      </aside>

      {/* MAIN */}
      <div className="student-main-wrapper">

        {/* TOPBAR */}
        <header className="student-topbar">
          <div className="topbar-left">
            <h1 className="topbar-title">EcoScholar</h1>
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

      </div>
    </div>
  )
}

export default StudentLayout