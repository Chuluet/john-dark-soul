import { config } from '../config'
import { request } from './client'
import * as mock from './mock'

// Endpoints de controllers/chat_controller.py.

// POST /chat  { question, session_id }
// -> { answer, sources: [{ title, game, document }], rejected }
//    document: archivo de la base de conocimiento del que salió la respuesta
// rejected: true cuando el agente no tiene información suficiente (no es un error).
// Si Ollama o Postgres fallan el backend responde 503 (ApiError con status 503).
export function sendQuestion(question, sessionId) {
  if (config.useMocks) return mock.sendQuestion(question, sessionId)
  return request('/chat', { method: 'POST', body: { question, session_id: sessionId } })
}

// GET /chat/history
// -> [{ id, session_id, question, answer, sources, rejected, created_at }]  (más reciente primero)
export function getHistory() {
  return config.useMocks ? mock.getHistory() : request('/chat/history')
}

// GET /chat/conversations
// -> [{ session_id, title, updated_at, messages }]  (más reciente primero)
//    title: primera pregunta de la conversación
export function getConversations(limit = 5) {
  return config.useMocks ? mock.getConversations(limit) : request(`/chat/conversations?limit=${limit}`)
}

// GET /chat/conversations/{session_id}
// -> mismos campos que /chat/history, del más antiguo al más reciente (404 si no existe)
export function getConversation(sessionId) {
  if (config.useMocks) return mock.getConversation(sessionId)
  return request(`/chat/conversations/${encodeURIComponent(sessionId)}`)
}
