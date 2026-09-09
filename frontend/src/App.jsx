import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'

// Layouts
import AdminLayout from './layouts/AdminLayout'
import StudentLayout from './layouts/StudentLayout'

// Auth
import ProtectedRoute from './components/ProtectedRoute'
import { getUser, isFullAccess } from './api'

const Login = lazy(() => import('./pages/Login'))
const ResetPassword = lazy(() => import('./pages/ResetPassword'))
const ApplyAdmin = lazy(() => import('./pages/ApplyAdmin'))
const AdminSetup = lazy(() => import('./pages/AdminSetup'))

// Student
const StudentDashboard = lazy(() => import('./pages/student/StudentDashboard'))
const ApplicationForm = lazy(() => import('./pages/student/ApplicationForm'))
const ApplicantDetails = lazy(() => import('./pages/student/ApplicantDetails'))
const Guidelines = lazy(() => import('./pages/student/Guidelines'))
const StudentSettings = lazy(() => import('./pages/student/StudentSettings'))

// Admin
const Dashboard = lazy(() => import('./pages/admin/Dashboard'))
const Ranking = lazy(() => import('./pages/admin/Ranking'))
const Applications = lazy(() => import('./pages/admin/applications'))
const Settings = lazy(() => import('./pages/admin/settings'))

function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<div style={{ padding: '3rem', textAlign: 'center', color: '#6b7280' }}>Loading...</div>}>
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
              const canReview = isFullAccess(u) || !!u.permissions?.can_review_applicants
              return canReview ? 'dashboard' : 'settings'
            })()
          } />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="ranking" element={<Ranking />} />
          {/* Old route from before Applicants merged into Applications */}
          <Route path="applicants" element={<Navigate to="/admin/applications" replace />} />
          <Route path="applications" element={<Applications />} />
          {/* Old route from before Reports merged into Dashboard */}
          <Route path="reports" element={<Navigate to="/admin/dashboard" replace />} />
          {/* Old route from before Form Builder moved into Settings > System */}
          <Route path="form-builder" element={<Navigate to="/admin/settings" replace />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
      </Suspense>
    </BrowserRouter>
  )
}

export default App