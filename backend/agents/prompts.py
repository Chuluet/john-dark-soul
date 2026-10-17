from langchain_core.prompts import ChatPromptTemplate

# Respuesta obligatoria cuando no hay información suficiente (sección 3.1 del enunciado).
# El agente responde en inglés salvo que la pregunta esté en español; el
# rechazo es un texto fijo, así que hay una versión por idioma.
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


# Palabra con la que se citan las fuentes dentro de la respuesta: "(source: ...)"
# en inglés, "(fuente: ...)" en español.
CITATION_WORDS = {"en": "source", "es": "fuente"}


def citation_word(language: str) -> str:
    """Palabra de las citas en el idioma de la pregunta (inglés si no hay versión)."""
    return CITATION_WORDS.get(language, CITATION_WORDS[DEFAULT_LANGUAGE])


# --- Nodo validate_intent ---------------------------------------------------
# Decide si la pregunta es del dominio. Con YES se reescribe antes de buscar;
# con NO se busca con la pregunta original (nunca se rechaza sin buscar). Con
# un criterio estricto marcaba como ajenas preguntas de seguimiento ("who is
# his wolf") o con nombres sueltos ("¿Qué le pasó a Gwyn?") y se buscaban mal.
INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a classifier for a Dark Souls lore assistant. Decide whether the user's question "
     "could be about the Dark Souls trilogy (Dark Souls, Dark Souls II and Dark Souls III, "
     "including their DLCs): its story, lore, characters, bosses, places, items, covenants or "
     "events.\n"
     "The question may be written in any language.\n"
     "Answer YES if the question mentions anything from those games (a name like Gwyn, Artorias "
     "or Lothric is enough).\n"
     "Also answer YES if the question refers to something said earlier (he, his, they, it, that "
     "boss...; for example 'and his wolf?', 'who did they fight?', 'what happened to his shield?') "
     "and any earlier message of the conversation is about Dark Souls, even if the last one "
     "was about something else.\n"
     "Answer NO only if the question is clearly about something else (cooking, weather, sports, "
     "programming, other video games...).\n"
     "When in doubt, answer YES.\n"
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
     "- If the question refers to earlier messages (he, his, they, it, that boss...), replace the "
     "reference with the name from the conversation so the question can be understood on its own. "
     "The reference points to what the USER has been asking about (the subjects of the user's "
     "previous questions), not to other names that only appear inside the assistant's answers. "
     "For example, after 'Who is Artorias?' and 'who is his wolf?', 'they' means Artorias and Sif.\n"
     "- If the question already names someone or something ('quien es la gael' -> Gael), keep "
     "that name: it is a new topic, not a reference to the conversation.\n"
     "- Do not add names, titles or details that are not in the question or the conversation.\n"
     "Reply with the rewritten question only."),
    ("human", "Conversation so far:\n{history}\n\nQuestion: {question}"),
])


# --- Nodo evaluate_context --------------------------------------------------
# Verifica que los fragmentos recuperados realmente respondan la pregunta.
# Pide YES también si la respuesta es parcial: con "suficiente" el modelo
# rechazaba preguntas que la página recuperada sí respondía. Recibe además la
# pregunta reescrita en inglés: sin ella no sabe que "Llama Primigenia" es la
# "First Flame" de los fragmentos. No menciona Dark Souls: los usuarios pueden
# subir documentos de otros temas, y esos también se deben poder responder.
EVALUATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You check whether some document fragments from a knowledge base can answer a question.\n"
     "The question and the fragments may be in different languages.\n"
     "Answer YES if the fragments contain information that answers the question, fully or in part "
     "(for example, who a character is, what happened, why or where).\n"
     "Answer NO only if the fragments are about other things and do not help answer it.\n"
     "Judge only what the fragments say, not your own knowledge.\n"
     "Answer only YES or NO."),
    ("human", "Question: {question}\nSame question on its own, with the names used in the fragments: "
              "{search_query}\n\nFragments:\n{context}\n\nCan the fragments answer the question? YES or NO:"),
])


# --- Nodo generate ----------------------------------------------------------
# Basado en las INSTRUCCIONES del agente RAG del profesor.
# La regla 5 pide responder lo que haya aunque sea parcial: con "si el contexto
# no basta, rechaza" el modelo rechazaba preguntas que evaluate_context ya había
# aprobado y cuyos fragmentos sí tenían la respuesta.
# {language} es el idioma detectado de la pregunta: se repite en el mensaje
# del usuario porque el contexto en inglés arrastra al modelo a responder en inglés.
# {citation} es la palabra de las citas en ese idioma ("source" o "fuente"), y
# se cita el archivo, igual que las fuentes que muestra la interfaz.
# {search_query} es la pregunta reescrita: sin ella, en "who did they fight?"
# el modelo no sabía quiénes eran "they" y rechazaba.
ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You answer questions with a knowledge base about the lore of the Dark Souls trilogy, which "
     "users can extend with their own documents on any topic. Give a complete answer in one or "
     "two paragraphs, using all the relevant details from the context fragments.\n\n"
     "Language: answer in English, unless the question is written in Spanish: then answer "
     "in Spanish.\n\n"
     "Rules:\n"
     "1. Answer ONLY with the information in the context fragments. "
     "Do not use your prior knowledge or make anything up.\n"
     "2. If the fragments are in another language than your answer, translate them, "
     "but keep the official English names of characters, places and items.\n"
     "3. Cite the source document in parentheses at the end of each statement, with the file "
     "name exactly as it appears after \"document:\" in the fragment header, like this: "
     "({citation}: knight-artorias__DS1.md).\n"
     "4. If the fragments contradict each other, say so and mention both versions.\n"
     "5. If the fragments answer the question only in part, answer with that part and say "
     "briefly what the fragments do not cover. Only if none of the fragments has anything to do "
     "with the question, reply exactly: \"{rejection}\"\n"
     "6. The conversation so far only tells you what the question refers to "
     "(for example who \"he\" is). Never use it as a source of facts."),
    ("human", "Conversation so far:\n{history}\n\nContext:\n{context}\n\n"
              "Question: {question}\n"
              "Same question on its own: {search_query}\n\n(Answer in {language}.)"),
])
