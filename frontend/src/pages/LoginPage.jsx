import { useAuth } from '../auth/AuthProvider'
import { Bonfire, Quote } from '../components/Decor'
import { LockIcon } from '../components/Icons'

export default function LoginPage() {
  const { login, register, error } = useAuth()
  return (
    <section className="login">
      <div className="login-panel">
        <Bonfire size={104} />
        <div className="login-title">
          <h1 className="cinzel">John Dark Soul</h1>
          <p className="serif">Ask about the history, characters and places of Dark Souls I, II and III.</p>
        </div>
        {error && <p className="notice notice-error" role="alert">{error}</p>}
        <div className="login-actions">
          <button type="button" className="btn btn-primary btn-lg" onClick={login}>Sign in</button>
          <button type="button" className="btn btn-ghost btn-lg" onClick={register}>Create account</button>
        </div>
        <Quote>Prepare to die</Quote>
        <p className="login-note">
          <LockIcon /> Authentication handled by Keycloak
        </p>
      </div>
    </section>
  )
}
