// Cliente HTTP del backend: agrega el token de Keycloak y traduce los errores
// a mensajes que se pueden mostrar al usuario.
import { config } from '../config'
import { getToken, keycloak } from '../auth/keycloak'

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

const MESSAGES = {
  404: "This feature isn't available on the server yet.",
  413: 'The file is too large.',
  415: 'File type not supported.',
  503: 'The agent is not available right now. Please try again in a few moments.',
}

export function errorMessage(status, detail) {
  if (typeof detail === 'string' && detail) return detail
  return MESSAGES[status] || `Unexpected server error (${status}).`
}

export async function request(path, { method = 'GET', body } = {}) {
  const token = await getToken()
  const isForm = body instanceof FormData
  let response
  try {
    response = await fetch(`${config.apiUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body && !isForm ? { 'Content-Type': 'application/json' } : {}),
      },
      body: isForm ? body : body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Could not connect to the server.')
  }

  if (response.status === 401) {
    keycloak.login()
    throw new ApiError(401, 'Your session expired. Please sign in again.')
  }
  if (!response.ok) {
    let detail
    try {
      detail = (await response.json()).detail
    } catch {
      /* respuesta sin JSON */
    }
    throw new ApiError(response.status, errorMessage(response.status, detail))
  }
  return response.status === 204 ? null : response.json()
}
