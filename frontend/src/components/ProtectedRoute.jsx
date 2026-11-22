import { Navigate } from 'react-router-dom'
import { getToken, getUser } from '../api'

// LGU members and the LGU Admin share the organization dashboard; scoped
// permissions are checked server-side per endpoint.
const ADMIN_AREA_ROLES = ['lgu_admin', 'lgu_member']

function ProtectedRoute({ role, children }) {
  const token = getToken()
  const user = getUser()

  if (!token || !user) {
    return <Navigate to="/login" replace />
  }

  const allowed = role === 'admin' ? ADMIN_AREA_ROLES.includes(user.role) : user.role === role
  if (role && !allowed) {
    const destination = user.role === 'admin'
      ? '/login'
      : user.role === 'student' ? '/student/dashboard' : '/admin/dashboard'
    return <Navigate to={destination} replace />
  }

  return children
}

export default ProtectedRoute
