from langchain_core.prompts import ChatPromptTemplate

# Respuesta obligatoria cuando no hay información suficiente (sección 3.1 del enunciado).
# El agente responde en inglés salvo que la pregunta esté en otro idioma; el
# rechazo es un texto fijo, así que hay una versión por idioma soportado.
REJECTION_MESSAGES = {
    "en": (
        "I don't have enough information in my knowledge base to answer that question. "
        "If you have documents on this topic, you can upload them so I can answer it."
    ),
    "es": (
        "No tengo suficiente información en mi base de conocimiento para responder esa pregunta. "
        "Si tienes documentos sobre ese tema, puedes subirlos para que pueda responderla."
    ),
}
DEFAULT_LANGUAGE = "en"


def rejection_message(language: str) -> str:
    """Mensaje de rechazo en el idioma de la pregunta (inglés si no hay versión)."""
    return REJECTION_MESSAGES.get(language, REJECTION_MESSAGES[DEFAULT_LANGUAGE])


# Cuando falla un servicio (Ollama, Postgres) no se responde nada del lore:
# se avisa del problema sin inventar una respuesta.
SERVICE_ERROR_MESSAGES = {
    "en": "The agent is not available right now. Please try again in a few moments.",
    "es": "El agente no está disponible en este momento. Intenta de nuevo en unos instantes.",
}


def service_error_message(language: str) -> str:
    """Mensaje de fallo del servicio en el idioma de la pregunta (inglés si no hay versión)."""
    return SERVICE_ERROR_MESSAGES.get(language, SERVICE_ERROR_MESSAGES[DEFAULT_LANGUAGE])


# --- Nodo validate_intent ---------------------------------------------------
# Decide si la pregunta pertenece al dominio antes de buscar.
INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a classifier. Decide whether the user's question is about the story, "
     "lore, characters, bosses, places or items of the Dark Souls trilogy "
     "(Dark Souls, Dark Souls II and Dark Souls III, including their DLCs).\n"
     "The question may be written in any language.\n"
     "If the question is a follow-up that only makes sense with the conversation "
     "(for example 'and his wolf?'), use the conversation to decide.\n"
     "Answer only YES or NO, with no explanation."),
    ("human", "Conversation so far:\n{history}\n\nQuestion: {question}"),
])


# --- Nodo rewrite_query -----------------------------------------------------
# La wiki está en inglés: los nombres traducidos ("Vigilantes del Abismo") o
# incompletos ("Frampt") se parecen poco a los de las páginas ("Abyss Watchers",
# "Kingseeker Frampt"). Esta versión de la pregunta solo se usa para buscar.
REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You rewrite questions as search queries for an English wiki about the Dark Souls "
     "trilogy (Dark Souls, Dark Souls II, Dark Souls III and their DLCs).\n"
     "- Translate the question into English if it is in another language.\n"
     "- Use the official English names from the games, not literal translations "
     "(No muerto elegido -> Chosen Undead, Portador de la Maldición -> Bearer of the Curse, "
     "Ceniza Sin Llama -> Ashen One, Primera Llama / Llama Primigenia -> First Flame, "
     "Cama del Caos -> Bed of Chaos).\n"
     "- Keep the meaning of the question; do not answer it.\n"
     "- If the question refers to earlier messages (he, his, it, that boss...), replace the "
     "reference with the name from the conversation so the question can be understood on its own.\n"
     "- Do not add names, titles or details that are not in the question or the conversation.\n"
     "Reply with the rewritten question only."),
    ("human", "Conversation so far:\n{history}\n\nQuestion: {question}"),
])


# --- Nodo evaluate_context --------------------------------------------------
# Verifica que los fragmentos recuperados realmente respondan la pregunta.
# Pide YES también si la respuesta es parcial: con "suficiente" el modelo
# rechazaba preguntas que la página recuperada sí respondía. Recibe además la
# pregunta reescrita en inglés: sin ella no sabe que "Llama Primigenia" es la
# "First Flame" de los fragmentos.
EVALUATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You check whether some document fragments can answer a question about the Dark Souls games.\n"
     "The question may be in any language; the fragments are in English.\n"
     "Answer YES if the fragments contain information that answers the question, fully or in part "
     "(for example, who a character is, what happened, why or where).\n"
     "Answer NO only if the fragments are about other things and do not help answer it.\n"
     "Judge only what the fragments say, not your own knowledge.\n"
     "Answer only YES or NO."),
    ("human", "Question: {question}\nSame question in English, with the names used in the fragments: "
              "{search_query}\n\nFragments:\n{context}\n\nCan the fragments answer the question? YES or NO:"),
])


# --- Nodo generate ----------------------------------------------------------
# Basado en las INSTRUCCIONES del agente RAG del profesor.
# {language} es el idioma detectado de la pregunta: se repite en el mensaje
# del usuario porque el contexto en inglés arrastra al modelo a responder en inglés.
ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are an expert on the lore of the Dark Souls trilogy. Give a complete answer in one or "
     "two paragraphs, using all the relevant details from the context fragments.\n\n"
     "Language: answer in English by default. If the question is written in another "
     "language, answer in that same language.\n\n"
     "Rules:\n"
     "1. Answer ONLY with the information in the context fragments. "
     "Do not use your prior knowledge or make anything up.\n"
     "2. The fragments are in English: if you answer in another language, translate them, "
     "but keep the official English names of characters, places and items.\n"
     "3. Cite the source in parentheses at the end of each statement, always with the word "
     "\"fuente\" and never \"source\", like this: (fuente: Knight Artorias, DS1).\n"
     "4. If the fragments contradict each other, say so and mention both versions.\n"
     "5. If the context is not enough to answer, reply exactly: \"{rejection}\"\n"
     "6. The conversation so far only tells you what the question refers to "
     "(for example who \"he\" is). Never use it as a source of facts."),
    ("human", "Conversation so far:\n{history}\n\nContext:\n{context}\n\n"
              "Question: {question}\n\n(Answer in {language}.)"),
])
