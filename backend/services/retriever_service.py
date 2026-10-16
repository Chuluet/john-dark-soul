"""Búsqueda de fragmentos para el agente.

    pregunta -> preparar (LLM: ¿es de Dark Souls? + traducción al inglés)
             -> pgvector con la pregunta original y la traducida (FETCH_K cada una)
             -> umbral -> pista de juego -> diversidad -> K fragmentos

1. Preparar: la wiki está en inglés y las preguntas en español. bge-m3 es
   multilingüe, pero los nombres traducidos ("Vigilantes del Abismo") se
   parecen poco a los originales ("Abyss Watchers"); traducir la pregunta sube
   mucho el puntaje de los fragmentos correctos. En la misma llamada el LLM dice
   si la pregunta es de Dark Souls: si dice que no y la pregunta no nombra nada
   de la wiki, se rechaza sin buscar.
2. Se busca con las dos versiones y se queda el mejor puntaje de cada fragmento.
3. Se descartan los que no llegan a SIMILARITY_THRESHOLD.
4. Si la pregunta deja ver un juego ("Dark Souls 2", "Vendrick"...), los
   fragmentos de ese juego suben RETRIEVER_BONO_JUEGO y los claramente de otro
   bajan lo mismo. Los que no tienen juego (video, PDF sin juego) no se tocan.
   Es un empujón, no un filtro: muchas preguntas no dicen el juego.
5. Como mucho RETRIEVER_MAX_POR_FUENTE fragmentos por archivo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import ollama
from langchain_core.documents import Document

from app import config
from services.juegos import JUEGOS, IndiceJuegos
from vectorstore import vectorstore as backend

PROMPT_PREPARAR = """You prepare questions for a search engine over an English wiki about the Dark Souls video games (Dark Souls, Dark Souls II, Dark Souls III and their DLCs).
Reply with JSON only, exactly with these two keys: {"dark_souls": true or false, "en": "<English translation>"}
- dark_souls: false only if the question is clearly about something else: another video game (Elden Ring, Bloodborne, The Witcher...), food, sports, programming, prices or real-world facts. Characters, places or events you do not recognize may be from Dark Souls: if in doubt, answer true.
- en: the question translated into English, using the official English names from the games (Abismo -> Abyss, Portador de la Maldicion -> Bearer of the Curse, Ceniza Sin Llama -> Ashen One, Cama del Caos -> Bed of Chaos)."""


@dataclass
class Consulta:
    original: str
    en: str | None = None          # traducción; None si no se tradujo
    en_tema: bool = True           # False: no es de Dark Souls, no se busca
    juegos: list[str] = field(default_factory=list)  # juegos que deja ver la pregunta


@dataclass
class Resultado:
    documento: Document
    similitud: float  # coseno de pgvector, 0..1
    puntaje: float    # similitud + ajuste por juego; es el que ordena

    @property
    def fuente(self) -> str:
        return self.documento.metadata.get("fuente", "")


_indice: IndiceJuegos | None = None


def indice_juegos() -> IndiceJuegos:
    """Índice de nombres por juego, construido una vez a partir de lo indexado."""
    global _indice
    if _indice is None:
        _indice = IndiceJuegos(backend.titulos_por_juego())
    return _indice


def preparar(pregunta: str, traducir: bool | None = None) -> Consulta:
    """Traduce la pregunta y decide si es de Dark Souls (una sola llamada al LLM).

    Si el LLM falla o responde algo raro, se busca con la pregunta tal cual:
    preparar nunca debe impedir una respuesta.
    """
    consulta = Consulta(pregunta)
    if config.RETRIEVER_TRADUCIR if traducir is None else traducir:
        try:
            respuesta = ollama.Client(host=config.OLLAMA_BASE_URL).chat(
                model=config.LLM_MODEL,
                format="json",
                messages=[{"role": "system", "content": PROMPT_PREPARAR}, {"role": "user", "content": pregunta}],
                options={"temperature": 0},
            ).message.content
            datos = json.loads(respuesta)
            consulta.en = str(datos.get("en") or "").strip() or None
            # El LLM no conoce todos los nombres (rechazaba "Frampt"): si la
            # pregunta nombra algo de la wiki, se busca igual.
            consulta.en_tema = datos.get("dark_souls") is not False or indice_juegos().menciona_nombre(pregunta)
        except Exception:  # noqa: BLE001
            pass
    consulta.juegos = indice_juegos().detectar(f"{pregunta}\n{consulta.en or ''}")
    return consulta


def candidatos(consulta: Consulta, fetch_k: int) -> list[tuple[Document, float]]:
    """Busca con la pregunta original y con la traducida; mejor puntaje por fragmento."""
    store = backend.get_vectorstore()
    mejores: dict[tuple, tuple[Document, float]] = {}
    for texto in filter(None, (consulta.original, consulta.en)):
        for documento, similitud in store.similarity_search_with_relevance_scores(texto, k=fetch_k):
            clave = (documento.metadata.get("fuente"), documento.metadata.get("fragmento"))
            if clave not in mejores or similitud > mejores[clave][1]:
                mejores[clave] = (documento, similitud)
    return sorted(mejores.values(), key=lambda par: par[1], reverse=True)


def _juegos_del_fragmento(documento: Document) -> set[str]:
    metadatos = documento.metadata
    if metadatos.get("juego") in JUEGOS:
        return {metadatos["juego"]}
    return set(metadatos.get("juegos") or [])


def reordenar(
    candidatos: list[tuple[Document, float]],
    juegos_pregunta: list[str],
    *,
    k: int,
    umbral: float,
    bono: float,
    max_por_fuente: int,
) -> list[Resultado]:
    """Pasos 3-5 sobre los candidatos (documento, similitud) ya traídos de pgvector."""
    buscados = set(juegos_pregunta)
    resultados = []
    for documento, similitud in candidatos:
        if similitud < umbral:
            continue
        ajuste = 0.0
        juegos = _juegos_del_fragmento(documento)
        if buscados and juegos:
            ajuste = bono if juegos & buscados else -bono
        resultados.append(Resultado(documento, similitud, similitud + ajuste))

    resultados.sort(key=lambda r: r.puntaje, reverse=True)

    elegidos, por_fuente = [], {}
    for resultado in resultados:
        usados = por_fuente.get(resultado.fuente, 0)
        if usados >= max_por_fuente:
            continue
        por_fuente[resultado.fuente] = usados + 1
        elegidos.append(resultado)
        if len(elegidos) == k:
            break
    return elegidos


def buscar(
    pregunta: str,
    *,
    k: int | None = None,
    fetch_k: int | None = None,
    umbral: float | None = None,
    bono: float | None = None,
    max_por_fuente: int | None = None,
) -> list[Resultado]:
    """Fragmentos más útiles para responder la pregunta (lista vacía = no hay info)."""
    consulta = preparar(pregunta)
    if not consulta.en_tema:
        return []
    return reordenar(
        candidatos(consulta, fetch_k or config.RETRIEVER_FETCH_K),
        consulta.juegos,
        k=k or config.RETRIEVER_K,
        umbral=config.SIMILARITY_THRESHOLD if umbral is None else umbral,
        bono=config.RETRIEVER_BONO_JUEGO if bono is None else bono,
        max_por_fuente=max_por_fuente or config.RETRIEVER_MAX_POR_FUENTE,
    )
