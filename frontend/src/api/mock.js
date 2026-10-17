// Datos de ejemplo para VITE_USE_MOCKS=true: permiten usar la interfaz sin
// backend ni Keycloak. Siguen el mismo contrato que chat.js y documents.js.

const wait = (ms) => new Promise((r) => setTimeout(r, ms))

const REJECTION =
  'No tengo suficiente información en mi base de conocimiento para responder esa pregunta. ' +
  'Si tienes documentos sobre ese tema, puedes subirlos para que pueda responderla.'

const ARTORIAS = {
  answer:
    'Artorias, el Caminante del Abismo, fue uno de los cuatro caballeros de Lord Gwyn. Era conocido por su habilidad con la espada y por su voluntad inquebrantable (fuente: Knight Artorias, DS1).\n\n' +
    'Según la leyenda, viajó a Oolacile para detener la propagación del Abismo, acompañado por el gran lobo gris Sif. Fue corrompido por el Abismo y terminó luchando contra quienes intentaba salvar (fuente: Oolacile, DS1).',
  sources: [
    { title: 'Knight Artorias', game: 'DS1', url: 'https://darksouls.wiki.fextralife.com/Knight+Artorias' },
    { title: 'Oolacile', game: 'DS1', url: null },
  ],
  rejected: false,
}

const now = Date.now()
const history = [
  { id: 3, question: '¿Quién es Solaire de Astora?', answer: 'Solaire es un caballero de Astora que busca su propio sol…', sources: [{ title: 'Solaire of Astora', game: 'DS1' }], rejected: false, created_at: new Date(now - 26 * 3600e3).toISOString() },
  { id: 2, question: '¿Cuál es el mejor sushi de Tokio?', answer: REJECTION, sources: [], rejected: true, created_at: new Date(now - 2 * 3600e3).toISOString() },
  { id: 1, question: '¿Quién es Artorias?', ...ARTORIAS, created_at: new Date(now - 3 * 3600e3).toISOString() },
]

let documents = [
  { source: 'slave_knight_gael.md', type: 'texto', chunks: 14, created_at: new Date(now - 3600e3).toISOString() },
  { source: 'The COMPLETE Dark Souls Series Story Retrospective.mp4', type: 'video', chunks: 276, created_at: new Date(now - 2 * 86400e3).toISOString() },
  { source: 'ornstein_y_smough.png', type: 'imagen', chunks: 1, created_at: new Date(now - 2 * 86400e3).toISOString() },
  { source: 'Dark Souls Wiki (DS1 · DS2 · DS3)', type: 'wiki', chunks: 2112, created_at: new Date(now - 3 * 86400e3).toISOString(), base: true },
]

export async function getMe() {
  return { sub: 'demo', username: 'demo', email: 'demo@john-dark-soul.local', roles: ['user'] }
}

export async function sendQuestion(question) {
  await wait(1200)
  const offTopic = /sushi|pizza|weather|clima|fútbol|futbol/i.test(question)
  const result = offTopic ? { answer: REJECTION, sources: [], rejected: true } : ARTORIAS
  history.unshift({ id: history.length + 1, question, ...result, created_at: new Date().toISOString() })
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

export async function deleteDocument(source) {
  await wait(300)
  documents = documents.filter((d) => d.source !== source)
  return null
}

export async function uploadDocument(file, onProgress) {
  for (let p = 10; p <= 100; p += 15) {
    await wait(200)
    onProgress?.(Math.min(p, 100))
  }
  const chunks = Math.max(1, Math.round(file.size / 900))
  documents = [{ source: file.name, type: 'texto', chunks, created_at: new Date().toISOString() }, ...documents]
  return { source: file.name, chunks }
}
