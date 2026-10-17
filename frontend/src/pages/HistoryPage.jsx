import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getHistory } from '../api/chat'
import gwyn from '../assets/gwyn.png'
import { Quote } from '../components/Decor'
import { SearchIcon } from '../components/Icons'
import { GameTags, Sources } from '../components/Sources'

export default function HistoryPage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  // La pregunta abierta vive en la URL (?open=<id>): así el menú "Recent"
  // puede abrir una aunque ya estemos en esta página.
  const [params, setParams] = useSearchParams()
  const open = Number(params.get('open')) || null
  const setOpen = (id) => setParams(id ? { open: String(id) } : {}, { replace: true })

  // Al llegar desde "Recent", la pregunta abierta puede quedar fuera de la vista.
  useEffect(() => {
    if (open && !loading) {
      document.getElementById(`message-${open}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [open, loading])

  useEffect(() => {
    getHistory()
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const groups = useMemo(() => {
    const q = search.trim().toLowerCase()
    const filtered = items.filter((i) => !q || i.question.toLowerCase().includes(q) || i.answer.toLowerCase().includes(q))
    const byDay = new Map()
    for (const item of filtered) {
      const day = dayLabel(item.created_at)
      if (!byDay.has(day)) byDay.set(day, [])
      byDay.get(day).push(item)
    }
    return [...byDay.entries()]
  }, [items, search])

  return (
    <div className="view page">
      <div className="wrap wide stack">
        <div className="page-head">
          <div>
            <h1 className="cinzel">History</h1>
            <p className="soft">Your previous questions and the agent's answers.</p>
          </div>
          <div className="search">
            <SearchIcon className="muted-icon" />
            <label htmlFor="search" className="sr">Search history</label>
            <input id="search" type="search" placeholder="Search history" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </div>

        {loading && <p className="soft">Loading…</p>}
        {error && <p className="notice notice-error" role="alert">{error}</p>}
        {!loading && !error && groups.length === 0 && <p className="soft">No questions yet.</p>}

        {groups.map(([day, list]) => (
          <section key={day} className="stack-sm">
            <h2 className="label">{day}</h2>
            <div className="list">
              {list.map((item) => (
                <div key={item.id} id={`message-${item.id}`} className="row">
                  {/* Al hacer clic se muestra la respuesta completa con sus fuentes. */}
                  <button type="button" className="row-toggle" aria-expanded={open === item.id} onClick={() => setOpen(open === item.id ? null : item.id)}>
                    <span className="row-head">
                      <span className="row-title">{item.question}</span>
                      <span className="muted">{timeLabel(item.created_at)}</span>
                    </span>
                    {open !== item.id && (
                      <span className={`row-preview ${item.rejected ? '' : 'serif'}`}>{item.answer}</span>
                    )}
                    <span className="row-tags">
                      {item.rejected ? (
                        <span className="tag-warn">No information</span>
                      ) : (
                        <>
                          <GameTags sources={item.sources} />
                          <span className="muted small">{item.sources?.length || 0} {item.sources?.length === 1 ? 'source' : 'sources'}</span>
                        </>
                      )}
                    </span>
                  </button>
                  {open === item.id && (
                    <div className="row-full">
                      <div className={item.rejected ? '' : 'serif answer'}>{item.answer}</div>
                      <Sources sources={item.sources} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        ))}

        <div className="page-end">
          <Quote>Don't you dare go Hollow</Quote>
          <img src={gwyn} alt="" aria-hidden="true" className="wide-only end-char" />
        </div>
      </div>
    </div>
  )
}

function dayLabel(iso) {
  const d = new Date(iso)
  const today = new Date()
  const yesterday = new Date(Date.now() - 86400e3)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function timeLabel(iso) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}
