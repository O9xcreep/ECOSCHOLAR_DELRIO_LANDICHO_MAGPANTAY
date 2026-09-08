import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getUser, logout, isFullAccess } from '../api'
import NotificationBell from '../components/NotificationBell'
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

  return (
    <div className="admin-container">

      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <span className="logo-text">EcoScholar</span>
        </div>

        <nav className="sidebar-nav">
          {canReview && (
            <>
              <NavLink to="/admin/dashboard" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
                <span>Home</span>
              </NavLink>
              <NavLink to="/admin/ranking"
                className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
                <span>Ranking</span>
              </NavLink>
              <NavLink to="/admin/applications" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
                <span>Applications</span>
              </NavLink>
              <NavLink to="/admin/reports" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
                <span>Reports</span>
              </NavLink>
            </>
          )}
          <NavLink to="/admin/settings" className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
            <span>Settings</span>
          </NavLink>
        </nav>
      </aside>

      {/* MAIN CONTENT */}
      <div className="main-wrapper">

        {/* TOP NAVBAR */}
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

      </div>
    </div>
  )
}

export default AdminLayout