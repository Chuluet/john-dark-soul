import { useEffect, useMemo, useRef, useState } from 'react'
import {
  deleteDocument,
  listDocuments,
  listKnowledgeBase,
  setDocumentActive,
  setKnowledgeBaseActive,
  uploadDocument,
} from '../api/documents'
import ornstein from '../assets/ornstein.png'
import smough from '../assets/smough.png'
import { ACCEPTED_EXTENSIONS } from '../config'
import { Character, Quote } from '../components/Decor'
import { CheckIcon, SearchIcon, TrashIcon, UploadIcon, VideoIcon, WarningIcon } from '../components/Icons'

const TYPE_LABELS = { wiki: 'Wiki · MD', texto: 'Text', pdf: 'PDF', docx: 'Word', csv: 'CSV', imagen: 'Image', video: 'Video' }

export default function DocumentsPage() {
  const [docs, setDocs] = useState([])
  const [base, setBase] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [baseError, setBaseError] = useState(null)
  const [search, setSearch] = useState('')
  const [upload, setUpload] = useState(null) // { name, progress }
  const [notice, setNotice] = useState(null) // { kind: 'ok' | 'error', text }
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  const loadDocs = () =>
    listDocuments()
      .then((d) => { setDocs(d); setError(null) })
      .catch((e) => setError(e.message))

  const loadBase = () =>
    listKnowledgeBase()
      .then((d) => { setBase(d); setBaseError(null) })
      .catch((e) => setBaseError(e.message))

  useEffect(() => {
    Promise.all([loadDocs(), loadBase()]).finally(() => setLoading(false))
  }, [])

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
      setNotice({ kind: 'ok', text: `${result?.filename || file.name} uploaded · ${result?.chunks ?? '?'} chunks` })
      loadDocs()
    } catch (e) {
      setNotice({ kind: 'error', text: `${file.name}: ${e.message}` })
    } finally {
      setUpload(null)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  async function handleDelete(doc) {
    if (!window.confirm(`Delete ${doc.filename} from the knowledge base?`)) return
    try {
      await deleteDocument(doc.id)
      loadDocs()
    } catch (e) {
      setNotice({ kind: 'error', text: e.message })
    }
  }

  // El interruptor cambia al instante; si el backend falla, vuelve a su estado.
  async function toggle(setList, matches, save, active) {
    setList((list) => list.map((d) => (matches(d) ? { ...d, active } : d)))
    try {
      await save()
    } catch (e) {
      setList((list) => list.map((d) => (matches(d) ? { ...d, active: !active } : d)))
      setNotice({ kind: 'error', text: e.message })
    }
  }

  const toggleDoc = (doc, active) =>
    toggle(setDocs, (d) => d.id === doc.id, () => setDocumentActive(doc.id, active), active)

  const toggleBase = (doc, active) =>
    toggle(setBase, (d) => d.source === doc.source, () => setKnowledgeBaseActive(doc.source, active), active)

  const filteredBase = useMemo(() => {
    const q = search.trim().toLowerCase()
    return base.filter((d) => !q || d.source.toLowerCase().includes(q) || d.title.toLowerCase().includes(q))
  }, [base, search])

  const activeChunks = [...docs, ...base].filter((d) => d.active).reduce((sum, d) => sum + (d.chunks || 0), 0)
  const activeBase = base.filter((d) => d.active).length
  const isMedia = upload && /\.(mp4|mp3)$/i.test(upload.name)

  return (
    <div className="view page">
      <div className="wrap wide stack">
        <div>
          <h1 className="cinzel">Documents</h1>
          <p className="soft">Choose which documents the agent uses to answer you, or upload your own.</p>
        </div>

        <div className="counters">
          <div className="panel"><strong>{activeChunks.toLocaleString('en-US')}</strong><span>active chunks</span></div>
          <div className="panel"><strong>{activeBase} / {base.length}</strong><span>knowledge base documents enabled</span></div>
          <div className="panel"><strong>{docs.length}</strong><span>uploaded by you</span></div>
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

        {loading && <p className="soft">Loading…</p>}

        {!loading && (
          <section className="stack-sm">
            <h2 className="label">Your documents</h2>
            {error && <p className="notice notice-error" role="alert">{error}</p>}
            {!error && (
              <div className="table-box">
                <table>
                  <thead>
                    <tr><th>Name</th><th>Type</th><th>Games</th><th>Date</th><th className="num">Chunks</th><th>Active</th><th><span className="sr">Actions</span></th></tr>
                  </thead>
                  <tbody>
                    {docs.length === 0 && (
                      <tr><td colSpan="7" className="soft">You have not uploaded any documents yet.</td></tr>
                    )}
                    {docs.map((doc) => (
                      <tr key={doc.id} className={doc.active ? '' : 'inactive'}>
                        <td>{doc.filename}</td>
                        <td>{TYPE_LABELS[doc.tipo] || doc.tipo}</td>
                        <td><Games juegos={doc.juegos} /></td>
                        <td>{doc.created_at ? new Date(doc.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}</td>
                        <td className="num strong">{(doc.chunks ?? 0).toLocaleString('en-US')}</td>
                        <td><Switch checked={doc.active} label={doc.filename} onChange={(active) => toggleDoc(doc, active)} /></td>
                        <td className="actions">
                          <button type="button" className="icon-btn danger" aria-label={`Delete ${doc.filename}`} onClick={() => handleDelete(doc)}>
                            <TrashIcon />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {!loading && (
          <section className="stack-sm">
            <div className="page-head">
              <div>
                <h2 className="label">Knowledge base</h2>
                <p className="soft small">Original documents. Disabling one only affects your answers.</p>
              </div>
              <div className="search">
                <SearchIcon className="muted-icon" />
                <label htmlFor="kb-search" className="sr">Search the knowledge base</label>
                <input id="kb-search" type="search" placeholder="Search documents" value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>
            </div>
            {baseError && <p className="notice notice-error" role="alert">{baseError}</p>}
            {!baseError && (
              <div className="table-box">
                <table>
                  <thead>
                    <tr><th>Document</th><th>Type</th><th>Games</th><th className="num">Chunks</th><th>Active</th></tr>
                  </thead>
                  <tbody>
                    {filteredBase.length === 0 && (
                      <tr><td colSpan="5" className="soft">{base.length ? 'No documents match your search.' : 'The knowledge base is empty.'}</td></tr>
                    )}
                    {filteredBase.map((doc) => (
                      <tr key={doc.source} className={doc.active ? '' : 'inactive'}>
                        <td>
                          <span className="doc-name">{doc.source}</span>
                          {doc.title !== doc.source && <span className="muted small doc-title">{doc.title}</span>}
                        </td>
                        <td>{TYPE_LABELS[doc.tipo] || doc.tipo}</td>
                        <td><Games juegos={doc.juegos} /></td>
                        <td className="num strong">{(doc.chunks ?? 0).toLocaleString('en-US')}</td>
                        <td><Switch checked={doc.active} label={doc.source} onChange={(active) => toggleBase(doc, active)} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        <Quote>May the flames guide thee</Quote>
      </div>
    </div>
  )
}

function Games({ juegos }) {
  return juegos?.length ? juegos.map((g) => <span key={g} className="tag">{g}</span>) : '—'
}

function Switch({ checked, label, onChange }) {
  return (
    <label className="switch">
      <input type="checkbox" role="switch" checked={checked} aria-label={`Use ${label}`} onChange={(e) => onChange(e.target.checked)} />
      <span aria-hidden="true" />
    </label>
  )
}
