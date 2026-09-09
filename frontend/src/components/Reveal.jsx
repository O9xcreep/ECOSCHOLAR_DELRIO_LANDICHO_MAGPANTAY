import { motion } from 'framer-motion'

// Fades + slides a block in the moment it scrolls into view, once - used on
// the major content sections of each page (not every single card, which
// would read as chaotic rather than polished). `viewport.once` means it
// never re-triggers on scrolling back up, and a small negative margin starts
// the animation slightly before the block is fully on screen so it doesn't
// feel laggy on a fast scroll.
export default function Reveal({ children, delay = 0, className, style }) {
  return (
    <motion.div
      className={className}
      style={style}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.45, delay, ease: [0.4, 0, 0.2, 1] }}
    >
      {children}
    </motion.div>
  )
}
