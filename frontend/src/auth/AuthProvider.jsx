import { createContext, useContext, useEffect, useState } from 'react'
import { config } from '../config'
import { initKeycloak, keycloak } from './keycloak'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [state, setState] = useState({ ready: false, authenticated: false, user: null, error: null })

  useEffect(() => {
    if (config.useMocks) {
      setState({ ready: true, authenticated: false, user: null, error: null })
      return
    }
    initKeycloak()
      .then((authenticated) => setState({ ready: true, authenticated, user: userFromToken(), error: null }))
      .catch(() =>
        setState({ ready: true, authenticated: false, user: null, error: 'Could not connect to the authentication server.' }),
      )
  }, [])

  const redirectUri = `${window.location.origin}/chat`

  const value = {
    ...state,
    login: () =>
      config.useMocks
        ? setState((s) => ({ ...s, authenticated: true, user: { username: 'demo', email: 'demo@john-dark-soul.local' } }))
        : keycloak.login({ redirectUri }),
    register: () => (config.useMocks ? value.login() : keycloak.register({ redirectUri })),
    logout: () =>
      config.useMocks
        ? setState((s) => ({ ...s, authenticated: false, user: null }))
        : keycloak.logout({ redirectUri: `${window.location.origin}/` }), // debe calzar con post.logout.redirect.uris del realm
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}

// Datos del usuario sacados del token (los mismos que devuelve GET /me).
function userFromToken() {
  const t = keycloak.tokenParsed
  if (!t) return null
  return { sub: t.sub, username: t.preferred_username || t.sub, email: t.email }
}
