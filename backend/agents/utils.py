"""Funciones puras fáciles de probar."""
import re
from typing import Any

# Palabras muy frecuentes que delatan el idioma de una pregunta corta. Los
# nombres propios del juego están en inglés, así que no sirven de pista.
_SPANISH_WORDS = {
    "que", "qué", "quien", "quién", "quienes", "quiénes", "como", "cómo", "cual", "cuál",
    "cuales", "cuáles", "donde", "dónde", "cuando", "cuándo", "por", "porque", "para",
    "el", "la", "los", "las", "un", "una", "es", "son", "fue", "era", "del", "de", "en",
    "y", "se", "su", "sus", "le", "lo", "al", "con", "sobre", "hay", "pasa", "pasó",
    "hace", "hizo", "historia", "juego", "jefe", "personaje",
}
_ENGLISH_WORDS = {
    "the", "who", "what", "which", "where", "when", "why", "how", "is", "are", "was",
    "were", "did", "does", "do", "of", "and", "in", "to", "a", "an", "about", "his",
    "her", "their", "there", "story", "game", "boss", "character", "tell",
}

# Palabras frecuentes de otros idiomas cercanos (francés, portugués, italiano,
# alemán): evitan que una pregunta en francés cuente como español por un "le".
_OTHER_WORDS = {
    "qui", "est", "il", "elle", "les", "des", "du", "où", "quoi", "pourquoi", "quem",
    "não", "é", "você", "chi", "è", "perché", "wer", "ist", "der", "die", "das", "und",
}

# Nombre del idioma para pedírselo al modelo en ANSWER_PROMPT.
LANGUAGE_NAMES = {"en": "English", "es": "Spanish"}


def detect_language(text: str) -> str:
    """'es', 'en' u 'other' según las palabras de la pregunta.

    Solo distingue los idiomas que tienen mensaje de rechazo propio; con
    'other' el modelo responde en el idioma de la pregunta y el rechazo sale
    en inglés.
    """
    words = re.findall(r"[^\W\d_]+", text.lower())
    spanish = sum(word in _SPANISH_WORDS for word in words)
    english = sum(word in _ENGLISH_WORDS for word in words)
    other = sum(word in _OTHER_WORDS for word in words)
    if other > max(spanish, english):
        return "other"
    if spanish > english:
        return "es"
    if english > spanish:
        return "en"
    # Empate: ¿ ¡ y ñ son casi una firma del español (las tildes no: el
    # francés o el portugués también las usan). Se miran después de las
    # palabras para que "¿Who is Solaire?" no cuente como español.
    if re.search(r"[¿¡ñ]", text, re.IGNORECASE):
        return "es"
    if not words:
        return "en"
    # Empate (o ninguna palabra conocida): si hay letras fuera del alfabeto
    # inglés es otro idioma; si no, se asume inglés, el idioma por defecto.
    return "other" if re.search(r"[^\x00-\x7f]", text) else "en"


def language_name(language: str) -> str:
    """Instrucción de idioma para el modelo: 'English', 'Spanish' o el de la pregunta."""
    return LANGUAGE_NAMES.get(language, "the same language as the question")


def message_text(message: Any) -> str:
    """Extrae texto de un mensaje LangChain, incluso si su contenido es una lista."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content).strip()
    return str(content).strip()


def expand_names(query: str, titles) -> str:
    """Completa los nombres cortos con el título de su página de la wiki.

    'What did Frampt ask...' -> 'What did Kingseeker Frampt ask...'. Solo se
    usan palabras con mayúscula (nombres propios) que aparecen en UN solo
    título: si están en varios ('Abyss', 'Gwyn') no se sabe cuál es.
    """
    pages_by_word: dict[str, set[str]] = {}
    for title in titles:
        for word in set(re.findall(r"[a-z]{3,}", title.lower())):
            pages_by_word.setdefault(word, set()).add(title)

    def replace(match: re.Match) -> str:
        word = match.group(0)
        pages = pages_by_word.get(word.lower(), set())
        # Palabras de pregunta con mayúscula ("Who", "Why") no son nombres.
        if len(pages) != 1 or word.lower() in _ENGLISH_WORDS:
            return word
        title = next(iter(pages))
        # Si el título completo ya está en la pregunta, no se repite.
        return word if title.lower() in query.lower() else title

    return re.sub(r"\b[A-Z][a-zA-Z]{2,}\b", replace, query)


def merge_results(result_lists, k: int, max_per_source: int) -> list:
    """Une las búsquedas de varias versiones de la pregunta en un solo ranking.

    Cada fragmento se queda con su mejor puntaje (puede salir en las dos
    búsquedas) y, como mucho, entran `max_per_source` fragmentos de cada
    archivo: así una página muy parecida no tapa a la que responde.
    """
    best = {}
    for results in result_lists:
        for document, score in results:
            meta = document.metadata or {}
            key = (meta.get("fuente"), meta.get("fragmento"), document.page_content)
            if key not in best or score > best[key][1]:
                best[key] = (document, score)

    merged, per_source = [], {}
    for document, score in sorted(best.values(), key=lambda pair: pair[1], reverse=True):
        source = (document.metadata or {}).get("fuente")
        if per_source.get(source, 0) >= max_per_source:
            continue
        per_source[source] = per_source.get(source, 0) + 1
        merged.append((document, score))
        if len(merged) >= k:
            break
    return merged


def format_context(docs) -> str:
    blocks = []
    for position, (document, _score) in enumerate(docs, start=1):
        meta = document.metadata or {}
        # .md de la wiki: "Knight Artorias, DS1". Imágenes/video: el nombre del archivo.
        title = meta.get("title") or meta.get("fuente", "unknown")
        game = meta.get("juego")
        reference = f"{title}, {game}" if game and game != "general" else title

        # Sección del fragmento: título '##' de la wiki, "Página N" del PDF o
        # "mm:ss - mm:ss" del video.
        section = meta.get("seccion")
        if section:
            reference += f", {section}"

        blocks.append(
            f"[Fragment {position} | source: {reference}]\n"
            f"{document.page_content.strip()}"
        )

    return "\n\n---\n\n".join(blocks)


def extract_sources(docs, puntaje_minimo: float = 0.55) -> list[dict]:
    """Devuelve las fuentes únicas de los documentos con puntaje >= puntaje_minimo, en orden de aparición."""
    sources = []
    seen = set()
    # Los fragmentos poco parecidos a la pregunta no se muestran como fuente;
    # si ninguno llega al mínimo, se muestra al menos el de mayor puntaje.
    relevant = [(doc, score) for doc, score in docs if score >= puntaje_minimo]
    if not relevant and docs:
        relevant = [max(docs, key=lambda pair: pair[1])]
    for document, _score in relevant:
        meta = document.metadata or {}
        file = meta.get("fuente")
        if not file or file in seen:
            continue  # sin fuente o ya agregada (varios fragmentos del mismo archivo)
        seen.add(file)
        sources.append({
            "title": meta.get("title") or file,  # imágenes/video no tienen title
            "game": meta.get("juego"),           # None si no aplica
            "url": meta.get("url"),              # link a la wiki; None si no aplica
        })
    return sources
