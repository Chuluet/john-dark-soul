import { config } from '../config'
import { request } from './client'
import * as mock from './mock'

// Contrato pensado para el backend (aún no existe). Coincide con lo que
// devuelve agents/graph.py -> ask() y con la tabla `messages` de app/db.py.

// POST /chat  { question, session_id }
// -> { answer, sources: [{ title, game, url }], rejected }
// Si un servicio falla el backend responde 503 (ApiError con status 503).
export function sendQuestion(question, sessionId) {
  if (config.useMocks) return mock.sendQuestion(question)
  return request('/chat', { method: 'POST', body: { question, session_id: sessionId } })
}

// GET /chat/history
// -> [{ id, question, answer, sources, rejected, created_at }]  (más reciente primero)
export function getHistory() {
  return config.useMocks ? mock.getHistory() : request('/chat/history')
}
