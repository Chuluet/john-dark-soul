from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agents.nodes import (
    context_route,
    evaluate_context,
    generate,
    intent_route,
    reject,
    retrieve,
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
    graph.add_node("save_history", save_history)

    # Edge fijo: toda pregunta entra validando la intención.
    graph.add_edge(START, "validate_intent")

    # Edge condicional: intent_route devuelve "rewrite_query" o "reject".
    # El diccionario mapea esa respuesta al nodo destino (y lo hace visible en el diagrama).
    graph.add_conditional_edges(
        "validate_intent",
        intent_route,
        {"rewrite_query": "rewrite_query", "reject": "reject"},
    )

    # Edge fijo: la pregunta reescrita en inglés pasa a la búsqueda.
    graph.add_edge("rewrite_query", "retrieve")

    # Edge fijo: después de buscar, siempre se evalúa el contexto.
    graph.add_edge("retrieve", "evaluate_context")

    # Edge condicional: context_route devuelve "generate" o "reject".
    graph.add_conditional_edges(
        "evaluate_context",
        context_route,
        {"generate": "generate", "reject": "reject"},
    )

    # Ambos caminos (responder o rechazar) terminan guardando la interacción.
    graph.add_edge("generate", "save_history")
    graph.add_edge("reject", "save_history")
    graph.add_edge("save_history", END)

    # InMemorySaver: guarda el estado por sesión (thread_id), como en el agente de voz.
    return graph.compile(checkpointer=InMemorySaver())


def ask(graph, question: str, session: str) -> dict:
    """Ejecuta una pregunta completa. Equivalente a answer_text() del profesor.

    Devuelve {"answer": ..., "sources": [...]}.
    """
    # Con checkpointer, LangGraph EXIGE un thread_id: identifica la sesión del usuario.
    result = graph.invoke(
        {"question": question},
        {"configurable": {"thread_id": session}},
    )
    return {"answer": result["answer"], "sources": result.get("sources", [])}
