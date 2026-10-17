import { useCallback, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getHistory } from '../api/chat'
import { useAuth } from '../auth/AuthProvider'
import solaire from '../assets/solaire.png'
import { Bonfire } from './Decor'
import { ChatIcon, ClockIcon, FileIcon, LogoutIcon, PlusIcon } from './Icons'

// session_id para el thread de LangGraph (crypto.randomUUID solo existe en HTTPS o localhost).
const newId = () => window.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
const newSession = () => ({ id: newId(), messages: [] })

// Estructura de la app autenticada: menú lateral + la página activa.
// La conversación vive aquí para no perderla al cambiar de página.
export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [session, setSession] = useState(newSession)
  const [recent, setRecent] = useState([])

  const refreshRecent = useCallback(() => {
    getHistory()
      .then((items) => setRecent(items.slice(0, 3)))
      .catch(() => setRecent([])) // sin endpoint todavía: el menú queda sin recientes
  }, [])

  useEffect(refreshRecent, [refreshRecent])

  const startNewChat = () => {
    setSession(newSession())
    navigate('/chat')
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <Bonfire size={32} />
          <span className="cinzel">John Dark Soul</span>
        </div>

        <button type="button" className="btn btn-ghost" onClick={startNewChat}>
          <PlusIcon /> New chat
        </button>

        <nav className="nav" aria-label="Main">
          <NavLink to="/chat"><ChatIcon /> Chat</NavLink>
          <NavLink to="/history"><ClockIcon /> History</NavLink>
          <NavLink to="/documents"><FileIcon /> Documents</NavLink>
        </nav>

        {recent.length > 0 && (
          <div className="recent">
            <span className="label">Recent</span>
            {recent.map((item) => (
              // ?open=<id>: History abre esa pregunta y la lleva a la vista.
              <Link key={item.id} to={`/history?open=${item.id}`} className="recent-item">
                {item.question}
              </Link>
            ))}
          </div>
        )}

        <div className="spacer" />

        <div className="sidebar-quote">
          <img src={solaire} alt="" aria-hidden="true" />
          <span className="quote">Praise the Sun!</span>
        </div>

        <div className="user">
          <div className="avatar" aria-hidden="true">
            {(user?.username || '?').charAt(0).toUpperCase()}
          </div>
          <div className="user-info">
            <span>{user?.username}</span>
            <small>Signed in</small>
          </div>
          <button type="button" className="icon-btn" aria-label="Sign out" onClick={logout}>
            <LogoutIcon />
          </button>
        </div>
      </aside>

      <main className="main">
        <Outlet context={{ session, setSession, refreshRecent }} />
      </main>
    </div>
  )
}
