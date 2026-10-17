"""Tablas propias en PostgreSQL (las de pgvector las gestiona `vectorstore/`).

`messages` guarda cada interacción con el agente: es el historial que se
consulta por usuario. El checkpointer de LangGraph (InMemorySaver) solo vive
mientras corre el proceso; esta tabla sobrevive a los reinicios.
"""

from __future__ import annotations

import json

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app import config

_motor: Engine | None = None
_tablas_creadas = False

_CREAR_MESSAGES = text(
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
        conexion.execute(_CREAR_MESSAGES)
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
