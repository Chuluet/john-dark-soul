from langchain_ollama import ChatOllama
from app import config


def create_llm() -> ChatOllama:
    """Modelo de chat Qwen servido por Ollama."""
    return ChatOllama(
        model=config.LLM_MODEL,
        base_url=config.OLLAMA_BASE_URL,
        temperature=config.TEMPERATURE,
    )
