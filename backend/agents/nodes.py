"""Nodos del grafo: un paso del agente por función.

Igual que `assistant()` en el agente de voz del profesor, cada nodo recibe el
estado y devuelve un diccionario SOLO con las claves que actualiza; LangGraph
lo mezcla con el estado existente.

Los nodos que dependen de Ollama o Postgres capturan sus fallos y escriben
`error` en el estado: el grafo lo desvía a `handle_error` en vez de reventar o
de responder algo que no salió de la base de conocimiento.
"""

from __future__ import annotations

import logging

from app import config, db
from agents.llm import create_llm
from agents.prompts import (
    ANSWER_PROMPT,
    EVALUATION_PROMPT,
    INTENT_PROMPT,
    REJECTION_MESSAGES,
    REWRITE_PROMPT,
    rejection_message,
    service_error_message,
)
from agents.state import AgentState
from agents.tools import get_titles, search_documents
from agents.utils import (
    detect_language,
    expand_names,
    extract_sources,
    format_context,
    is_rejection,
    language_name,
    merge_results,
    message_text,
)

logger = logging.getLogger(__name__)


def _is_yes(response) -> bool:
    """True si el modelo respondió YES (tolera 'Yes.', 'yes', y 'SI'/'Sí' por si responde en español)."""
    return message_text(response).upper().startswith(("YES", "SI", "SÍ"))


def _error(node: str, exc: Exception) -> dict:
    """Registra el fallo y lo deja en el estado para que el grafo lo enrute."""
    logger.exception("Falló el nodo %s", node)
    return {"error": f"{node}: {type(exc).__name__}: {exc}"}


# --- Nodos ------------------------------------------------------------------

def validate_intent(state: AgentState) -> dict:
    """¿La pregunta es sobre el lore de Dark Souls? Si no, se rechaza sin buscar.

    También detecta el idioma de la pregunta (lo usan generate y reject) y
    limpia `error`, que el checkpointer arrastra de la pregunta anterior.
    """
    language = detect_language(state["question"])
    try:
        # prompt | llm: el ChatPromptTemplate rellena {question} y el resultado va al modelo.
        response = (INTENT_PROMPT | create_llm()).invoke({"question": state["question"]})
    except Exception as exc:  # noqa: BLE001 - Ollama caído o modelo sin descargar
        return {"language": language, "on_topic": False} | _error("validate_intent", exc)
    return {"on_topic": _is_yes(response), "language": language, "error": None}


def rewrite_query(state: AgentState) -> dict:
    """Versión en inglés de la pregunta, con los nombres oficiales, solo para buscar.

    El modelo traduce ('Vigilantes del Abismo' -> 'Abyss Watchers'); retrieve
    completa después los nombres cortos con los títulos de la wiki.
    """
    try:
        response = (REWRITE_PROMPT | create_llm()).invoke({"question": state["question"]})
        search_query = message_text(response).strip().strip('"')
    except Exception:  # noqa: BLE001 - si falla, se busca solo con la pregunta original
        search_query = state["question"]
    return {"search_query": search_query}


def retrieve(state: AgentState) -> dict:
    """Busca en la base vectorial. Se ejecuta SIEMPRE: no lo decide el modelo.

    Busca con la pregunta original, la reescrita y la reescrita con nombres
    completos: si una versión se equivoca, las otras siguen encontrando lo suyo.
    """
    queries = [state["question"]]
    search_query = state.get("search_query")
    if search_query:
        # El modelo no conoce todos los nombres completos: los títulos de la
        # wiki sí. Va como búsqueda aparte por si el reemplazo deforma la frase.
        queries += [search_query, expand_names(search_query, get_titles())]
    queries = list(dict.fromkeys(query for query in queries if query))  # sin repetidas

    try:
        # .invoke() de la @tool: la misma herramienta del profe, pero llamada por el grafo.
        result_lists = [
            search_documents.invoke({"query": query, "k": config.RETRIEVER_FETCH_K})
            for query in queries
        ]
    except Exception as exc:  # noqa: BLE001 - Postgres u Ollama (embeddings) caídos
        return {"docs": []} | _error("retrieve", exc)
    docs = merge_results(result_lists, config.RETRIEVER_K, config.RETRIEVER_MAX_POR_FUENTE)
    return {"docs": docs}


