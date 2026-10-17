import { config } from '../config'
import { getToken } from '../auth/keycloak'
import { ApiError, errorMessage, request } from './client'
import * as mock from './mock'

// Contrato pensado para el backend (aún no existe).

// GET /documents
// -> [{ source, type, chunks, created_at, base }]
//    source: ruta del archivo (metadato `fuente` en pgvector)
//    type: "wiki" | "texto" | "pdf" | "docx" | "csv" | "imagen" | "video"
//    base: true para los documentos de la wiki, que no se pueden borrar
export function listDocuments() {
  return config.useMocks ? mock.listDocuments() : request('/documents')
}

// DELETE /documents/{source}  -> 204
export function deleteDocument(source) {
  if (config.useMocks) return mock.deleteDocument(source)
  return request(`/documents/${encodeURIComponent(source)}`, { method: 'DELETE' })
}

// POST /documents  (multipart/form-data, campo "file")
// -> { source, chunks }
// Usa XMLHttpRequest en vez de fetch para poder mostrar el progreso de subida.
export async function uploadDocument(file, onProgress) {
  if (config.useMocks) return mock.uploadDocument(file, onProgress)

  const token = await getToken()
  const form = new FormData()
  form.append('file', file)

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
