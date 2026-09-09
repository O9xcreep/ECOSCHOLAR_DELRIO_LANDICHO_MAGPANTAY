import { motion } from 'framer-motion'
import './StatTile.css'

// "Book Opening Motion" stat tile, shared by every stat row in the app (admin
// and student alike): a semi-transparent rounded rectangle holds the value/
// label, with a colored diamond accent peeking out from behind its top-right
// corner. The diamond starts flat and closed over the card and rotates+
// scales open the moment it scrolls into view - `index` staggers each tile
// in a row slightly so they don't all snap open in lockstep.
const diamondClosed = { rotate: 0, scale: 0.4, opacity: 0 }
const diamondOpen = { rotate: 45, scale: 1, opacity: 1 }

export default function StatTile({ value, label, color, index = 0 }) {
  return (
    <div className="stat-tile-book">
      <motion.div
        className="stat-tile-diamond"
        style={{ background: color }}
        initial={diamondClosed}
        whileInView={diamondOpen}
        viewport={{ once: true }}
        transition={{ duration: 0.5, delay: index * 0.08, ease: [0.4, 0, 0.2, 1] }}
      />
      <div className="stat-tile-rect">
        <h3>{value}</h3>
        <p>{label}</p>
      </div>
    </div>
  )
}
