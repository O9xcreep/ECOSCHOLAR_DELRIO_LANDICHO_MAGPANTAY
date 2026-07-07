import { Navigate } from 'react-router-dom'
import { getToken, getUser } from '../api'

function ProtectedRoute({ role, children }) {
  const token = getToken()
  const user = getUser()

  if (!token || !user) {
    return <Navigate to="/login" replace />
  }

  if (role && user.role !== role) {
    return <Navigate to={user.role === 'admin' ? '/admin/dashboard' : '/student/dashboard'} replace />
  }

  return children
}

export default ProtectedRoute
