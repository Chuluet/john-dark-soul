import { useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getConversation, getConversations } from '../api/chat'
import { useAuth } from '../auth/AuthProvider'
import solaire from '../assets/solaire.png'
import { Bonfire } from './Decor'
import { ChatIcon, ClockIcon, FileIcon, LogoutIcon, PlusIcon } from './Icons'

// session_id para el thread de LangGraph (crypto.randomUUID solo existe en HTTPS o localhost).
const newId = () => window.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
const newSession = () => ({ id: newId(), messages: [] })

// Mensajes guardados ({ question, answer, ... }) -> mensajes del chat.
const toChatMessages = (items) =>
  items.flatMap((item) => [
    { role: 'user', text: item.question },
    { role: 'agent', text: item.answer, sources: item.sources, rejected: item.rejected },
  ])

// Estructura de la app autenticada: menú lateral + la página activa.
// La conversación vive aquí para no perderla al cambiar de página.
export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [session, setSession] = useState(newSession)
  const [recent, setRecent] = useState([])

  // "Recent" lista conversaciones (todas las preguntas con el mismo session_id),
  // no preguntas sueltas.
  const refreshRecent = useCallback(() => {
    getConversations(5)
      .then(setRecent)
      .catch(() => setRecent([])) // sin conexión: el menú queda sin recientes
  }, [])

  useEffect(refreshRecent, [refreshRecent])

  const startNewChat = () => {
    setSession(newSession())
    navigate('/chat')
  }

  // Abre una conversación guardada en el chat: las preguntas nuevas siguen en
  // el mismo session_id, así que se agregan a ella.
  const openConversation = useCallback(
    async (sessionId) => {
      navigate('/chat')
      if (sessionId === session.id) return
      try {
        const items = await getConversation(sessionId)
        setSession({ id: sessionId, messages: toChatMessages(items) })
      } catch (error) {
        setSession({ id: sessionId, messages: [{ role: 'error', text: error.message }] })
      }
    },
    [navigate, session.id],
  )

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
              <button
                key={item.session_id}
                type="button"
                className={`recent-item ${item.session_id === session.id ? 'current' : ''}`}
                aria-current={item.session_id === session.id ? 'true' : undefined}
                title={item.title}
                onClick={() => openConversation(item.session_id)}
              >
                {item.title}
              </button>
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
        <Outlet context={{ session, setSession, refreshRecent, openConversation }} />
      </main>
    </div>
  )
}
