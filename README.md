# john-dark-soul

Agente inteligente con LangChain, LangGraph y RAG.

## Estructura

```
backend/    API (FastAPI), agente LangGraph, servicios y base vectorial
frontend/   Interfaz web
deploy/     Configuración del servidor (Caddy, .env de producción, Keycloak)
docs/       Arquitectura, documento técnico, presentación, capturas y despliegue
```

**Equipo:** Santiago Cardozo · Santiago Toro

| | |
|---|---|
| Aplicación | https://johndarksoul.netlify.app |
| API (Swagger) | https://api.13-58-191-152.sslip.io/docs |

## Arquitectura

![Arquitectura](docs/architecture.png)

## Documentación

| Archivo | Contenido |
|---|---|
| [docs/technical-document.pdf](docs/technical-document.pdf) | Documento técnico: los 14 apartados del enunciado |
| [docs/presentation.pdf](docs/presentation.pdf) | Diapositivas de la sustentación |
| [docs/architecture.png](docs/architecture.png) | Diagrama de arquitectura |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Guía de despliegue (Netlify + EC2) |
| [docs/screenshots/](docs/screenshots/) | Capturas de la aplicación desplegada |

| Login | Respuesta con fuentes |
|---|---|
| ![Login](docs/screenshots/login.png) | ![Respuesta](docs/screenshots/chat-answer.png) |
| **Pregunta rechazada** | **Carga de documentos** |
| ![Rechazo](docs/screenshots/chat-rejected.png) | ![Documentos](docs/screenshots/document-upload.png) |
| **Historial** | **API protegida (Swagger)** |
| ![Historial](docs/screenshots/history.png) | ![Swagger](docs/screenshots/swagger.png) |

## Agente (LangGraph)

Generado con `build_graph().get_graph().draw_mermaid()` (`backend/agents/graph.py`):

```mermaid
graph TD;
	__start__([start]) --> validate_intent;
	validate_intent -.->|del dominio| rewrite_query;
	validate_intent -.->|fuera del dominio| retrieve;
	validate_intent -.-> handle_error;
	rewrite_query --> retrieve;
	retrieve -.-> evaluate_context;
	retrieve -.-> handle_error;
	evaluate_context -.->|suficiente| generate;
	evaluate_context -.->|insuficiente| reject;
	evaluate_context -.-> handle_error;
	generate -.-> save_history;
	generate -.-> handle_error;
	reject --> save_history;
	save_history --> __end__([end]);
	handle_error --> __end__;
```

| Nodo | Qué hace |
|---|---|
| `validate_intent` | Clasifica si la pregunta es de Dark Souls y detecta el idioma (español o inglés). Decide **cómo** se busca, no **si** se busca: ninguna pregunta se rechaza sin consultar la base. |
| `rewrite_query` | Reescribe la pregunta en inglés con los nombres oficiales y resuelve referencias a la conversación ("who is his wolf" → "Who is Artorias's wolf?"). |
| `retrieve` | Búsqueda semántica en pgvector con la pregunta original y la reescrita; excluye los documentos que el usuario desactivó. |
| `evaluate_context` | Umbral de similitud (`SIMILARITY_THRESHOLD`) y verificación por el LLM de que los fragmentos responden la pregunta. |
| `generate` | Responde solo con los fragmentos y cita el archivo de cada dato. |
| `reject` | Mensaje explícito: "No tengo suficiente información en mi base de conocimiento…". |
| `save_history` | Guarda la interacción en la memoria de la sesión y en la tabla `messages`. |
| `handle_error` | Ollama o Postgres caídos: avisa sin inventar nada (la API responde 503). |

Control de alucinaciones: umbral mínimo de similitud, nodo dedicado a validar el contexto,
prompt que obliga a responder solo con lo recuperado, rechazo explícito y fuentes visibles
(el archivo que generó cada fragmento) en cada respuesta.

## Puesta en marcha local

