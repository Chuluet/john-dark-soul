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

from langchain_core.messages import AIMessage, HumanMessage

from app import config, db
from agents.llm import create_llm
from agents.prompts import (
    ANSWER_PROMPT,
    EVALUATION_PROMPT,
    INTENT_PROMPT,
    REJECTION_MESSAGES,
    REWRITE_PROMPT,
    citation_word,
    rejection_message,
    service_error_message,
)
from agents.state import AgentState
from agents.tools import get_names, get_titles, search_documents
from agents.utils import (
    detect_language,
    expand_names,
    extract_sources,
    format_context,
    format_history,
    is_rejection,
    language_name,
    known_names_in,
    merge_results,
    rare_names,
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
    """¿La pregunta es sobre el lore de Dark Souls? Decide CÓMO se busca, no SI se busca.

    Con YES la pregunta se reescribe (traducción, nombres oficiales, "his" ->
    "Artorias") antes de buscar. Con NO se busca igual, con la pregunta tal
    cual: el clasificador no conoce todos los nombres del juego (Midir, Gael)
    ni los temas de los documentos que suben los usuarios, así que nunca
    rechaza solo. Rechazan el umbral y evaluate_context, que miran lo que la
    base devolvió.

    También detecta el idioma de la pregunta (lo usan generate y reject) y
    limpia `error` y `search_query`, que el checkpointer arrastra de la
    pregunta anterior.
    """
    language = detect_language(state["question"])
    reset = {"language": language, "search_query": None}
    try:
        # prompt | llm: el ChatPromptTemplate rellena {question} y el resultado va al modelo.
        response = (INTENT_PROMPT | create_llm()).invoke({
            "question": state["question"],
            "history": format_history(state.get("messages")),
        })
    except Exception as exc:  # noqa: BLE001 - Ollama caído o modelo sin descargar
        return reset | {"on_topic": False} | _error("validate_intent", exc)
    # Si la pregunta nombra algo de la base ("quien es la gael"), también se
    # reescribe: buscar la frase en español sin traducir no encuentra a Gael.
    on_topic = _is_yes(response) or bool(known_names_in(state["question"], get_names()))
    return reset | {"on_topic": on_topic, "error": None}


def rewrite_query(state: AgentState) -> dict:
    """Versión en inglés de la pregunta, con los nombres oficiales, solo para buscar.

    El modelo traduce ('Vigilantes del Abismo' -> 'Abyss Watchers'); retrieve
    completa después los nombres cortos con los títulos de la wiki.
    """
    try:
        # Con el historial, "¿y su lobo?" se reescribe como "Who was Artorias' wolf?".
        response = (REWRITE_PROMPT | create_llm()).invoke({
            "question": state["question"],
            "history": format_history(state.get("messages")),
        })
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
        # Documentos que el usuario apagó en la página Documents.
        user_id = state.get("user_id")
        excluded = sorted(db.fuentes_desactivadas(user_id)) if user_id else []
        # .invoke() de la @tool: la misma herramienta del profe, pero llamada por el grafo.
        result_lists = [
            search_documents.invoke({"query": query, "k": config.RETRIEVER_FETCH_K, "excluded": excluded})
            for query in queries
        ]
    except Exception as exc:  # noqa: BLE001 - Postgres u Ollama (embeddings) caídos
        return {"docs": []} | _error("retrieve", exc)
    docs = merge_results(result_lists, config.RETRIEVER_K, config.RETRIEVER_MAX_POR_FUENTE)
    return {"docs": docs}


def evaluate_context(state: AgentState) -> dict:
    """Dos controles anti-alucinación: umbral de similitud + verificación por el LLM."""
    # 1) Umbral: se descartan los fragmentos poco parecidos a la pregunta.
    # Un nombre suelto ("who is gael") se parece poco a cualquier fragmento:
    # entre el piso y el umbral se aceptan los que nombran lo que se pregunta.
    # Solo nombres poco frecuentes: 'Dark Souls' sale en casi todo y no dice nada.
    names = known_names_in(
        f"{state['question']} {state.get('search_query') or ''}", rare_names(get_names())
    )
    relevant = [
        (doc, score) for doc, score in state["docs"]
        if score >= config.SIMILARITY_THRESHOLD
        or (score >= config.SIMILARITY_FLOOR and known_names_in(doc.page_content, names, cutoff=1))
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
            "search_query": state.get("search_query") or state["question"],
            "context": format_context(state["docs"]),
            "history": format_history(state.get("messages")),
            "language": language_name(language),
            "rejection": rejection_message(language),
            "citation": citation_word(language),
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
    """Guarda la interacción en la memoria de la sesión y en la tabla `messages`.

    Memoria: la pregunta y la respuesta se agregan a `messages` del estado
    (add_messages las acumula y el checkpointer las conserva por thread_id), así
    la siguiente pregunta de la misma sesión puede referirse a esta.

    Tabla: sin `user_id` (pruebas por consola) no se guarda. Si Postgres falla,
    la respuesta ya está lista: se registra el error y no se pierde.
    """
    memory = {"messages": [HumanMessage(state["question"]), AIMessage(state["answer"])]}
    user_id = state.get("user_id")
    if not user_id:
        return memory
    try:
        db.guardar_mensaje(
            user_id=user_id,
            session_id=state.get("session_id"),
            question=state["question"],
            answer=state["answer"],
            sources=state.get("sources", []),
            rejected=state.get("rejected", False),
        )
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo guardar el historial de %s", user_id)
    return memory


# --- Rutas (las usan los edges condicionales de graph.py) --------------------

def intent_route(state: AgentState) -> str:
    """Después de validate_intent: reescribir y buscar, buscar directamente o manejar el error.

    No hay ruta a "reject": ninguna pregunta se rechaza sin consultar la base.
    """
    if state.get("error"):
        return "handle_error"
    return "rewrite_query" if state["on_topic"] else "retrieve"


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
