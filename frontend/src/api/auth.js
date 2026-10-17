import { config } from '../config'
import { request } from './client'
import * as mock from './mock'

// GET /me (ya existe en el backend: controllers/auth_controller.py)
// -> { sub, username, email, roles }
export function getMe() {
  return config.useMocks ? mock.getMe() : request('/me')
}
