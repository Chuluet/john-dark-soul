import { useEffect, useRef, useState } from 'react'
import { deleteDocument, listDocuments, uploadDocument } from '../api/documents'
import ornstein from '../assets/ornstein.png'
import smough from '../assets/smough.png'
import { ACCEPTED_EXTENSIONS } from '../config'
import { Character, Quote } from '../components/Decor'
import { CheckIcon, TrashIcon, UploadIcon, VideoIcon, WarningIcon } from '../components/Icons'

const TYPE_LABELS = { wiki: 'Wiki · MD', texto: 'Text', pdf: 'PDF', docx: 'Word', csv: 'CSV', imagen: 'Image', video: 'Video' }

export default function DocumentsPage() {
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [upload, setUpload] = useState(null) // { name, progress }
  const [notice, setNotice] = useState(null) // { kind: 'ok' | 'error', text }
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  const load = () =>
    listDocuments()
      .then((d) => { setDocs(d); setError(null) })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))

  useEffect(() => { load() }, [])

  async function handleFile(file) {
    if (!file || upload) return
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setNotice({ kind: 'error', text: `${file.name}: file type not supported.` })
      return
    }
    setNotice(null)
    setUpload({ name: file.name, progress: 0 })
    try {
      const result = await uploadDocument(file, (progress) => setUpload({ name: file.name, progress }))
      setNotice({ kind: 'ok', text: `${result?.source || file.name} uploaded · ${result?.chunks ?? '?'} chunks` })
      load()
    } catch (e) {
      setNotice({ kind: 'error', text: `${file.name}: ${e.message}` })
    } finally {
      setUpload(null)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  async function handleDelete(doc) {
    if (!window.confirm(`Delete ${doc.source} from the knowledge base?`)) return
    try {
      await deleteDocument(doc.source)
      load()
    } catch (e) {
      setNotice({ kind: 'error', text: e.message })
    }
  }

  const totalChunks = docs.reduce((sum, d) => sum + (d.chunks || 0), 0)
  const images = docs.filter((d) => d.type === 'imagen').length
  const videos = docs.filter((d) => d.type === 'video').length
  const isMedia = upload && /\.(mp4|mp3)$/i.test(upload.name)

  return (
    <div className="view page">
      <div className="wrap wide stack">
        <div>
          <h1 className="cinzel">Documents</h1>
          <p className="soft">Upload files to expand the agent's knowledge base.</p>
        </div>

        <div className="counters">
          <div className="panel"><strong>{totalChunks.toLocaleString('en-US')}</strong><span>indexed chunks</span></div>
          <div className="panel"><strong>{images}</strong><span>images</span></div>
          <div className="panel"><strong>{videos}</strong><span>transcribed videos</span></div>
        </div>

        <div className="dropzone-wrap">
          <Character src={ornstein} className="wide-only" style={{ width: 120, left: -92, bottom: -4 }} />
          <Character src={smough} className="wide-only" style={{ width: 170, right: -120, bottom: -4 }} />
          <label
            htmlFor="file"
            className={`dropzone ${dragging ? 'dragging' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]) }}
          >
            <UploadIcon className="ember-icon" />
            <span className="dropzone-title">Drag a file here or <u>browse</u></span>
            <span className="soft small">PDF, TXT, MD, DOCX, CSV · Images JPG, PNG · Audio and video MP3, MP4</span>
            <input ref={inputRef} id="file" type="file" className="sr" accept={ACCEPTED_EXTENSIONS.join(',')} onChange={(e) => handleFile(e.target.files[0])} />
          </label>
        </div>

        {(upload || notice) && (
          <section className="stack-sm">
            <h2 className="label">Processing</h2>
            {upload && (
              <div className="panel progress-card">
                <div className="row-head">
                  <span className="file-name"><VideoIcon className="muted-icon" /> {upload.name}</span>
                  <span className="soft small">{upload.progress < 100 ? `Uploading · ${upload.progress}%` : 'Processing…'}</span>
                </div>
                <div className="progress" role="progressbar" aria-label={`${upload.name} progress`} aria-valuenow={upload.progress} aria-valuemin="0" aria-valuemax="100">
                  <div style={{ width: `${upload.progress}%` }} />
                </div>
                {isMedia && <span className="muted small">Long videos can take several minutes. You can keep using the chat.</span>}
              </div>
            )}
            {notice && (
              <div className={`notice ${notice.kind === 'ok' ? 'notice-ok' : 'notice-error'}`} role="status">
                {notice.kind === 'ok' ? <CheckIcon /> : <WarningIcon />} {notice.text}
              </div>
            )}
          </section>
        )}

        <section className="stack-sm">
          <h2 className="label">Uploaded documents</h2>
          {error && <p className="notice notice-error" role="alert">{error}</p>}
          {loading && <p className="soft">Loading…</p>}
          {!loading && !error && (
            <div className="table-box">
              <table>
                <thead>
                  <tr><th>Name</th><th>Type</th><th>Date</th><th className="num">Chunks</th><th><span className="sr">Actions</span></th></tr>
                </thead>
                <tbody>
                  {docs.length === 0 && (
                    <tr><td colSpan="5" className="soft">No documents yet.</td></tr>
                  )}
                  {docs.map((doc) => (
                    <tr key={doc.source}>
                      <td>{doc.source}</td>
                      <td>{TYPE_LABELS[doc.type] || doc.type}</td>
                      <td>{doc.created_at ? new Date(doc.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}</td>
                      <td className="num strong">{(doc.chunks ?? 0).toLocaleString('en-US')}</td>
                      <td className="actions">
                        {doc.base ? (
                          <span className="muted small">Base</span>
                        ) : (
                          <button type="button" className="icon-btn danger" aria-label={`Delete ${doc.source}`} onClick={() => handleDelete(doc)}>
                            <TrashIcon />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <Quote>May the flames guide thee</Quote>
      </div>
    </div>
  )
}