def evaluate_context(state: AgentState) -> dict:
    """Dos controles anti-alucinación: umbral de similitud + verificación por el LLM."""
    # 1) Umbral: se descartan los fragmentos poco parecidos a la pregunta.
    relevant = [
        (doc, score) for doc, score in state["docs"]
        if score >= config.SIMILARITY_THRESHOLD
    ]
    if not relevant:
        # Ninguno pasa el umbral: se rechaza sin gastar una llamada al LLM.
        return {"docs": [], "sufficient": False}

    # 2) El LLM revisa si lo que queda realmente responde la pregunta.
    try:
        response = (EVALUATION_PROMPT | create_llm()).invoke({
            "question": state["question"],
            "search_query": state.get("search_query") or state["question"],
            "context": format_context(relevant),
        })
    except Exception as exc:  # noqa: BLE001
        return {"sufficient": False} | _error("evaluate_context", exc)
    return {"docs": relevant, "sufficient": _is_yes(response)}


def generate(state: AgentState) -> dict:
    """Responde SOLO con el contexto recuperado y adjunta las fuentes usadas."""
    language = state.get("language", "en")
    try:
        response = (ANSWER_PROMPT | create_llm()).invoke({
            "question": state["question"],
            "context": format_context(state["docs"]),
            "language": language_name(language),
            "rejection": rejection_message(language),
        })
    except Exception as exc:  # noqa: BLE001
        return _error("generate", exc)

    answer = message_text(response)
    # Regla 5 del prompt: el modelo puede concluir que el contexto no alcanza.
    # Entonces es un rechazo y no se muestran fuentes que no respaldan nada.
    if is_rejection(answer, REJECTION_MESSAGES.values()):
        return {"answer": rejection_message(language), "sources": [], "rejected": True}
    return {"answer": answer, "sources": extract_sources(state["docs"]), "rejected": False}


def reject(state: AgentState) -> dict:
    """Rechazo explícito cuando no hay información suficiente (sección 3.1)."""
    return {
        "answer": rejection_message(state.get("language", "en")),
        "sources": [],
        "rejected": True,
    }


def handle_error(state: AgentState) -> dict:
    """Un servicio falló: se avisa sin responder nada del lore y no se guarda historial."""
    return {
        "answer": service_error_message(state.get("language", "en")),
        "sources": [],
        "rejected": False,
    }


def save_history(state: AgentState) -> dict:
    """Guarda la pregunta y la respuesta (o el rechazo) en la tabla `messages`.

    Sin `user_id` (pruebas por consola) no se guarda nada. Si Postgres falla,
    la respuesta ya está lista: se registra el error y no se pierde.
    """
    user_id = state.get("user_id")
    if not user_id:
        return {}
    try:
        db.guardar_mensaje(
            user_id=user_id,
            question=state["question"],
            answer=state["answer"],
            sources=state.get("sources", []),
            rejected=state.get("rejected", False),
        )
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo guardar el historial de %s", user_id)
    return {}


# --- Rutas (las usan los edges condicionales de graph.py) --------------------

def intent_route(state: AgentState) -> str:
    """Después de validate_intent: buscar, rechazar o manejar el error."""
    if state.get("error"):
        return "handle_error"
    return "rewrite_query" if state["on_topic"] else "reject"


def retrieve_route(state: AgentState) -> str:
    """Después de retrieve: evaluar el contexto o manejar el error."""
    return "handle_error" if state.get("error") else "evaluate_context"


def context_route(state: AgentState) -> str:
    """Después de evaluate_context: responder, rechazar o manejar el error."""
    if state.get("error"):
        return "handle_error"
    return "generate" if state["sufficient"] else "reject"


def generate_route(state: AgentState) -> str:
    """Después de generate: guardar el historial o manejar el error."""
    return "handle_error" if state.get("error") else "save_history"
