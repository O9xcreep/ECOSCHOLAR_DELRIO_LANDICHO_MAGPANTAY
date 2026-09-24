import { motion } from 'framer-motion'
import './StatTile.css'

// Line icons (24x24, stroke) for the stat tiles.
const ICONS = {
  users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></>,
  clock: <><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></>,
  check: <><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></>,
  x: <><circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" /></>,
  alert: <><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></>,
  hourglass: <><path d="M5 22h14" /><path d="M5 2h14" /><path d="M17 22v-4.17a2 2 0 0 0-.59-1.42L12 12l-4.41 4.41A2 2 0 0 0 7 17.83V22" /><path d="M7 2v4.17a2 2 0 0 0 .59 1.42L12 12l4.41-4.41A2 2 0 0 0 17 6.17V2" /></>,
  layers: <><polygon points="12 2 2 7 12 12 22 7 12 2" /><polyline points="2 17 12 22 22 17" /><polyline points="2 12 12 17 22 12" /></>,
  file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /></>,
  upload: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></>,
  pie: <><path d="M21.21 15.89A10 10 0 1 1 8 2.83" /><path d="M22 12A10 10 0 0 0 12 2v10z" /></>,
  list: <><line x1="9" y1="6" x2="21" y2="6" /><line x1="9" y1="12" x2="21" y2="12" /><line x1="9" y1="18" x2="21" y2="18" /><polyline points="3 6 4.5 7.5 7 5" /><polyline points="3 12 4.5 13.5 7 11" /><polyline points="3 18 4.5 19.5 7 17" /></>,
  chart: <><line x1="12" y1="20" x2="12" y2="10" /><line x1="18" y1="20" x2="18" y2="4" /><line x1="6" y1="20" x2="6" y2="16" /></>,
}

// Picks an icon from the tile's label, so pages only pass a label and a color.
// Order matters: the first match wins ("Docs Uploaded" before "Missing Docs", etc.).
const ICON_RULES = [
  [/upload/i, 'upload'],
  [/missing|incomplete/i, 'alert'],
  [/reject/i, 'x'],
  [/approved|within/i, 'check'],
  [/waitlist/i, 'hourglass'],
  [/slot/i, 'layers'],
  [/review|pending/i, 'clock'],
  [/newly|required/i, 'file'],
  [/completion/i, 'pie'],
  [/step/i, 'list'],
  [/total|applicant/i, 'users'],
]

function iconFor(label) {
  const hit = ICON_RULES.find(([pattern]) => pattern.test(String(label)))
  return ICONS[hit ? hit[1] : 'chart']
}

// Stat tile shared by every stat row in the app (admin and student alike): the label and a
// tinted icon on top, the value below, with a soft glow and a short marker in the tile's
// color. Fades up when it scrolls into view; `index` staggers the tiles in a row.
export default function StatTile({ value, label, color = 'var(--accent)', index = 0 }) {
  return (
    <motion.div
      className="stat-tile"
      style={{ '--tile': color }}
      initial={{ opacity: 0, y: 8 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.35, delay: index * 0.06, ease: [0.4, 0, 0.2, 1] }}
    >
      <div className="stat-tile-top">
        <p className="stat-tile-label">{label}</p>
        <span className="stat-tile-icon">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {iconFor(label)}
          </svg>
        </span>
      </div>
      <h3 className="stat-tile-value">{value}</h3>
    </motion.div>
  )
}
