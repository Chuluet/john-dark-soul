"""Funciones puras fáciles de probar."""
import difflib
import re
from collections.abc import Collection
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

# Nombre del idioma para pedírselo al modelo en ANSWER_PROMPT.
LANGUAGE_NAMES = {"en": "English", "es": "Spanish"}


def detect_language(text: str) -> str:
    """'es' o 'en' según las palabras de la pregunta.

    El agente solo trabaja en español e inglés: lo que no se reconoce como
    español se responde en inglés, el idioma por defecto.
    """
    words = re.findall(r"[^\W\d_]+", text.lower())
    spanish = sum(word in _SPANISH_WORDS for word in words)
    english = sum(word in _ENGLISH_WORDS for word in words)
    if spanish != english:
        return "es" if spanish > english else "en"
    # Empate: ¿ ¡ ñ y las tildes delatan el español. Se miran después de las
    # palabras para que "¿Who is Solaire?" no cuente como español.
    return "es" if re.search(r"[¿¡ñáéíóú]", text, re.IGNORECASE) else "en"


def language_name(language: str) -> str:
    """Instrucción de idioma para el modelo: 'English' o 'Spanish' (inglés por defecto)."""
    return LANGUAGE_NAMES.get(language, LANGUAGE_NAMES["en"])


def message_text(message: Any) -> str:
    """Extrae texto de un mensaje LangChain, incluso si su contenido es una lista."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content).strip()
    return str(content).strip()


def format_history(messages, max_turns: int = 3, max_chars: int = 400) -> str:
    """Últimos intercambios de la sesión como texto, para entender preguntas de seguimiento.

    Solo sirve para saber a qué se refiere la pregunta ("¿y su lobo?"); nunca
    como fuente de información. Las respuestas largas se recortan.

    Los mensajes de rechazo se omiten: no dicen nada del tema y, si la misma
    pregunta ya se rechazó una vez, el modelo tiende a repetir el rechazo.
    """
    from agents.prompts import REJECTION_MESSAGES  # aquí para no crear un import circular

    if not messages:
        return "(no previous messages)"
    lines = []
    for message in messages[-2 * max_turns:]:
        role = "User" if getattr(message, "type", "") == "human" else "Assistant"
        text = message_text(message)
        if role == "Assistant" and is_rejection(text, REJECTION_MESSAGES.values()):
            continue
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "…"
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


def _normalize(text: str) -> str:
    """Minúsculas, sin comillas al borde y con los espacios colapsados."""
    return " ".join(text.strip().strip("\"'“”«»").lower().split())


def is_rejection(answer: str, rejection_messages) -> bool:
    """True si la respuesta empieza con la primera frase de algún mensaje de rechazo.

    Se compara solo la primera frase: el modelo a veces omite la sugerencia de
    subir documentos o cambia la puntuación del final.
    """
    normalized = _normalize(answer)
    for message in rejection_messages:
        first_sentence = _normalize(message).split(". ")[0].rstrip(".")
        if normalized.startswith(first_sentence):
            return True
    return False


_WORD = re.compile(r"[^\W\d_]{4,}")


def proper_nouns(texts, min_count: int = 2, min_ratio: float = 0.8) -> dict[str, float]:
    """Palabras que en la base casi siempre van con mayúscula: nombres propios.

    'Midir', 'Gael' o 'Lothric' salen siempre con mayúscula; 'black' o 'fire'
    también aparecen en minúscula, así que no cuentan. Se devuelven en minúscula,
    cada una con la fracción de textos en que aparece ('dark' ~0.7, 'gael' ~0.01).
    """
    texts = list(texts)
    if not texts:
        return {}
    upper: dict[str, int] = {}
    total: dict[str, int] = {}
    in_texts: dict[str, int] = {}
    for text in texts:
        seen = set()
        for word in _WORD.findall(text):
            lower = word.lower()
            total[lower] = total.get(lower, 0) + 1
            if word[0].isupper():
                upper[lower] = upper.get(lower, 0) + 1
            seen.add(lower)
        for lower in seen:
            in_texts[lower] = in_texts.get(lower, 0) + 1
    return {
        word: in_texts[word] / len(texts)
        for word, count in total.items()
        if count >= min_count and upper.get(word, 0) / count >= min_ratio
    }


def rare_names(names: dict[str, float], max_share: float = 0.05) -> set[str]:
    """Nombres que salen en pocos textos: 'gael' dice de qué trata algo, 'dark' no."""
    return {word for word, share in names.items() if share <= max_share}


def known_names_in(text: str, names: Collection[str], cutoff: float = 0.87) -> set[str]:
    """Nombres de la base que aparecen en el texto, tolerando erratas.

    'who is quelag' -> {'quelaag'}. La tolerancia solo se aplica a palabras de
    5 letras o más: en las cortas, una letra cambia demasiado.
    """
    found = set()
    for word in set(_WORD.findall(text.lower())):
        if word in names:
            found.add(word)
        elif len(word) >= 5:
            found.update(difflib.get_close_matches(word, names, n=1, cutoff=cutoff))
    return found


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
        # El modelo cita el archivo, igual que las fuentes que muestra la
        # interfaz. Título, juego y sección ya van en la cabecera del propio
        # fragmento ('Knight Artorias (DS1) > Lore'), puesta por la ingesta.
        reference = document_name(meta.get("fuente") or "unknown")
        blocks.append(
            f"[Fragment {position} | document: {reference}]\n"
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
            "document": document_name(file),
        })
    return sources


def document_name(source: str) -> str:
    """Nombre del archivo que generó los fragmentos, sin carpetas.

    'uploads/<uuid>/gael__DS3.pdf' -> 'gael__DS3.pdf'. La ingesta en Windows
    guarda las subcarpetas con '\\', por eso se cortan las dos barras.
    """
    return re.split(r"[\\/]", source)[-1]
