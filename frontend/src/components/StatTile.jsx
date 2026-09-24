import { motion } from 'framer-motion'
import './StatTile.css'

// Stat tile shared by every stat row in the app (admin and student alike): a white card
// with the label, a large value, and a slim bar in the tile's color along its left edge.
// Fades up the moment it scrolls into view; `index` staggers each tile in a row slightly
// so they don't all appear in lockstep.
export default function StatTile({ value, label, color, index = 0 }) {
  return (
    <motion.div
      className="stat-tile"
      initial={{ opacity: 0, y: 8 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.35, delay: index * 0.06, ease: [0.4, 0, 0.2, 1] }}
    >
      <span className="stat-tile-bar" style={{ background: color }} />
      <p className="stat-tile-label">{label}</p>
      <h3 className="stat-tile-value">{value}</h3>
    </motion.div>
  )
}
