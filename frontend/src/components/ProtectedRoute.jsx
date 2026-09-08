import { Navigate } from 'react-router-dom'
import { getToken, getUser } from '../api'

// LGU members (and the LGU's own Admin) share the admin area with Super Admin - their
// scoped permissions are checked server-side per endpoint, only the route-level
// admin/student split happens here.
const ADMIN_AREA_ROLES = ['admin', 'lgu_admin', 'lgu_member']

function ProtectedRoute({ role, children }) {
  const token = getToken()
  const user = getUser()

  if (!token || !user) {
    return <Navigate to="/login" replace />
  }

  const allowed = role === 'admin' ? ADMIN_AREA_ROLES.includes(user.role) : user.role === role
  if (role && !allowed) {
    return <Navigate to={user.role === 'student' ? '/student/dashboard' : '/admin/dashboard'} replace />
  }

  return children
}

export default ProtectedRoute
