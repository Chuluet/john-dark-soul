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
EXTENSIONES_SOPORTADAS = {
    ".pdf", ".txt", ".md", ".docx", ".csv", ".jpg", ".jpeg", ".png", ".mp4", ".mp3",
}

# Modelo de visión local: describe las imágenes para poder indexarlas.
VISION_MODEL = os.getenv("VISION_MODEL", "qwen2.5vl:3b")

# Modelo de Whisper para transcribir audio/video (tiny, base, small, medium).
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

# "auto" (GPU si hay, si no CPU), "cuda" o "cpu". La GPU necesita cuBLAS 12 y
# cuDNN 9: `uv sync --extra gpu` los instala. Si la GPU falla, se usa la CPU.
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")

# Nombres propios que Whisper suele escribir mal ("Framped" en vez de "Frampt").
# Se aplican a todo el audio, no solo al principio.
WHISPER_HOTWORDS = os.getenv(
    "WHISPER_HOTWORDS",
    "Gwyn, Gwynevere, Gwyndolin, Lordran, Anor Londo, Firelink Shrine, Sen's Fortress, "
    "Quelaag, Frampt, Kaathe, Ornstein, Smough, Artorias, Seath, Nito, Izalith, Manus, "
    "Oolacile, Lothric, Lorian, Drangleic, Vendrick, Aldia, Nashandra, Aldrich, Sulyvahn, "
    "Irithyll, Yhorm, Ludleth, Ashen One, Hollow, Undead",
)

# Duración de cada bloque de transcripción (cada bloque = una sección citable).
VIDEO_BLOQUE_SEGUNDOS = _int("VIDEO_BLOQUE_SEGUNDOS", 90)

# Tamaño máximo de un archivo subido por la API (POST /documents), en MB.
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 100)


# --- Recuperación y control de alucinaciones -------------------------------
RETRIEVER_K = _int("RETRIEVER_K", 5)

# Candidatos que se traen de pgvector por cada versión de la pregunta (la
# original y la reescrita en inglés) antes de quedarse con los K mejores.
RETRIEVER_FETCH_K = _int("RETRIEVER_FETCH_K", 40)

# Máximo de fragmentos del mismo archivo en el contexto: evita que una sola
# página (o el video) lo ocupe todo y deje fuera a la que responde.
RETRIEVER_MAX_POR_FUENTE = _int("RETRIEVER_MAX_POR_FUENTE", 1)

# Fragmentos por debajo de este puntaje se descartan; si no queda ninguno,
# el agente rechaza la pregunta.
SIMILARITY_THRESHOLD = _float("SIMILARITY_THRESHOLD", 0.46)


# --- Autenticación (Keycloak) -----------------------------------------------
# URL pública de Keycloak: es la que ve el navegador y la que aparece en el
# claim `iss` de los tokens.
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080").rstrip("/")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "john-dark-soul")

# Cliente del frontend: los tokens que emite traen `azp` igual a este valor.
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "frontend")

# URL desde la que el backend descarga las llaves públicas. En Docker es
# `http://keycloak:8080` (red interna); fuera de Docker coincide con la pública.
KEYCLOAK_INTERNAL_URL = os.getenv("KEYCLOAK_INTERNAL_URL", KEYCLOAK_URL).rstrip("/")

KEYCLOAK_ISSUER = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
KEYCLOAK_JWKS_URL = (
    f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
)


# --- API --------------------------------------------------------------------
# Orígenes permitidos por CORS, separados por coma (el frontend en desarrollo).
CORS_ORIGINS = [
    origen.strip()
    for origen in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origen.strip()
]
