// Datos de ejemplo para VITE_USE_MOCKS=true: permiten usar la interfaz sin
// backend ni Keycloak. Siguen el mismo contrato que chat.js y documents.js.

const wait = (ms) => new Promise((r) => setTimeout(r, ms))

const REJECTION =
  "I don't have enough information in my knowledge base to answer that question. " +
  'If you have documents on this topic, you can upload them so I can answer it.'

const ARTORIAS = {
  answer:
    "Artorias the Abysswalker was one of Lord Gwyn's Four Knights, known for his swordsmanship and his unbending will (source: Knight Artorias, DS1).\n\n" +
    'According to legend, he travelled to Oolacile to stop the spread of the Abyss, together with the great grey wolf Sif. He was corrupted by the Abyss and ended up fighting the people he meant to save (source: Oolacile, DS1).',
  sources: [
    { title: 'Knight Artorias', game: 'DS1', document: 'knight-artorias__DS1.md' },
    { title: 'Oolacile', game: 'DS1', document: 'oolacile__DS1.md' },
  ],
  rejected: false,
}

const now = Date.now()
const history = [
  { id: 3, session_id: 'm-2', question: 'Who is Solaire of Astora?', answer: 'Solaire is a knight of Astora searching for his own sun…', sources: [{ title: 'Solaire of Astora', game: 'DS1', document: 'solaire-of-astora__DS1.md' }], rejected: false, created_at: new Date(now - 26 * 3600e3).toISOString() },
  { id: 2, session_id: 'm-1', question: 'What is the best sushi in Tokyo?', answer: REJECTION, sources: [], rejected: true, created_at: new Date(now - 2 * 3600e3).toISOString() },
  { id: 1, session_id: 'm-1', question: 'Who is Artorias?', ...ARTORIAS, created_at: new Date(now - 3 * 3600e3).toISOString() },
]

let documents = [
  { id: 3, filename: 'slave_knight_gael__DS3.md', tipo: 'wiki', juegos: ['DS3'], chunks: 14, active: true, created_at: new Date(now - 3600e3).toISOString() },
  { id: 2, filename: 'The COMPLETE Dark Souls Series Story Retrospective.mp4', tipo: 'video', juegos: ['DS1', 'DS2', 'DS3'], chunks: 276, active: true, created_at: new Date(now - 2 * 86400e3).toISOString() },
  { id: 1, filename: 'ornstein_y_smough.png', tipo: 'imagen', juegos: ['DS1'], chunks: 1, active: false, created_at: new Date(now - 2 * 86400e3).toISOString() },
]

export async function getMe() {
  return { sub: 'demo', username: 'demo', email: 'demo@john-dark-soul.local', roles: ['user'] }
}

export async function sendQuestion(question, sessionId) {
  await wait(1200)
  const offTopic = /sushi|pizza|weather|clima|fútbol|futbol/i.test(question)
  const result = offTopic ? { answer: REJECTION, sources: [], rejected: true } : ARTORIAS
  history.unshift({ id: history.length + 1, session_id: sessionId, question, ...result, created_at: new Date().toISOString() })
  return result
}

export async function getHistory() {
  await wait(300)
  return [...history]
}

export async function listDocuments() {
  await wait(300)
  return [...documents]
}

export async function deleteDocument(id) {
  await wait(300)
  documents = documents.filter((d) => d.id !== id)
  return null
}

export async function uploadDocument(file, onProgress) {
  for (let p = 10; p <= 100; p += 15) {
    await wait(200)
    onProgress?.(Math.min(p, 100))
  }
  const chunks = Math.max(1, Math.round(file.size / 900))
  const doc = { id: Date.now(), filename: file.name, tipo: 'texto', juegos: [], chunks, active: true, created_at: new Date().toISOString() }
  documents = [doc, ...documents]
  return doc
}

export async function setDocumentActive(id, active) {
  await wait(150)
  documents = documents.map((d) => (d.id === id ? { ...d, active } : d))
  return null
}

let knowledgeBase = [
  { source: 'knight-artorias__DS1.md', title: 'Knight Artorias', tipo: 'wiki', juegos: ['DS1'], chunks: 25, active: true },
  { source: 'great-grey-wolf-sif__DS1.md', title: 'Great Grey Wolf Sif', tipo: 'wiki', juegos: ['DS1'], chunks: 9, active: true },
  { source: 'abyss-watchers__DS3.md', title: 'Abyss Watchers', tipo: 'wiki', juegos: ['DS3'], chunks: 8, active: true },
  { source: 'The COMPLETE Dark Souls Series Story Retrospective.mp4', title: 'The COMPLETE Dark Souls Series Story Retrospective', tipo: 'video', juegos: ['DS1', 'DS2', 'DS3'], chunks: 262, active: false },
]

export async function listKnowledgeBase() {
  await wait(300)
  return [...knowledgeBase]
}

export async function setKnowledgeBaseActive(source, active) {
  await wait(150)
  knowledgeBase = knowledgeBase.map((d) => (d.source === source ? { ...d, active } : d))
  return null
}

export async function getConversations(limit) {
  await wait(200)
  const bySession = new Map()
  for (const item of history) {
    const c = bySession.get(item.session_id)
    if (!c) bySession.set(item.session_id, { session_id: item.session_id, title: item.question, updated_at: item.created_at, messages: 1 })
    else c.messages += 1
  }
  // history va del más reciente al más antiguo: el título es la pregunta más vieja.
  for (const item of history) bySession.get(item.session_id).title = item.question
  return [...bySession.values()].slice(0, limit)
}

export async function getConversation(sessionId) {
  await wait(200)
  return history.filter((h) => h.session_id === sessionId).reverse()
}
