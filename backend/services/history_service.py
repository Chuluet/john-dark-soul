"""Historial de conversaciones de cada usuario (tabla `messages`).

Los mensajes los guarda el propio grafo en su nodo `save_history`; aquí solo
se consultan.
"""

from app import db
from services.errores import fallos_de_servicio


def listar(user_id: str, limite: int) -> list[dict]:
    """Interacciones del usuario, de la más reciente a la más antigua."""
    with fallos_de_servicio("Could not load the history: the database is not responding."):
        return db.listar_mensajes(user_id, limite)
