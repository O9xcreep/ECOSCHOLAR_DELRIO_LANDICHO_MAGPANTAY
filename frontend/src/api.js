export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:5000'

// A request that never connects makes the browser hang ~40s before failing, with
// nothing on screen to say why. Give up sooner so the user gets an answer.
export const REQUEST_TIMEOUT_MS = 15000

// fetch that aborts (rejecting with an AbortError) if the server hasn't started
// responding within timeoutMs. The timer stops once headers arrive, so a slow
// response body is never cut off.
export function fetchWithTimeout(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  return fetch(url, { ...options, signal: controller.signal }).finally(() => clearTimeout(timer))
}

// Message for when fetch itself fails (offline, blocked, DNS, timeout) as opposed
// to the server answering with an error.
export function connectionErrorMessage() {
  if (navigator.onLine === false) {
    return 'You appear to be offline. Check your internet connection and try again.'
  }
  return "Can't reach the server. Check your internet connection, or try again in a minute."
}

// A "Rejected" applicant who was actually eligible just lost their slot to a
// higher-ranked applicant (see the accepted-applicant limit on the Ranking page) -
// display that as "Waitlisted" rather than "Rejected", since it isn't a judgment
// on them and they can be promoted back automatically if a slot opens up. Applicants
// the model found genuinely ineligible still show "Rejected" as-is.
export function displayStatus(status, mlStatus) {
  return status === 'Rejected' && mlStatus === 'Eligible' ? 'Waitlisted' : status
}

// Super Admin (dev/platform) and the LGU's own Admin both get full, unconditional
// access everywhere - only lgu_member is ever permission-scoped. Mirrors
// is_full_access_role() in backend/app.py; use this instead of a raw
// role === 'admin' check so lgu_admin never has to be added twice.
export function isFullAccess(user) {
  return user?.role === 'admin' || user?.role === 'lgu_admin'
}

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

// Tells the backend to blacklist the current token (so it can't be reused if
// leaked) before clearing the local session. Best-effort: logging out locally
// still proceeds even if this request fails.
export async function logout() {
  const token = getToken()
  if (token) {
    try {
      await fetch(`${API_BASE_URL}/api/logout`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
    } catch {
      // ignore - clearing the local session below is what actually logs the user out client-side
    }
  }
  clearSession()
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