### Requisitos
- Docker Desktop (con soporte de GPU NVIDIA vía WSL2)
- [uv](https://docs.astral.sh/uv/) para Python
- Si tienes PostgreSQL instalado en Windows, detenlo (usa el puerto 5432):
  `Stop-Service postgresql-x64-18` (PowerShell como administrador)

### 1. Configuración
Desde la raíz del proyecto (`john-dark-soul/`):

```powershell
copy .env.example .env        # luego cambia las contraseñas (Postgres y admin de Keycloak)
```

**Atajo: todo con Docker.** Con el `.env` listo y los modelos descargados (paso 3):

```powershell
docker compose up -d --build
```

Levanta Postgres, Ollama, Keycloak, backend y frontend; si la base vectorial está
vacía la llena con `backend/data/embeddings.dump`. La app queda en
http://localhost:5173 (usuario de prueba `demo` / `demo`) y la API en
http://localhost:8000/docs. Los pasos siguientes son para trabajar sin Docker en
el backend.

### 2. Levantar Postgres (pgvector) y Ollama

```powershell
docker compose up -d db ollama
```

### 3. Descargar los modelos locales

```powershell
docker compose exec ollama ollama pull qwen2.5:7b      # LLM del agente
docker compose exec ollama ollama pull bge-m3          # embeddings (multilingüe)
docker compose exec ollama ollama pull qwen2.5vl:3b    # visión (ingesta de imágenes)
docker compose exec ollama ollama list                 # verificar
docker compose exec ollama nvidia-smi                  # verificar GPU
```

### 4. Instalar dependencias del backend

```powershell
cd backend
uv sync
```

### 5. Cargar la base de conocimiento
Los documentos van en `backend/data/wiki/` (`.md`, `.txt`, `.pdf`, `.docx`, `.csv`, `.jpg`, `.png`, `.mp4`, `.mp3`).

```powershell
# Desde backend/
uv run python -m services.ingest_service --reset   # reconstruye desde cero
uv run python -m services.ingest_service           # agrega/actualiza sin borrar
```

**Alternativa: restaurar un respaldo** (evita repetir la ingesta, útil con videos largos).
El respaldo está versionado en `backend/data/embeddings.dump`. Con `docker compose up`
se restaura solo: el servicio `db-seed` lo carga si la base vectorial está vacía y no
hace nada si ya tiene datos (`docker compose logs db-seed` muestra qué hizo).
Para restaurarlo a mano, desde la raíz:

```powershell
docker compose exec db psql -U darksoul -d darksoul -c "CREATE EXTENSION IF NOT EXISTS vector"
docker compose cp ./backend/data/embeddings.dump db:/tmp/embeddings.dump
docker compose exec db pg_restore -U darksoul -d darksoul --no-owner --clean --if-exists /tmp/embeddings.dump
```

**Generar el respaldo** (desde la raíz):

```powershell
docker compose exec db pg_dump -U darksoul -d darksoul -Fc --no-owner -t langchain_pg_collection -t langchain_pg_embedding -f /tmp/embeddings.dump
docker compose cp db:/tmp/embeddings.dump ./backend/data/embeddings.dump
```

El respaldo solo incluye la base vectorial; el historial (`messages`) no se
exporta. La tabla `messages` se crea sola la primera vez que el agente guarda
una interacción.

### 6. Probar
Desde `backend/`:

```powershell
# Conexión a Postgres y número de fragmentos
uv run python -c "from vectorstore import vectorstore as v; print(v.comprobar_conexion()); print(v.contar_fragmentos())"

# Búsqueda semántica (puntaje de relevancia 0-1)
uv run python -c "from agents.tools import buscar_en_documentos as b; [print(round(s,3), d.metadata.get('title')) for d,s in b.invoke({'consulta': '¿Quién es Artorias?'})]"

# Agente completo: pregunta con respuesta
uv run python -c "from agents.graph import build_graph; g = build_graph(); r = g.invoke({'question': '¿Quién es Artorias?'}, {'configurable': {'thread_id': 'prueba'}}); print(r['answer']); print(r.get('sources'))"

# Con user_id la interacción se guarda en la tabla messages (historial)
uv run python -c "from agents.graph import build_graph, ask; print(ask(build_graph(), '¿Quién es Artorias?', 'prueba-h', user_id='demo'))"
uv run python -c "from app import db; [print(m['created_at'], m['rejected'], m['question']) for m in db.listar_mensajes('demo')]"

# Agente completo: pregunta fuera del dominio (debe rechazar)
uv run python -c "from agents.graph import build_graph; g = build_graph(); r = g.invoke({'question': '¿Cómo se prepara sushi?'}, {'configurable': {'thread_id': 'prueba2'}}); print(r['answer'])"

# Ver el recorrido por los nodos del grafo
uv run python -c "from agents.graph import build_graph; g = build_graph(); [print(p) for p in g.stream({'question': '¿Quién es Artorias?'}, {'configurable': {'thread_id': 'prueba3'}}, stream_mode='updates')]"

# Diagrama del grafo en Mermaid (pegar en https://mermaid.live)
uv run python -c "from agents.graph import build_graph; print(build_graph().get_graph().draw_mermaid())"
```

### 7. API

Requiere Keycloak arriba (`docker compose up -d keycloak`). Desde `backend/`:

```powershell
uv run uvicorn app.main:app --reload
```

Documentación interactiva en http://localhost:8000/docs (botón **Authorize** para pegar el token).
Todos los endpoints exigen `Authorization: Bearer <token>`; sin token responden 401.

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/me` | Usuario autenticado (`sub`, `username`, `email`, `roles`) |
| `POST` | `/chat` | `{"question", "session_id"?}` → `{"answer", "sources", "rejected"}` |
| `GET` | `/chat/history?limit=50` | Historial del usuario, del más reciente al más antiguo |
| `GET` | `/chat/conversations?limit=20` | Conversaciones del usuario (mensajes agrupados por `session_id`) |
| `GET` | `/chat/conversations/{session_id}` | Mensajes de una conversación, en orden |
| `POST` | `/documents` | Sube un archivo (`multipart`, campo `archivo`), lo indexa y lo registra |
| `GET` | `/documents` | Archivos subidos por el usuario, con `active` |
| `PATCH` | `/documents/{id}` | `{"active"}`: activa o desactiva un archivo subido |
| `DELETE` | `/documents/{id}` | Borra el archivo y sus fragmentos de la base vectorial |
| `GET` | `/documents/knowledge-base` | Archivos de la base original, con `active` |
| `PATCH` | `/documents/knowledge-base` | `{"source", "active"}`: activa o desactiva un archivo de la base |

Las fuentes de cada respuesta traen `document`: el archivo que generó los fragmentos.
Desactivar un documento solo afecta las respuestas de ese usuario (tabla `disabled_sources`).

Códigos de error: `401` sin token o token inválido · `404` documento inexistente o de otro
usuario · `413` archivo mayor a `MAX_UPLOAD_MB` · `415` formato no soportado · `422` archivo
vacío, dañado o sin texto útil · `503` Ollama o Postgres no responden.

La base de conocimiento es compartida: lo que sube un usuario lo usa el agente para todos,
pero cada usuario solo ve y borra sus propios archivos. Un rechazo del agente (sin información
suficiente) no es un error: responde `200` con `"rejected": true`.

```powershell
# Token del usuario de prueba y una pregunta
$t = Invoke-RestMethod -Method Post http://localhost:8080/realms/john-dark-soul/protocol/openid-connect/token -Body @{grant_type='password'; client_id='frontend'; username='demo'; password='demo'}
$h = @{Authorization = "Bearer $($t.access_token)"}
Invoke-RestMethod -Method Post http://localhost:8000/chat -Headers $h -ContentType 'application/json; charset=utf-8' -Body '{"question": "¿Quién es Artorias?"}'

# Subir un documento
curl.exe -H "Authorization: Bearer $($t.access_token)" -F "archivo=@C:\ruta\gael__DS3.pdf" http://localhost:8000/documents
```

### 8. Detener

```powershell
docker compose down        # conserva modelos y datos
docker compose down -v     # ⚠️ borra también modelos y base de datos
```

## Despliegue en la nube

Frontend en **Netlify** y backend (API, agente, Ollama, Postgres y Keycloak) en
una **EC2 de AWS** detrás de Caddy con HTTPS. La guía paso a paso está en
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Archivos de producción:
`netlify.toml`, `docker-compose.prod.yml` y la carpeta `deploy/`.
