export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:5000'

export function getToken() {
  return localStorage.getItem('token')
}

export function getUser() {
  try {
    return JSON.parse(localStorage.getItem('user') || 'null')
  } catch {
    return null
  }
}

export function setSession(user, token) {
  localStorage.setItem('user', JSON.stringify(user))
  localStorage.setItem('token', token)
}

export function clearSession() {
  localStorage.removeItem('user')
  localStorage.removeItem('token')
}

// fetch wrapper that prefixes the API base URL and attaches the auth token.
// On a 401 (expired/invalid session) it clears the session and redirects to /login.
export async function apiFetch(path, options = {}) {
  const token = getToken()
  const headers = { ...(options.headers || {}) }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })

  if (res.status === 401) {
    clearSession()
    if (window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
  }

  return res
}
