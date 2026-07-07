import { useState, useEffect, useRef, useCallback } from 'react'
import { apiFetch } from '../api'
import './NotificationBell.css'

function timeAgo(dateString) {
  const seconds = Math.floor((Date.now() - new Date(dateString).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(dateString).toLocaleDateString('en-PH', { month: 'short', day: 'numeric' })
}

function NotificationBell() {
  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [open, setOpen] = useState(false)
  const containerRef = useRef(null)

  const fetchNotifications = useCallback(() => {
    apiFetch('/api/notifications')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (!data) return
        setNotifications(data.notifications || [])
        setUnreadCount(data.unread_count || 0)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetchNotifications()
    const interval = setInterval(fetchNotifications, 30000)
    return () => clearInterval(interval)
  }, [fetchNotifications])

  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleToggle = () => setOpen(o => !o)

  const handleMarkRead = (id) => {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n))
    setUnreadCount(prev => Math.max(0, prev - 1))
    apiFetch(`/api/notifications/${id}/read`, { method: 'PUT' }).catch(() => {})
  }

  const handleMarkAllRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
    setUnreadCount(0)
    apiFetch('/api/notifications/read-all', { method: 'PUT' }).catch(() => {})
  }

  return (
    <div className="nb-container" ref={containerRef}>
      <button className="nb-btn" onClick={handleToggle} title="Notifications">
        Notifications
        {unreadCount > 0 && <span className="nb-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>}
      </button>

      {open && (
        <div className="nb-panel">
          <div className="nb-header">
            <span>Notifications</span>
            {unreadCount > 0 && (
              <button className="nb-mark-all" onClick={handleMarkAllRead}>Mark all read</button>
            )}
          </div>
          <div className="nb-list">
            {notifications.length === 0 && (
              <div className="nb-empty">No notifications yet.</div>
            )}
            {notifications.map(n => (
              <div
                key={n.id}
                className={`nb-item ${n.is_read ? '' : 'unread'}`}
                onClick={() => !n.is_read && handleMarkRead(n.id)}>
                <div className="nb-item-body">
                  <p className="nb-item-message">{n.message}</p>
                  <p className="nb-item-time">{timeAgo(n.created_at)}</p>
                </div>
                {!n.is_read && <span className="nb-dot" />}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default NotificationBell
