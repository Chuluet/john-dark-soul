"""Preguntas al agente: invoca el grafo de LangGraph en nombre del usuario."""

from __future__ import annotations

from agents.graph import ask, build_graph
from services.errores import ServicioNoDisponible

# El grafo se compila una sola vez: su checkpointer (InMemorySaver) guarda el
# estado de cada conversación mientras corre el proceso.
_grafo = None


def _get_grafo():
    global _grafo
    if _grafo is None:
        _grafo = build_graph()
    return _grafo


def preguntar(user_id: str, pregunta: str, session_id: str) -> dict:
    """Respuesta del agente: {"answer", "sources", "rejected"}.

    El `thread_id` lleva el usuario delante: dos usuarios con el mismo
    `session_id` no comparten estado. El grafo guarda la interacción en el
    historial (nodo save_history).
    """
    resultado = ask(_get_grafo(), pregunta.strip(), f"{user_id}:{session_id}", user_id)
    if resultado["error"]:
        # Ollama o Postgres fallaron: `answer` trae el aviso en el idioma de la pregunta.
        raise ServicioNoDisponible(resultado["answer"])
    return {
        "answer": resultado["answer"],
        "sources": resultado["sources"],
        "rejected": resultado["rejected"],
    }
