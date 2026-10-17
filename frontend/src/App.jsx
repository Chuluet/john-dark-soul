import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthProvider'
import { Bonfire, Embers } from './components/Decor'
import Layout from './components/Layout'
import ChatPage from './pages/ChatPage'
import DocumentsPage from './pages/DocumentsPage'
import HistoryPage from './pages/HistoryPage'
import LoginPage from './pages/LoginPage'

export default function App() {
  const { ready, authenticated } = useAuth()

  return (
    <>
      <div className={`bg ${authenticated ? 'bg-app' : 'bg-login'}`} aria-hidden="true" />
      <Embers />
      <div className="content">
        {!ready ? (
          <div className="splash" role="status">
            <Bonfire size={72} />
            <span className="soft">Kindling the bonfire…</span>
          </div>
        ) : !authenticated ? (
          // Sin sesión no se ve ninguna ruta de la app: solo el login.
          <LoginPage />
        ) : (
          <Routes>
            <Route element={<Layout />}>
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="*" element={<Navigate to="/chat" replace />} />
            </Route>
          </Routes>
        )}
      </div>
    </>
  )
}
