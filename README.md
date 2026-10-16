# john-dark-soul

Agente inteligente con LangChain, LangGraph y RAG.

## Estructura

```
backend/    API (FastAPI), agente LangGraph, servicios y base vectorial
frontend/   Interfaz web
docs/       Arquitectura, documento técnico y presentación
```

## Puesta en marcha local

### Requisitos
- Docker Desktop (con soporte de GPU NVIDIA vía WSL2)
- [uv](https://docs.astral.sh/uv/) para Python
- Si tienes PostgreSQL instalado en Windows, detenlo (usa el puerto 5432):
  `Stop-Service postgresql-x64-18` (PowerShell como administrador)

### 1. Configuración
Desde la raíz del proyecto (`john-dark-soul/`):

```powershell
copy .env.example .env        # luego edita la contraseña de Postgres
```

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
Los documentos van en `backend/data/wiki/` (`.md`, `.txt`, `.pdf`, `.jpg`, `.png`, `.mp4`, `.mp3`).

```powershell
# Desde backend/
uv run python -m services.ingest_service --reset   # reconstruye desde cero
uv run python -m services.ingest_service           # agrega/actualiza sin borrar
```

**Alternativa: restaurar un respaldo** (evita repetir la ingesta, útil con videos largos).
Desde la raíz, con el archivo en `data/embeddings.dump`:

```powershell
docker compose exec db psql -U darksoul -d darksoul -c "CREATE EXTENSION IF NOT EXISTS vector"
docker compose cp ./data/embeddings.dump db:/tmp/embeddings.dump
docker compose exec db pg_restore -U darksoul -d darksoul --no-owner --clean --if-exists /tmp/embeddings.dump
```

**Generar el respaldo** (desde la raíz):

```powershell
New-Item -ItemType Directory -Force data
docker compose exec db pg_dump -U darksoul -d darksoul -Fc --no-owner -t langchain_pg_collection -t langchain_pg_embedding -f /tmp/embeddings.dump
docker compose cp db:/tmp/embeddings.dump ./data/embeddings.dump
```

### 6. Probar
Desde `backend/`:

```powershell
# Conexión a Postgres y número de fragmentos
uv run python -c "from vectorstore import vectorstore as v; print(v.comprobar_conexion()); print(v.contar_fragmentos())"

# Búsqueda semántica (puntaje de relevancia 0-1)
uv run python -c "from agents.tools import buscar_en_documentos as b; [print(round(s,3), d.metadata.get('title')) for d,s in b.invoke({'consulta': '¿Quién es Artorias?'})]"

# Agente completo: pregunta con respuesta
uv run python -c "from agents.graph import build_graph; g = build_graph(); r = g.invoke({'question': '¿Quién es Artorias?'}, {'configurable': {'thread_id': 'prueba'}}); print(r['answer']); print(r.get('sources'))"

# Agente completo: pregunta fuera del dominio (debe rechazar)
uv run python -c "from agents.graph import build_graph; g = build_graph(); r = g.invoke({'question': '¿Cómo se prepara sushi?'}, {'configurable': {'thread_id': 'prueba2'}}); print(r['answer'])"

# Ver el recorrido por los nodos del grafo
uv run python -c "from agents.graph import build_graph; g = build_graph(); [print(p) for p in g.stream({'question': '¿Quién es Artorias?'}, {'configurable': {'thread_id': 'prueba3'}}, stream_mode='updates')]"

# Diagrama del grafo en Mermaid (pegar en https://mermaid.live)
uv run python -c "from agents.graph import build_graph; print(build_graph().get_graph().draw_mermaid())"
```

### 7. Detener

```powershell
docker compose down        # conserva modelos y datos
docker compose down -v     # ⚠️ borra también modelos y base de datos
```
