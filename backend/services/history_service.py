"""Historial de conversaciones de cada usuario (tabla `messages`).

Los mensajes los guarda el propio grafo en su nodo `save_history`; aquí solo
se consultan.
"""

from app import db
from services.errores import NoEncontrado, fallos_de_servicio


def listar(user_id: str, limite: int) -> list[dict]:
    """Interacciones del usuario, de la más reciente a la más antigua."""
    with fallos_de_servicio("Could not load the history: the database is not responding."):
        return db.listar_mensajes(user_id, limite)


def conversaciones(user_id: str, limite: int) -> list[dict]:
    """Conversaciones del usuario, de la más reciente a la más antigua."""
    with fallos_de_servicio("Could not load the conversations: the database is not responding."):
        return db.listar_conversaciones(user_id, limite)


def conversacion(user_id: str, session_id: str) -> list[dict]:
    """Mensajes de una conversación del usuario, en orden; 404 si no tiene ninguno."""
    with fallos_de_servicio("Could not load the conversation: the database is not responding."):
        mensajes = db.mensajes_de_conversacion(user_id, session_id)
    if not mensajes:
        raise NoEncontrado("Conversation not found.")
    return mensajes
