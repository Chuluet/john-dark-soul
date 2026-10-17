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
│   ├── auth.js         GET /me            (ya existe en el backend)
│   ├── chat.js         POST /chat, GET /chat/history     (por implementar)
│   ├── documents.js    GET/POST /documents, DELETE /documents/{source} (por implementar)
│   └── mock.js         datos de ejemplo para VITE_USE_MOCKS=true
├── components/         Layout (menú lateral), Decor (hoguera, ascuas, frases), Sources, Icons
├── pages/              LoginPage, ChatPage, HistoryPage, DocumentsPage
├── styles/app.css
└── assets/             fondo, ícono de la hoguera y personajes
```

## Contrato con el backend

Los endpoints de chat y documentos todavía no existen. Mientras falten, la
interfaz muestra "This feature isn't available on the server yet." (404).
Todos envían `Authorization: Bearer <token>`.

| Método | Ruta | Cuerpo | Respuesta |
|---|---|---|---|
| GET | `/me` | — | `{ sub, username, email, roles }` |
| POST | `/chat` | `{ question, session_id }` | `{ answer, sources: [{ title, game, url }], rejected }` |
| GET | `/chat/history` | — | `[{ id, question, answer, sources, rejected, created_at }]` |
| GET | `/documents` | — | `[{ source, type, chunks, created_at, base }]` |
| POST | `/documents` | multipart, campo `file` | `{ source, chunks }` |
| DELETE | `/documents/{source}` | — | 204 |

`POST /chat` corresponde a `agents/graph.py -> ask()`; si `error` no es `None`
debe responder 503. El historial sale de `app/db.py -> listar_mensajes()`.

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
