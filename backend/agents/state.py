from typing import Annotated, TypedDict

from langchain_core.documents import Document
from langgraph.graph.message import add_messages


# TypedDict: un diccionario con claves y tipos fijos. LangGraph lo usa como
# "esquema" del estado: cada clave es un canal que los nodos pueden leer y escribir.
class AgentState(TypedDict):
    # Pregunta del usuario. Es lo único que se pasa al invocar el grafo:
    #   graph.invoke({"question": "Who is Artorias?"})
    question: str

    # Lo escribe validate_intent: idioma de la pregunta ("en", "es" u "other").
    # El agente responde en inglés salvo que la pregunta esté en otro idioma.
    language: str

    # Lo escribe validate_intent: True si la pregunta es del lore de Dark Souls.
    # El edge condicional lo lee para decidir entre "rewrite_query" o "reject".
    on_topic: bool

    # Lo escribe rewrite_query: la pregunta en inglés y con los nombres oficiales
    # del juego. Solo se usa para buscar; la respuesta se basa en `question`.
    search_query: str

    # Lo escribe retrieve (llamando la tool): lista de (fragmento, puntaje).
    # El puntaje es la relevancia de 0 a 1 que se compara contra SIMILARITY_THRESHOLD.
    docs: list[tuple[Document, float]]

    # Lo escribe evaluate_context: True si los fragmentos que pasaron el umbral
    # realmente responden la pregunta. Decide entre "generate" o "reject".
    sufficient: bool

    # Lo escribe generate (la respuesta) o reject (el mensaje de rechazo).
    # Es lo que finalmente se le muestra al usuario.
    answer: str

    # Lo escribe generate: las fuentes usadas, por ejemplo
    #   [{"title": "Knight Artorias", "game": "DS1", "url": "https://..."}]
    # Sirve para mostrarlas en el frontend (estrategia anti-alucinación 3.4).
    sources: list[dict]

    # Annotated[..., add_messages] cambia cómo se actualiza esta clave: en vez de
    # REEMPLAZAR la lista, add_messages AGREGA los mensajes nuevos al final.
    messages: Annotated[list, add_messages]
