"""Preguntas al agente: invoca el grafo de LangGraph en nombre del usuario."""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, HumanMessage

from agents.graph import ask, build_graph, has_memory
from agents.prompts import DEFAULT_LANGUAGE, service_error_message
from app import db
from services.errores import ServicioNoDisponible

logger = logging.getLogger(__name__)

# El grafo se compila una sola vez: su checkpointer (InMemorySaver) guarda el
# estado de cada conversación mientras corre el proceso.
_grafo = None


def _get_grafo():
    global _grafo
    if _grafo is None:
        _grafo = build_graph()
    return _grafo


def _historial_guardado(user_id: str, session_id: str) -> list:
    """Mensajes ya guardados de la conversación, para retomarla tras un reinicio.

    El checkpointer vive en memoria: si el backend se reinició (o el usuario
    abre una conversación vieja desde "Recent"), las preguntas de seguimiento
    ("¿y su lobo?") necesitan lo que se habló antes. Si Postgres falla se
    sigue sin historial: la pregunta todavía se puede responder.
    """
    try:
        filas = db.mensajes_de_conversacion(user_id, session_id)
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo leer la conversación %s", session_id)
        return []
    mensajes = []
    for fila in filas:
        mensajes += [HumanMessage(fila["question"]), AIMessage(fila["answer"])]
    return mensajes


def preguntar(user_id: str, pregunta: str, session_id: str) -> dict:
    """Respuesta del agente: {"answer", "sources", "rejected"}.

    El `thread_id` lleva el usuario delante: dos usuarios con el mismo
    `session_id` no comparten estado. El grafo guarda la interacción en el
    historial (nodo save_history) con su `session_id`.
    """
    grafo = _get_grafo()
    sesion = f"{user_id}:{session_id}"
    historial = None if has_memory(grafo, sesion) else _historial_guardado(user_id, session_id)
    resultado = ask(grafo, pregunta.strip(), sesion, user_id, session_id, historial)
    if resultado["error"]:
        # Ollama o Postgres fallaron. Los errores de la API van siempre en el
        # idioma por defecto, aunque la pregunta esté en otro.
        raise ServicioNoDisponible(service_error_message(DEFAULT_LANGUAGE))
    return {
        "answer": resultado["answer"],
        "sources": resultado["sources"],
        "rejected": resultado["rejected"],
    }
