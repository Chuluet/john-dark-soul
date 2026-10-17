from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agents.nodes import (
    context_route,
    evaluate_context,
    generate,
    generate_route,
    handle_error,
    intent_route,
    reject,
    retrieve,
    retrieve_route,
    rewrite_query,
    save_history,
    validate_intent,
)
from agents.state import AgentState


def build_graph():
    """Construye y compila el grafo del agente."""
    # El grafo trabaja sobre el esquema de estado definido en state.py.
    graph = StateGraph(AgentState)

    # Cada nodo es un nombre + la función que lo implementa.
    graph.add_node("validate_intent", validate_intent)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("retrieve", retrieve)
    graph.add_node("evaluate_context", evaluate_context)
    graph.add_node("generate", generate)
    graph.add_node("reject", reject)
    graph.add_node("handle_error", handle_error)
    graph.add_node("save_history", save_history)

    # Edge fijo: toda pregunta entra validando la intención.
    graph.add_edge(START, "validate_intent")

    # Edge condicional: intent_route devuelve "rewrite_query", "reject" o
    # "handle_error" (si Ollama falló). El diccionario mapea esa respuesta al
    # nodo destino (y lo hace visible en el diagrama).
    graph.add_conditional_edges(
        "validate_intent",
        intent_route,
        {"rewrite_query": "rewrite_query", "reject": "reject", "handle_error": "handle_error"},
    )

    # Edge fijo: la pregunta reescrita en inglés pasa a la búsqueda.
    graph.add_edge("rewrite_query", "retrieve")

    # Edge condicional: después de buscar se evalúa el contexto, salvo que la
    # base vectorial haya fallado.
    graph.add_conditional_edges(
        "retrieve",
        retrieve_route,
        {"evaluate_context": "evaluate_context", "handle_error": "handle_error"},
    )

    # Edge condicional: context_route devuelve "generate", "reject" o "handle_error".
    graph.add_conditional_edges(
        "evaluate_context",
        context_route,
        {"generate": "generate", "reject": "reject", "handle_error": "handle_error"},
    )

    # Responder o rechazar terminan guardando la interacción. Un fallo de
    # servicio no se guarda: no es una respuesta del agente.
    graph.add_conditional_edges(
        "generate",
        generate_route,
        {"save_history": "save_history", "handle_error": "handle_error"},
    )
    graph.add_edge("reject", "save_history")
    graph.add_edge("save_history", END)
    graph.add_edge("handle_error", END)

    # InMemorySaver: guarda el estado por sesión (thread_id), como en el agente de voz.
    return graph.compile(checkpointer=InMemorySaver())


def ask(graph, question: str, session: str, user_id: str | None = None) -> dict:
    """Ejecuta una pregunta completa. Equivalente a answer_text() del profesor.

    Devuelve {"answer", "sources", "rejected", "error"}. Con `error` distinto de
    None la API debe responder 503: el agente no rechazó, falló un servicio.
    """
    entrada = {"question": question}
    if user_id:
        entrada["user_id"] = user_id
    # Con checkpointer, LangGraph EXIGE un thread_id: identifica la sesión del usuario.
    result = graph.invoke(entrada, {"configurable": {"thread_id": session}})
    return {
        "answer": result["answer"],
        "sources": result.get("sources", []),
        "rejected": result.get("rejected", False),
        "error": result.get("error"),
    }
