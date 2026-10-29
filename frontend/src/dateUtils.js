// The backend stores times in UTC and sends most of them as naive strings
// ("YYYY-MM-DD HH:MM:SS", see iso() in backend/helpers.py) with no timezone
// marker. new Date() reads those as the viewer's local time, which shifts
// them by 8 hours in the Philippines (a 12:00 PM deadline shows as 4:00 AM).
// This parses naive timestamps as UTC and leaves anything that already
// carries a zone (Flask's "... GMT", "Z", "+08:00") untouched.
const NAIVE_TIMESTAMP = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/

export function parseServerDate(value) {
  if (!value) return null
  if (value instanceof Date) return value
  const s = String(value)
  return new Date(NAIVE_TIMESTAMP.test(s) ? s.replace(' ', 'T') + 'Z' : s)
}
