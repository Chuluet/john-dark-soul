"""Configuración central del proyecto.

Todo se lee de variables de entorno para que el mismo código funcione
dentro de Docker (host `db`, `ollama`) y fuera de él (`localhost`).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Raíz del backend (backend/ en local, /app en Docker): las rutas relativas
# se resuelven desde aquí y no desde el directorio de trabajo.
BASE_DIR = Path(__file__).resolve().parent.parent


def _int(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, "") or defecto)
    except ValueError:
        return defecto


def _float(nombre: str, defecto: float) -> float:
    try:
        return float(os.getenv(nombre, "") or defecto)
    except ValueError:
        return defecto


# --- Modelos servidos por Ollama -------------------------------------------
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")

# bge-m3 es multilingüe (1024 dimensiones): permite preguntar en español
# sobre la wiki, que está en inglés.
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")

# Temperatura baja: en RAG queremos fidelidad al contexto, no creatividad.
TEMPERATURE = _float("TEMPERATURE", 0.1)


# --- PostgreSQL + pgvector --------------------------------------------------
# En Docker el compose la sobrescribe con el host `db`.
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://darksoul:darksoul@localhost:5432/darksoul"
)
PG_COLLECTION = os.getenv("PG_COLLECTION", "darksouls")


# --- Ingesta de documentos --------------------------------------------------
DOCS_PATH = BASE_DIR / os.getenv("DOCS_PATH", "data/wiki")
CHUNK_SIZE = _int("CHUNK_SIZE", 1000)
CHUNK_OVERLAP = _int("CHUNK_OVERLAP", 150)
EXTENSIONES_SOPORTADAS = {".pdf", ".txt", ".md", ".jpg", ".jpeg", ".png", ".mp4", ".mp3"}

# Modelo de visión local: describe las imágenes para poder indexarlas.
VISION_MODEL = os.getenv("VISION_MODEL", "qwen2.5vl:3b")

# Modelo de Whisper para transcribir audio/video (tiny, base, small, medium).
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")


# --- Recuperación y control de alucinaciones -------------------------------
RETRIEVER_K = _int("RETRIEVER_K", 4)

# Fragmentos por debajo de este puntaje se descartan; si no queda ninguno,
# el agente rechaza la pregunta.
SIMILARITY_THRESHOLD = _float("SIMILARITY_THRESHOLD", 0.5)