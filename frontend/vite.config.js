import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Puerto 5173: es el que el cliente "frontend" de Keycloak acepta como redirect.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
})
