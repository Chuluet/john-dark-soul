import { ExternalIcon } from './Icons'

// Fuentes de una respuesta: [{ title, game, url }]
export function Sources({ sources }) {
  if (!sources?.length) return null
  return (
    <div className="sources">
      <span className="label">Sources</span>
      <div className="chips">
        {sources.map((s, i) => {
          const content = (
            <>
              {s.title}
              {s.game && s.game !== 'general' && <span className="tag">{s.game}</span>}
              {s.url && <ExternalIcon className="muted-icon" />}
            </>
          )
          return s.url ? (
            <a key={i} className="chip" href={s.url} target="_blank" rel="noreferrer">
              {content}
            </a>
          ) : (
            <span key={i} className="chip">
              {content}
            </span>
          )
        })}
      </div>
    </div>
  )
}

export function GameTags({ sources }) {
  const games = [...new Set((sources || []).map((s) => s.game).filter((g) => g && g !== 'general'))]
  return games.map((g) => (
    <span key={g} className="tag">
      {g}
    </span>
  ))
}
