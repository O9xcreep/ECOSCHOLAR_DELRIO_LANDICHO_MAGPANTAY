import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'

// Layouts
import AdminLayout from './layouts/AdminLayout'
import StudentLayout from './layouts/StudentLayout'

// Auth
import Login from './pages/Login'
import ProtectedRoute from './components/ProtectedRoute'

// Student
import StudentDashboard from './pages/student/StudentDashboard'
import ApplicationForm from './pages/student/ApplicationForm'
import ApplicationView from './pages/student/ApplicationView'
import Documents from './pages/student/Documents'
import Guidelines from './pages/student/Guidelines'
import StudentSettings from './pages/student/StudentSettings'

// Admin
import Dashboard from './pages/admin/Dashboard'
import Ranking from './pages/admin/Ranking'
import Applicants from './pages/admin/applicants'
import Applications from './pages/admin/applications'
import Reports from './pages/admin/reports'
import Settings from './pages/admin/settings'
import FormBuilder from './pages/admin/FormBuilder'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Default */}
        <Route path="/" element={<Navigate to="/login" />} />

        {/* Auth */}
        <Route path="/login" element={<Login />} />

        {/* Student */}
        <Route path="/student" element={<ProtectedRoute role="student"><StudentLayout /></ProtectedRoute>}>
          <Route index element={<Navigate to="dashboard" />} />
          <Route path="dashboard" element={<StudentDashboard />} />
          <Route path="application" element={<ApplicationForm />} />
          <Route path="view-application" element={<ApplicationView />} />
          <Route path="documents" element={<Documents />} />
          <Route path="guidelines" element={<Guidelines />} />
          <Route path="settings" element={<StudentSettings />} />
        </Route>

        {/* Admin */}
        <Route path="/admin" element={<ProtectedRoute role="admin"><AdminLayout /></ProtectedRoute>}>
          <Route index element={<Navigate to="dashboard" />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="ranking" element={<Ranking />} />
          <Route path="applicants" element={<Applicants />} />
          <Route path="applications" element={<Applications />} />
          <Route path="reports" element={<Reports />} />
          <Route path="form-builder" element={<FormBuilder />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App