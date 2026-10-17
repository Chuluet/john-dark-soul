// Configuración leída de las variables VITE_* (.env.local en desarrollo).
export const config = {
  apiUrl: (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, ''),
  keycloak: {
    url: import.meta.env.VITE_KEYCLOAK_URL || 'http://localhost:8080',
    realm: import.meta.env.VITE_KEYCLOAK_REALM || 'john-dark-soul',
    clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'frontend',
  },
  useMocks: import.meta.env.VITE_USE_MOCKS === 'true',
}

// Mismos formatos que EXTENSIONES_SOPORTADAS del backend (app/config.py).
export const ACCEPTED_EXTENSIONS = [
  '.pdf', '.txt', '.md', '.docx', '.csv', '.jpg', '.jpeg', '.png', '.mp3', '.mp4',
]
