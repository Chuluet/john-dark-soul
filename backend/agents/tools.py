"""Herramientas del agente.

La búsqueda está decorada con @tool (LangChain), pero en este grafo NO la elige
el modelo: el nodo `retrieve` la invoca siempre. Así el agente nunca responde
sin haber consultado la base vectorial.
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.tools import tool

from app import config
from vectorstore import vectorstore as backend

# El vector store es costoso de construir (abre conexión y carga el modelo de
# embeddings), así que lo memorizamos entre llamadas.
_store = None
_titles = None


def _get_store():
    global _store
    if _store is None:
        _store = backend.get_vectorstore()
    return _store


def get_titles() -> list[str]:
    """Títulos de las páginas indexadas; se leen una vez de la base."""
    global _titles
    if not _titles:
        _titles = backend.listar_titulos()
    return _titles


@tool
def search_documents(query: str, k: int = config.RETRIEVER_K) -> list[tuple[Document, float]]:
    """Search the Dark Souls lore vector database for relevant fragments.

    Returns (fragment, score) pairs with a score between 0 and 1: higher means
    more similar. That score is compared against SIMILARITY_THRESHOLD.

    Args:
        query: The question or the terms to search for, in natural language.
        k: How many fragments to return.
    """
    return _get_store().similarity_search_with_relevance_scores(query, k=k)


@tool
def list_documents() -> str:
    """List the documents currently indexed in the vector database."""
    sources = backend.listar_fuentes(_get_store())
    total = backend.contar_fragmentos(_get_store())

    if not sources:
        return "The vector database is empty. No documents are indexed."

    listing = "\n".join(f"- {source}" for source in sources)
    return f"{len(sources)} indexed document(s), {total} fragments in total:\n{listing}"
