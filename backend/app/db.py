"""Tablas propias en PostgreSQL (las de pgvector las gestiona `vectorstore/`).

`messages` guarda cada interacción con el agente: es el historial que se
consulta por usuario. El checkpointer de LangGraph (InMemorySaver) solo vive
mientras corre el proceso; esta tabla sobrevive a los reinicios.

Cada mensaje lleva el `session_id` de su conversación: el menú "Recent" del
frontend las agrupa por él. Los mensajes guardados antes de existir la columna
quedan con NULL y cuentan como una conversación cada uno ('msg-<id>').

`documents` registra los archivos que cada usuario sube desde la web. Sus
fragmentos viven en pgvector con `fuente` igual a la columna `fuente`: así se
pueden borrar juntos.

`disabled_sources` guarda los documentos que cada usuario desactivó (de la
base original o suyos): el agente no los usa al responderle a ese usuario.
"""

from __future__ import annotations

import json

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app import config

_motor: Engine | None = None
_tablas_creadas = False

# Conversación de un mensaje; los antiguos (sin session_id) van cada uno aparte.
_SESION = "COALESCE(session_id, 'msg-' || id)"

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
    ALTER TABLE messages ADD COLUMN IF NOT EXISTS session_id TEXT;
    CREATE INDEX IF NOT EXISTS messages_user_session_idx ON messages (user_id, session_id);

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

    CREATE TABLE IF NOT EXISTS disabled_sources (
        user_id     TEXT        NOT NULL,
        fuente      TEXT        NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, fuente)
    );
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
    user_id: str,
    question: str,
    answer: str,
    sources: list[dict],
    rejected: bool,
    session_id: str | None = None,
) -> None:
    """Inserta una interacción (pregunta respondida o rechazada) en el historial."""
    init_db()
    with get_motor().begin() as conexion:
        conexion.execute(
            text(
                """
                INSERT INTO messages (user_id, session_id, question, answer, sources, rejected)
                VALUES (:user_id, :session_id, :question, :answer, CAST(:sources AS JSONB), :rejected)
                """
            ),
            {
                "user_id": user_id,
                "session_id": session_id,
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
                f"""
                SELECT id, {_SESION} AS session_id, question, answer, sources, rejected, created_at
                FROM messages
                WHERE user_id = :user_id
                ORDER BY created_at DESC, id DESC
                LIMIT :limite
                """
            ),
            {"user_id": user_id, "limite": limite},
        )
        return [dict(fila._mapping) for fila in filas]


def listar_conversaciones(user_id: str, limite: int = 20) -> list[dict]:
    """Conversaciones del usuario (título = su primera pregunta), la más reciente primero."""
    init_db()
    with get_motor().connect() as conexion:
        filas = conexion.execute(
            text(
                f"""
                SELECT {_SESION} AS session_id,
                       (array_agg(question ORDER BY created_at, id))[1] AS title,
                       max(created_at) AS updated_at,
                       count(*) AS messages
                FROM messages
                WHERE user_id = :user_id
                GROUP BY 1
                ORDER BY updated_at DESC
                LIMIT :limite
                """
            ),
            {"user_id": user_id, "limite": limite},
        )
        return [dict(fila._mapping) for fila in filas]


def mensajes_de_conversacion(user_id: str, session_id: str) -> list[dict]:
    """Mensajes de una conversación del usuario, en el orden en que se hicieron."""
    init_db()
    with get_motor().connect() as conexion:
        filas = conexion.execute(
            text(
                f"""
                SELECT id, {_SESION} AS session_id, question, answer, sources, rejected, created_at
                FROM messages
                WHERE user_id = :user_id AND {_SESION} = :session_id
                ORDER BY created_at, id
                """
            ),
            {"user_id": user_id, "session_id": session_id},
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
                RETURNING id, filename, fuente, tipo, juegos, chunks, created_at
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
                SELECT id, filename, fuente, tipo, juegos, chunks, created_at
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
        conexion.execute(
            text(
                """
                DELETE FROM disabled_sources
                WHERE fuente = (SELECT fuente FROM documents WHERE id = :id)
                """
            ),
            {"id": documento_id},
        )
        conexion.execute(text("DELETE FROM documents WHERE id = :id"), {"id": documento_id})


def fuentes_desactivadas(user_id: str) -> set[str]:
    """`fuente` de los documentos que el usuario desactivó."""
    init_db()
    with get_motor().connect() as conexion:
        filas = conexion.execute(
            text("SELECT fuente FROM disabled_sources WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        return {fila.fuente for fila in filas}


def cambiar_estado_fuente(user_id: str, fuente: str, activa: bool) -> None:
    """Activa (borra la fila) o desactiva (la inserta) un documento para el usuario."""
    init_db()
    sentencia = (
        "DELETE FROM disabled_sources WHERE user_id = :user_id AND fuente = :fuente"
        if activa
        else "INSERT INTO disabled_sources (user_id, fuente) VALUES (:user_id, :fuente) "
             "ON CONFLICT DO NOTHING"
    )
    with get_motor().begin() as conexion:
        conexion.execute(text(sentencia), {"user_id": user_id, "fuente": fuente})
