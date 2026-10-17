import { FileIcon } from './Icons'

// Fuentes de una respuesta: [{ title, game, document }]
// Solo se muestra el archivo de la base de conocimiento que generó los
// fragmentos; los mensajes guardados antes de existir `document` caen al título.
export function Sources({ sources }) {
  if (!sources?.length) return null
  return (
    <div className="sources">
      <span className="label">Sources</span>
      <div className="chips">
        {sources.map((s, i) => (
          <span key={i} className="chip">
            <FileIcon className="muted-icon" width={14} height={14} />
            {s.document || s.title}
          </span>
        ))}
      </div>
    </div>
  )
}
