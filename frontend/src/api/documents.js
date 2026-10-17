import { config } from '../config'
import { getToken } from '../auth/keycloak'
import { ApiError, errorMessage, request } from './client'
import * as mock from './mock'

// Endpoints de controllers/documents_controller.py. Cada usuario ve y borra
// solo los archivos que subió; la base de conocimiento es compartida.

// GET /documents
// -> [{ id, filename, tipo, juegos, chunks, created_at }]  (más reciente primero)
//    tipo: "wiki" | "texto" | "pdf" | "docx" | "csv" | "imagen" | "video"
//    juegos: juegos detectados en el contenido, p. ej. ["DS3"]
export function listDocuments() {
  return config.useMocks ? mock.listDocuments() : request('/documents')
}

// DELETE /documents/{id}  -> 204 (404 si no existe o es de otro usuario)
export function deleteDocument(id) {
  if (config.useMocks) return mock.deleteDocument(id)
  return request(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// POST /documents  (multipart/form-data, campo "archivo")
// -> 201 { id, filename, tipo, juegos, chunks, created_at }
// Responde cuando el archivo ya está indexado. Errores: 413 (muy grande),
// 415 (formato), 422 (vacío o dañado), 503 (Ollama o Postgres caídos).
// Usa XMLHttpRequest en vez de fetch para poder mostrar el progreso de subida.
export async function uploadDocument(file, onProgress) {
  if (config.useMocks) return mock.uploadDocument(file, onProgress)

  const token = await getToken()
  const form = new FormData()
  form.append('archivo', file)

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${config.apiUrl}/documents`)
    xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(Math.round((e.loaded / e.total) * 100))
    xhr.onload = () => {
      let data = null
      try {
        data = JSON.parse(xhr.responseText)
      } catch {
        /* sin JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data)
      else reject(new ApiError(xhr.status, errorMessage(xhr.status, data?.detail)))
    }
    xhr.onerror = () => reject(new ApiError(0, 'Could not connect to the server.'))
    xhr.send(form)
  })
}
