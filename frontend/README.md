# Frontend

Interfaz web de John Dark Soul en React + Vite: login con Keycloak, chat con el
agente, historial y carga de documentos.

## Ejecutar en local

```bash
cd frontend
cp .env.example .env.local   # ajusta las URLs si hace falta
npm install
npm run dev                  # http://localhost:5173
```

Necesita Keycloak arriba (`docker compose up -d keycloak` desde la raíz). El
realm `john-dark-soul` ya trae el cliente `frontend` (redirect a
`http://localhost:5173/*`, PKCE) y el usuario de prueba `demo` / `demo`.

Para ver la interfaz sin Keycloak ni backend, pon `VITE_USE_MOCKS=true` en
`.env.local`: el login entra directo con un usuario de ejemplo y las respuestas,
el historial y los documentos son datos de prueba (`src/api/mock.js`).

## Estructura

```
src/
├── main.jsx            arranque: router + AuthProvider
├── App.jsx             rutas; sin sesión solo se ve el login
├── config.js           variables VITE_* y formatos aceptados
├── auth/
│   ├── keycloak.js     instancia de keycloak-js, init (check-sso + PKCE), token
│   └── AuthProvider.jsx  estado de sesión: login, register, logout, usuario
├── api/
│   ├── client.js       fetch con el token y errores legibles (401, 404, 503…)
│   ├── auth.js         GET /me
│   ├── chat.js         POST /chat, GET /chat/history, GET /chat/conversations
│   ├── documents.js    /documents y /documents/knowledge-base
│   └── mock.js         datos de ejemplo para VITE_USE_MOCKS=true
├── components/         Layout (menú lateral), Decor (hoguera, ascuas, frases), Sources, Icons
├── pages/              LoginPage, ChatPage, HistoryPage, DocumentsPage
├── styles/app.css
└── assets/             fondo, ícono de la hoguera y personajes
```

## Contrato con el backend

Todos envían `Authorization: Bearer <token>`; con un 401 la app vuelve al login
de Keycloak. Los errores muestran el `detail` que manda el backend.

| Método | Ruta | Cuerpo | Respuesta |
|---|---|---|---|
| GET | `/me` | — | `{ sub, username, email, roles }` |
| POST | `/chat` | `{ question, session_id }` | `{ answer, sources: [{ title, game, document }], rejected }` |
| GET | `/chat/history` | — | `[{ id, session_id, question, answer, sources, rejected, created_at }]` |
| GET | `/chat/conversations` | — | `[{ session_id, title, updated_at, messages }]` |
| GET | `/chat/conversations/{session_id}` | — | mensajes de la conversación, del más antiguo al más reciente |
| GET | `/documents` | — | `[{ id, filename, tipo, juegos, chunks, active, created_at }]` |
| POST | `/documents` | multipart, campo `archivo` | `201 { id, filename, tipo, juegos, chunks, active, created_at }` |
| PATCH | `/documents/{id}` | `{ active }` | 204 |
| DELETE | `/documents/{id}` | — | 204 |
| GET | `/documents/knowledge-base` | — | `[{ source, title, tipo, juegos, chunks, active }]` |
| PATCH | `/documents/knowledge-base` | `{ source, active }` | 204 |

- Un rechazo del agente no es un error: `POST /chat` responde 200 con `rejected: true`.
- "Recent" del menú lista conversaciones; al abrir una, las preguntas nuevas
  siguen en el mismo `session_id`.
- `GET /documents` lista solo los archivos que subió el usuario; la base original
  sale en `GET /documents/knowledge-base`. Desactivar un documento solo cambia
  las respuestas de ese usuario.
- Errores de la subida: 413 (mayor a `MAX_UPLOAD_MB`), 415 (formato), 422 (vacío o
  dañado), 503 (Ollama o Postgres caídos). La respuesta llega cuando el archivo ya
  está indexado, así que audio y video tardan.

## Docker

```bash
docker build -t darksoul-frontend \
  --build-arg VITE_API_URL=http://localhost:8000 \
  --build-arg VITE_KEYCLOAK_URL=http://localhost:8080 .
docker run -p 5173:80 darksoul-frontend
```

## Créditos

Personajes chibi: fan art de **inkinesss**. Dark Souls es propiedad de
FromSoftware y Bandai Namco.
