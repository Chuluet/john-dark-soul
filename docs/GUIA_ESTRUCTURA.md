# Guía de estructura — john-dark-soul

Qué debe contener cada carpeta y archivo del repositorio, según el enunciado del *Trabajo Agente* (Anexo A) y el stack del proyecto (FastAPI + LangGraph + Ollama + pgvector + Keycloak).

> Regla general: **cada capa solo habla con la de abajo.**
> `controllers → services → agents / vectorstore / db`

```
john-dark-soul/
├── backend/
│   ├── app/            configuración, arranque, seguridad, BD, schemas
│   ├── controllers/    endpoints HTTP (sin lógica)
│   ├── services/       lógica de negocio
│   ├── agents/         grafo LangGraph
│   ├── vectorstore/    embeddings + pgvector
│   ├── pyproject.toml / uv.lock
│   ├── Dockerfile
│   └── README.md
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── Dockerfile
│   └── README.md
├── docs/
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## backend/app/

Punto de entrada y todo lo transversal. No contiene lógica del agente.

| Archivo | Contenido |
|---|---|
| `main.py` | Crea `app = FastAPI()`, configura CORS, registra los routers de `controllers/`. Al arrancar: inicializa tablas y, si la base vectorial está vacía, llama a `ingest_service.seed_from_folder()`. Se ejecuta con `uv run uvicorn app.main:app`. |
| `config.py` | Lee variables de entorno (`.env`) y las expone en un objeto `settings`. Ningún otro archivo usa `os.getenv` directamente. |
| `security.py` | Dependencia `get_current_user()`: lee el header `Authorization: Bearer <token>`, valida el JWT contra las llaves públicas (JWKS) de Keycloak y devuelve el usuario (`sub`, `username`). Si el token es inválido → `401`. |
| `db.py` | Conexión a PostgreSQL (psycopg) y creación de las tablas propias: `documents` y `messages`. |
| `schemas.py` | Modelos Pydantic de entrada/salida: `ChatRequest`, `ChatResponse` (incluye `sources`), `DocumentOut`, `MessageOut`. |

Tablas sugeridas:

- `documents(id, user_id, filename, juego, created_at, chunks)`
- `messages(id, user_id, question, answer, sources, created_at)`

---

## backend/controllers/

Solo endpoints. Reciben la petición, llaman a un servicio y devuelven la respuesta. **Todos** usan `Depends(get_current_user)` (el enunciado exige que ningún endpoint quede expuesto).

| Archivo | Endpoints |
|---|---|
| `chat_controller.py` | `POST /chat` → pregunta al agente · `GET /chat/history` → historial del usuario |
| `documents_controller.py` | `POST /documents` (subida con `UploadFile`) · `GET /documents` · `DELETE /documents/{id}` |
| `auth_controller.py` | `GET /me` → devuelve el usuario autenticado (el registro/login lo hace Keycloak) |

Qué **no** va aquí: consultas a la BD, llamadas al LLM, splitting de texto.

---

## backend/services/

Lógica de negocio. Coordinan `agents/`, `vectorstore/` y `db`.

| Archivo | Responsabilidad |
|---|---|
| `ingest_service.py` | Flujo de carga (sección 2.4 del enunciado): **1.** recibir archivo → **2.** extraer texto (`.md`/`.txt` directo, `.pdf` con pypdf) → **3.** leer frontmatter de los `.md` (`title`, `juego`, `categoria`, `fuente`) como metadata → **4.** dividir con `RecursiveCharacterTextSplitter` → **5.** guardar en pgvector con `document_id` en la metadata → **6.** registrar en `documents` y devolver confirmación. También `seed_from_folder(path)` para cargar los `.md` de la wiki al arrancar. |
| `chat_service.py` | Recibe pregunta + usuario, invoca el grafo (`graph.invoke`) y arma la respuesta con fuentes. |
| `history_service.py` | Guardar y listar mensajes por usuario. |
| `document_service.py` | Listar documentos del usuario y eliminarlos (borra la fila **y** sus chunks en pgvector). |

---

## backend/agents/

El agente LangGraph. Es lo que más pesa en la rúbrica (LangGraph 15 % + control de alucinaciones 10 %).

| Archivo | Contenido |
|---|---|
| `state.py` | `TypedDict` del estado: `question`, `user_id`, `docs`, `sufficient`, `answer`, `sources`. |
| `llm.py` | Instancia de `ChatOllama` con el modelo local (`settings.LLM_MODEL`). |
| `prompts.py` | 1) Prompt de clasificación de intención (¿es sobre Dark Souls?). 2) Prompt de respuesta: *responde SOLO con el contexto; si no está, dilo*. 3) Mensaje de rechazo literal: **"No tengo suficiente información en mi base de conocimiento para responder esa pregunta."** |
| `nodes.py` | Una función por nodo (ver tabla abajo). |
| `graph.py` | Construye el `StateGraph`, conecta nodos y edges condicionales, y exporta `graph = builder.compile()`. |

Nodos (Anexo B del enunciado):

| Nodo | Qué hace | Siguiente |
|---|---|---|
| `validar_intencion` | El LLM clasifica si la pregunta es del dominio | sí → `recuperar` · no → `rechazar` |
| `recuperar` | Busca top-k en pgvector **con score** | `evaluar_contexto` |
| `evaluar_contexto` | Descarta docs bajo `SIMILARITY_THRESHOLD`; opcional: el LLM juzga si el contexto alcanza | suficiente → `generar` · no → `rechazar` |
| `generar` | Responde solo con el contexto y adjunta fuentes (`title`, `juego`, `fuente`) | `guardar_historial` |
| `rechazar` | Devuelve el mensaje de rechazo y sugiere subir documentos | `guardar_historial` |
| `guardar_historial` | Inserta en `messages` | `END` |

Estrategias anti-alucinación que quedan cubiertas (se piden mínimo 2): umbral de similitud, nodo de validación de contexto, prompt restrictivo, rechazo explícito, presentación de fuentes.

---

## backend/vectorstore/

Todo el acceso a la base vectorial. Nadie más importa `PGVector` directamente.

| Archivo | Contenido |
|---|---|
| `embeddings.py` | `OllamaEmbeddings(model=settings.EMBED_MODEL)` (p. ej. `nomic-embed-text`). |
| `store.py` | Crea el `PGVector` (`langchain-postgres`) y expone tres funciones: `add_documents(chunks)`, `search(query, k)` → lista de `(doc, score)`, `delete_by_document_id(id)`. |

Cada chunk guarda en metadata: `document_id`, `title`, `juego`, `categoria`, `fuente`.

---

## Archivos sueltos de backend/

| Archivo | Contenido |
|---|---|
| `pyproject.toml` / `uv.lock` | Dependencias (equivalen al `requirements.txt` del enunciado). Falta agregar `pyjwt[crypto]` para validar tokens. `requests` y `mwparserfromhell` solo hacen falta si el scraper vive aquí. |
| `Dockerfile` | Imagen con uv: copiar `pyproject.toml` + `uv.lock`, `uv sync --frozen`, copiar código, `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`. |
| `README.md` | Cómo correr solo el backend y lista de endpoints. |

---

## frontend/

| Carpeta / archivo | Contenido |
|---|---|
| `src/` | Páginas **Login**, **Chat** (interfaz tipo chatbot con fuentes bajo cada respuesta), **Documentos** (subir, listar, eliminar). Cliente de API que agrega el token a cada request. Integración con Keycloak (`keycloak-js`), rutas protegidas, botón de cerrar sesión, mensajes de error. |
| `public/` | Estáticos: favicon, imágenes. |
| `package.json` | Dependencias (React/Vite u otro). |
| `Dockerfile` | Build del front. |
| `README.md` | Cómo correr y desplegar el front. |

---

## docs/

| Archivo | Contenido |
|---|---|
| `arquitectura.png` | Diagrama: Usuario → Frontend → API protegida → Agente LangGraph → Ollama / pgvector, con Keycloak al lado. |
| `documento-tecnico.pdf` | Los 14 apartados de la sección 5.2 del enunciado. |
| `presentacion.pdf` | 8–12 diapositivas (sección 5.4). |
| `capturas/` | Capturas de pantalla (las pide la sección 5.1). |

---

## Raíz

| Archivo | Contenido |
|---|---|
| `docker-compose.yml` | Servicios: `db` (`pgvector/pgvector`), `ollama`, `keycloak`, `backend`, `frontend`. |
| `.env.example` | Variables sin valores reales (lista abajo). |
| `README.md` | Descripción, arquitectura, cómo ejecutar local, cómo desplegar, URLs públicas, capturas. |
| `.gitignore` | Ya está. |

Variables para `.env.example`:

```
DATABASE_URL=postgresql+psycopg://user:pass@db:5432/darksouls
OLLAMA_BASE_URL=http://ollama:11434
LLM_MODEL=llama3.1
EMBED_MODEL=nomic-embed-text
SIMILARITY_THRESHOLD=0.5
KEYCLOAK_URL=http://keycloak:8080
KEYCLOAK_REALM=john-dark-soul
KEYCLOAK_CLIENT_ID=frontend
CORS_ORIGINS=http://localhost:5173
```

---

## Sobre `firekeeper/`

Es la herramienta que descargó la wiki; no es parte de la estructura del enunciado. Sus `.md` (`data/wiki/`) se cargan a la base vectorial con `ingest_service.seed_from_folder()`. Las páginas dejadas en `EXCLUDE` (Gael, Ringed City, Midir…) sirven para la demo de "subir documento nuevo y preguntar".

---

## Orden sugerido de implementación

1. `app/config.py` + `docker-compose.yml` (db + ollama)
2. `vectorstore/` → probar búsquedas
3. `services/ingest_service.py` → cargar la wiki
4. `agents/` → grafo completo, probarlo por consola
5. `controllers/` + `app/main.py` → API
6. `app/security.py` + Keycloak
7. `frontend/`
8. Despliegue y `docs/`

## Referencias

- FastAPI por capas: https://levelup.gitconnected.com/structuring-fastapi-project-using-3-tier-design-pattern-4d2e88a55757
- FastAPI Bigger Applications: https://fastapi.tiangolo.com/tutorial/bigger-applications/
- LangGraph Agentic RAG: https://docs.langchain.com/oss/python/langgraph/agentic-rag
- PGVector: https://docs.langchain.com/oss/python/integrations/vectorstores/pgvector
- Ollama en LangChain: https://docs.langchain.com/oss/python/integrations/providers/ollama
- FastAPI + Keycloak: https://skycloak.io/blog/keycloak-fastapi-python-api-authentication/
- Ejemplo de repo FastAPI + LangGraph: https://github.com/JoshuaC215/agent-service-toolkit
