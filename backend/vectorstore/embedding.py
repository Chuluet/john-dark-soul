"""Modelo de embeddings servido por Ollama.

El MISMO modelo debe usarse para indexar y para consultar: dos modelos
distintos generan espacios vectoriales incompatibles.
"""

from langchain_ollama import OllamaEmbeddings

from app import config


def get_embeddings() -> OllamaEmbeddings:
    return OllamaEmbeddings(
        model=config.EMBED_MODEL,
        base_url=config.OLLAMA_BASE_URL,
    )