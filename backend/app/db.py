"""Tablas propias en PostgreSQL (las de pgvector las gestiona `vectorstore/`).

`messages` guarda cada interacción con el agente: es el historial que se
consulta por usuario. El checkpointer de LangGraph (InMemorySaver) solo vive
mientras corre el proceso; esta tabla sobrevive a los reinicios.

`documents` registra los archivos que cada usuario sube desde la web. Sus
fragmentos viven en pgvector con `fuente` igual a la columna `fuente`: así se
pueden borrar juntos.
"""

from __future__ import annotations

import json

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app import config

_motor: Engine | None = None
_tablas_creadas = False

_CREAR_TABLAS = text(
    """
    CREATE TABLE IF NOT EXISTS messages (
        id          BIGSERIAL PRIMARY KEY,
        user_id     TEXT        NOT NULL,
        question    TEXT        NOT NULL,
        answer      TEXT        NOT NULL,
        sources     JSONB       NOT NULL DEFAULT '[]'::jsonb,
        rejected    BOOLEAN     NOT NULL DEFAULT FALSE,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS messages_user_created_idx ON messages (user_id, created_at DESC);

    CREATE TABLE IF NOT EXISTS documents (
        id          BIGSERIAL PRIMARY KEY,
        user_id     TEXT        NOT NULL,
        filename    TEXT        NOT NULL,
        fuente      TEXT        NOT NULL UNIQUE,
        tipo        TEXT        NOT NULL,
        juegos      JSONB       NOT NULL DEFAULT '[]'::jsonb,
        chunks      INTEGER     NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS documents_user_created_idx ON documents (user_id, created_at DESC);
    """
)


def get_motor() -> Engine:
    """Engine de SQLAlchemy reutilizable."""
    global _motor
    if _motor is None:
        _motor = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    return _motor


def init_db() -> None:
    """Crea las tablas propias si no existen. Se llama sola la primera vez que se usan."""
    global _tablas_creadas
    if _tablas_creadas:
        return
    with get_motor().begin() as conexion:
        conexion.execute(_CREAR_TABLAS)
    _tablas_creadas = True


def guardar_mensaje(
    user_id: str, question: str, answer: str, sources: list[dict], rejected: bool
) -> None:
    """Inserta una interacción (pregunta respondida o rechazada) en el historial."""
    init_db()
    with get_motor().begin() as conexion:
        conexion.execute(
            text(
                """
                INSERT INTO messages (user_id, question, answer, sources, rejected)
                VALUES (:user_id, :question, :answer, CAST(:sources AS JSONB), :rejected)
                """
            ),
            {
                "user_id": user_id,
                "question": question,
                "answer": answer,
                "sources": json.dumps(sources, ensure_ascii=False),
                "rejected": rejected,
            },
        )


def listar_mensajes(user_id: str, limite: int = 50) -> list[dict]:
    """Historial del usuario, del más reciente al más antiguo."""
    init_db()
    with get_motor().connect() as conexion:
        filas = conexion.execute(
            text(
                """
                SELECT id, question, answer, sources, rejected, created_at
                FROM messages
                WHERE user_id = :user_id
                ORDER BY created_at DESC, id DESC
                LIMIT :limite
                """
            ),
            {"user_id": user_id, "limite": limite},
        )
        return [dict(fila._mapping) for fila in filas]


def guardar_documento(
    user_id: str, filename: str, fuente: str, tipo: str, juegos: list[str], chunks: int
) -> dict:
    """Registra un archivo ya indexado y devuelve la fila creada."""
    init_db()
    with get_motor().begin() as conexion:
        fila = conexion.execute(
            text(
                """
                INSERT INTO documents (user_id, filename, fuente, tipo, juegos, chunks)
                VALUES (:user_id, :filename, :fuente, :tipo, CAST(:juegos AS JSONB), :chunks)
                RETURNING id, filename, tipo, juegos, chunks, created_at
                """
            ),
            {
                "user_id": user_id,
                "filename": filename,
                "fuente": fuente,
                "tipo": tipo,
                "juegos": json.dumps(juegos),
                "chunks": chunks,
            },
        ).one()
        return dict(fila._mapping)


def listar_documentos(user_id: str) -> list[dict]:
    """Archivos subidos por el usuario, del más reciente al más antiguo."""
    init_db()
    with get_motor().connect() as conexion:
        filas = conexion.execute(
            text(
                """
                SELECT id, filename, tipo, juegos, chunks, created_at
                FROM documents
                WHERE user_id = :user_id
                ORDER BY created_at DESC, id DESC
                """
            ),
            {"user_id": user_id},
        )
        return [dict(fila._mapping) for fila in filas]


def obtener_documento(documento_id: int, user_id: str) -> dict | None:
    """El documento si existe y es del usuario; None en otro caso."""
    init_db()
    with get_motor().connect() as conexion:
        fila = conexion.execute(
            text(
                """
                SELECT id, filename, fuente, tipo, juegos, chunks, created_at
                FROM documents
                WHERE id = :id AND user_id = :user_id
                """
            ),
            {"id": documento_id, "user_id": user_id},
        ).one_or_none()
        return dict(fila._mapping) if fila else None


def borrar_documento(documento_id: int) -> None:
    """Elimina la fila del documento (sus fragmentos se borran aparte)."""
    init_db()
    with get_motor().begin() as conexion:
        conexion.execute(text("DELETE FROM documents WHERE id = :id"), {"id": documento_id})
