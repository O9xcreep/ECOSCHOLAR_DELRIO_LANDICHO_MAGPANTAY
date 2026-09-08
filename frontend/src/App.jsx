import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'

// Layouts
import AdminLayout from './layouts/AdminLayout'
import StudentLayout from './layouts/StudentLayout'

// Auth
import Login from './pages/Login'
import ResetPassword from './pages/ResetPassword'
import ApplyAdmin from './pages/ApplyAdmin'
import AdminSetup from './pages/AdminSetup'
import ProtectedRoute from './components/ProtectedRoute'
import { getUser } from './api'

// Student
import StudentDashboard from './pages/student/StudentDashboard'
import ApplicationForm from './pages/student/ApplicationForm'
import ApplicantDetails from './pages/student/ApplicantDetails'
import Guidelines from './pages/student/Guidelines'
import StudentSettings from './pages/student/StudentSettings'

// Admin
import Dashboard from './pages/admin/Dashboard'
import Ranking from './pages/admin/Ranking'
import Applications from './pages/admin/applications'
import Reports from './pages/admin/reports'
import Settings from './pages/admin/settings'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Default */}
        <Route path="/" element={<Navigate to="/login" />} />

        {/* Auth */}
        <Route path="/login" element={<Login />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/apply-admin" element={<ApplyAdmin />} />
        <Route path="/admin-setup" element={<AdminSetup />} />

        {/* Student */}
        <Route path="/student" element={<ProtectedRoute role="student"><StudentLayout /></ProtectedRoute>}>
          <Route index element={<Navigate to="dashboard" />} />
          <Route path="dashboard" element={<StudentDashboard />} />
          <Route path="application" element={<ApplicationForm />} />
          <Route path="applicant-details" element={<ApplicantDetails />} />
          {/* Old routes from before Documents merged into Applicant Details */}
          <Route path="view-application" element={<Navigate to="/student/applicant-details" replace />} />
          <Route path="documents" element={<Navigate to="/student/applicant-details" replace />} />
          <Route path="guidelines" element={<Guidelines />} />
          <Route path="settings" element={<StudentSettings />} />
        </Route>

        {/* Admin */}
        <Route path="/admin" element={<ProtectedRoute role="admin"><AdminLayout /></ProtectedRoute>}>
          <Route index element={<Navigate to={
            (() => {
              const u = getUser() || {}
              const canReview = u.role === 'admin' || !!u.permissions?.can_review_applicants
              return canReview ? 'dashboard' : 'settings'
            })()
          } />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="ranking" element={<Ranking />} />
          {/* Old route from before Applicants merged into Applications */}
          <Route path="applicants" element={<Navigate to="/admin/applications" replace />} />
          <Route path="applications" element={<Applications />} />
          <Route path="reports" element={<Reports />} />
          {/* Old route from before Form Builder moved into Settings > System */}
          <Route path="form-builder" element={<Navigate to="/admin/settings" replace />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App