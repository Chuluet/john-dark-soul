import { useEffect, useRef, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { sendQuestion } from '../api/chat'
import mushroom from '../assets/mushroom.png'
import siegmeyer from '../assets/siegmeyer.png'
import { Bonfire, Character } from '../components/Decor'
import { SendIcon, WarningIcon } from '../components/Icons'
import { Sources } from '../components/Sources'

const SUGGESTIONS = ['Who is Artorias?', 'What happened to Gwyn?', 'Who is Solaire of Astora?']

export default function ChatPage() {
  const { session, setSession, refreshRecent } = useOutletContext()
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const endRef = useRef(null)
  const messages = session.messages

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, loading])

  const addMessage = (message) =>
    setSession((s) => ({ ...s, messages: [...s.messages, message] }))

  async function ask(text) {
    const q = text.trim()
    if (!q || loading) return
    setQuestion('')
    addMessage({ role: 'user', text: q })
    setLoading(true)
    try {
      const result = await sendQuestion(q, session.id)
      addMessage({ role: 'agent', text: result.answer, sources: result.sources, rejected: result.rejected })
      refreshRecent()
    } catch (error) {
      addMessage({ role: 'error', text: error.message })
    } finally {
      setLoading(false)
    }
  }

  const title = messages.find((m) => m.role === 'user')?.text || 'New chat'

  return (
    <div className="view">
      <header className="chat-header">
        <h1>{title}</h1>
      </header>

      <div className="chat-body">
        <div className="wrap chat-messages">
          {messages.length === 0 && (
            <div className="empty">
              <Bonfire size={88} />
              <h2 className="cinzel">Rest at the bonfire</h2>
              <p className="serif">Ask anything about the lore of the trilogy. I only answer with what my knowledge base holds.</p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="btn btn-ghost" onClick={() => ask(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <Message key={i} message={m} />
          ))}

          {loading && (
            <div className="thinking" role="status">
              <span className="dots" aria-hidden="true"><i /><i /><i /></span>
              Searching the knowledge base…
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="composer">
        <form className="wrap" onSubmit={(e) => { e.preventDefault(); ask(question) }}>
          <div className="composer-box">
            <Character src={mushroom} className="margin-only" style={{ width: 50, right: 'calc(100% + 22px)', bottom: -2 }} />
            <Character src={siegmeyer} className="margin-only" style={{ width: 64, left: 'calc(100% + 22px)', bottom: -2 }} />
            <label htmlFor="question" className="sr">Your question</label>
            <input
              id="question"
              type="text"
              placeholder="Ask about Dark Souls lore…"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              autoComplete="off"
            />
            <button type="submit" className="send" aria-label="Send" disabled={loading || !question.trim()}>
              <SendIcon />
            </button>
          </div>
          <span className="composer-note">John only answers with what's in its knowledge base.</span>
        </form>
      </div>
    </div>
  )
}

function Message({ message }) {
  if (message.role === 'user') return <div className="bubble">{message.text}</div>

  if (message.role === 'error') {
    return (
      <article className="agent">
        <AgentLabel />
        <div className="notice notice-error" role="alert">
          <WarningIcon /> <span>{message.text}</span>
        </div>
      </article>
    )
  }

  if (message.rejected) {
    return (
      <article className="agent">
        <AgentLabel />
        <div className="rejection">
          <WarningIcon className="ember-icon" />
          <div>
            <p>{message.text}</p>
            {/* El texto del rechazo ya sugiere subir documentos: aquí solo va el enlace. */}
            <Link to="/documents">Upload documents →</Link>
          </div>
        </div>
      </article>
    )
  }

  return (
    <article className="agent">
      <AgentLabel />
      <div className="answer serif">
        {message.text.split(/\n{2,}/).map((p, i) => (
          <p key={i}>{p}</p>
        ))}
      </div>
      <Sources sources={message.sources} />
    </article>
  )
}

function AgentLabel() {
  return (
    <div className="agent-label">
      <Bonfire size={22} /> John
    </div>
  )
}
