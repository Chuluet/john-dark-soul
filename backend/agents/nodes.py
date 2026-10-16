"""Nodos del grafo: un paso del agente por función.

Igual que `assistant()` en el agente de voz del profesor, cada nodo recibe el
estado y devuelve un diccionario SOLO con las claves que actualiza; LangGraph
lo mezcla con el estado existente.
"""

from __future__ import annotations

from app import config
from agents.llm import create_llm
from agents.prompts import (
    ANSWER_PROMPT,
    EVALUATION_PROMPT,
    INTENT_PROMPT,
    REWRITE_PROMPT,
    rejection_message,
)
from agents.state import AgentState
from agents.tools import get_titles, search_documents
from agents.utils import (
    detect_language,
    expand_names,
    extract_sources,
    format_context,
    language_name,
    merge_results,
    message_text,
)


def _is_yes(response) -> bool:
    """True si el modelo respondió YES (tolera 'Yes.', 'yes', y 'SI'/'Sí' por si responde en español)."""
    return message_text(response).upper().startswith(("YES", "SI", "SÍ"))


# --- Nodos ------------------------------------------------------------------

def validate_intent(state: AgentState) -> dict:
    """¿La pregunta es sobre el lore de Dark Souls? Si no, se rechaza sin buscar.

    También detecta el idioma de la pregunta: lo usan generate y reject.
    """
    # prompt | llm: el ChatPromptTemplate rellena {question} y el resultado va al modelo.
    response = (INTENT_PROMPT | create_llm()).invoke({"question": state["question"]})
    return {"on_topic": _is_yes(response), "language": detect_language(state["question"])}


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

    # .invoke() de la @tool: la misma herramienta del profe, pero llamada por el grafo.
    result_lists = [
        search_documents.invoke({"query": query, "k": config.RETRIEVER_FETCH_K})
        for query in queries
    ]
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
    response = (EVALUATION_PROMPT | create_llm()).invoke({
        "question": state["question"],
        "search_query": state.get("search_query") or state["question"],
        "context": format_context(relevant),
    })
    return {"docs": relevant, "sufficient": _is_yes(response)}


def generate(state: AgentState) -> dict:
    """Responde SOLO con el contexto recuperado y adjunta las fuentes usadas."""
    language = state.get("language", "en")
    response = (ANSWER_PROMPT | create_llm()).invoke({
        "question": state["question"],
        "context": format_context(state["docs"]),
        "language": language_name(language),
        "rejection": rejection_message(language),
    })
    return {
        "answer": message_text(response),
        "sources": extract_sources(state["docs"]),
    }


def reject(state: AgentState) -> dict:
    """Rechazo explícito cuando no hay información suficiente (sección 3.1)."""
    return {"answer": rejection_message(state.get("language", "en")), "sources": []}


def save_history(state: AgentState) -> dict:
    """Paso 6: guardará pregunta y respuesta en Postgres. Por ahora no hace nada."""
    return {}


# --- Rutas (las usan los edges condicionales de graph.py) --------------------

def intent_route(state: AgentState) -> str:
    """Después de validate_intent: buscar o rechazar."""
    return "rewrite_query" if state["on_topic"] else "reject"


def context_route(state: AgentState) -> str:
    """Después de evaluate_context: responder o rechazar."""
    return "generate" if state["sufficient"] else "reject"
