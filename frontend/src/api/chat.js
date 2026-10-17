import { config } from '../config'
import { request } from './client'
import * as mock from './mock'

// Endpoints de controllers/chat_controller.py.

// POST /chat  { question, session_id }
// -> { answer, sources: [{ title, game, url }], rejected }
// rejected: true cuando el agente no tiene información suficiente (no es un error).
// Si Ollama o Postgres fallan el backend responde 503 (ApiError con status 503).
export function sendQuestion(question, sessionId) {
  if (config.useMocks) return mock.sendQuestion(question)
  return request('/chat', { method: 'POST', body: { question, session_id: sessionId } })
}

// GET /chat/history
// -> [{ id, question, answer, sources, rejected, created_at }]  (más reciente primero)
export function getHistory() {
  return config.useMocks ? mock.getHistory() : request('/chat/history')
}
