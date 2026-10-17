import Keycloak from 'keycloak-js'
import { config } from '../config'

// Una sola instancia para toda la app (keycloak-js no permite inicializarla dos veces).
export const keycloak = new Keycloak(config.keycloak)

let initPromise = null

// check-sso: si ya hay sesión en Keycloak entra directo; si no, muestra el login
// propio de la app en lugar de redirigir de inmediato.
export function initKeycloak() {
  if (!initPromise) {
    initPromise = keycloak.init({
      onLoad: 'check-sso',
      pkceMethod: 'S256', // el cliente "frontend" del realm exige PKCE
      silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
      checkLoginIframe: false,
    })
    // Renueva el token cuando expira (dura 15 min en el realm).
    keycloak.onTokenExpired = () => {
      keycloak.updateToken(30).catch(() => keycloak.login())
    }
  }
  return initPromise
}

// Token vigente para el header Authorization (lo renueva si le quedan < 30 s).
export async function getToken() {
  if (config.useMocks) return 'mock-token'
  await keycloak.updateToken(30)
  return keycloak.token
}
