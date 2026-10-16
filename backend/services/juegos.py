"""Detecta a qué juego (DS1, DS2, DS3) se refiere un texto.

Muchas fuentes no dicen de qué juego hablan: el video recorre los tres, un PDF
puede no tenerlo en el nombre y las preguntas casi nunca dicen "en Dark Souls 2".
Se usan dos pistas:

1. Menciones explícitas: "Dark Souls III", "DS2", "Dark Souls 2"...
2. Nombres propios que solo existen en un juego: "Lothric" (DS3), "Vendrick"
   (DS2), "Lordran" (DS1). Se sacan de los títulos de la propia wiki, así que
   crecen solos al añadir páginas. Los que aparecen en varios juegos (Gwyn,
   Seath...) no cuentan, porque no dicen nada del juego.

El resultado es una pista, no una verdad: la búsqueda lo usa para subir un poco
el puntaje de los fragmentos del juego correcto, nunca para descartar otros.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable

JUEGOS = ("DS1", "DS2", "DS3")

# "Dark Souls" a secas no cuenta: en la wiki y en las preguntas se usa para toda la saga.
_EXPLICITO = re.compile(
    r"\b(?:ds\s?([123])|dark\s*souls\s*(iii|ii|i|3|2|1|tres|dos|uno)(?![\w'’])"
    r"|(primer|segundo|tercer)\s+(?:dark\s*souls|juego))",
    re.IGNORECASE,
)
_NUMERO = {"1": "DS1", "i": "DS1", "uno": "DS1", "primer": "DS1",
           "2": "DS2", "ii": "DS2", "dos": "DS2", "segundo": "DS2",
           "3": "DS3", "iii": "DS3", "tres": "DS3", "tercer": "DS3"}

# Títulos de la wiki que no son nombres propios y aparecerían en cualquier texto.
_GENERICOS = {
    "boss", "bosses", "lords", "lord", "characters", "locations", "hollow", "undead",
    "nestling", "elizabeth", "the gutter", "crestfallen warrior", "crestfallen merchant",
    "dark lord", "lords of cinder", "fire keeper", "ashen one", "chosen undead",
    "bearer of the curse", "abyss", "oolacile", "darklurker", "ancient dragon",
    "world", "depths", "the depths", "old ones", "giant", "dragon", "demon",
    # Palabras comunes que salen de partir "X of Y" ("Valley of Drakes" -> "valley").
    "battle", "bearer", "catacombs", "cemetery", "chasm", "dancer", "daughter", "deacons",
    "doors", "forest", "grave", "knight", "memory", "shrine", "spear", "throne", "valley",
    # Personajes que aparecen en más de un juego aunque su página esté en uno solo.
    "andre", "patches", "velka",
}
_MIN_LARGO = 5


def _variantes(titulo: str) -> set[str]:
    """'Gwyn, Lord of Cinder' -> {'gwyn, lord of cinder', 'gwyn'}; 'Solaire of Astora' -> + 'solaire'."""
    titulo = re.sub(r"\s*\(.*?\)\s*", " ", titulo).strip().lower()
    variantes = {titulo}
    for separador in (",", " of "):
        if separador in titulo:
            variantes.add(titulo.split(separador)[0].strip())
    return {v for v in variantes if len(v) >= _MIN_LARGO and v not in _GENERICOS}


class IndiceJuegos:
    """Nombres propios que pertenecen a un solo juego, listos para buscarlos en un texto."""

    def __init__(self, pares: Iterable[tuple[str, str]] = ()):
        """`pares`: (título, juego) de las páginas de la wiki."""
        pares = list(pares)
        juegos_por_nombre: dict[str, set[str]] = defaultdict(set)
        for titulo, juego in pares:
            for variante in _variantes(titulo or ""):
                juegos_por_nombre[variante].add(juego)
        self.nombres = {
            nombre: next(iter(juegos))
            for nombre, juegos in juegos_por_nombre.items()
            if len(juegos) == 1 and next(iter(juegos)) in JUEGOS
        }
        # Todas las palabras de los títulos (de uno o varios juegos): sirven para
        # saber si una pregunta habla de algo que está en la wiki.
        self.palabras = {
            palabra
            for titulo, _ in pares
            for palabra in re.findall(r"[a-z]{4,}", (titulo or "").lower())
        }
        # Más largos primero: "lothric castle" antes que "lothric".
        ordenados = sorted(self.nombres, key=len, reverse=True)
        self._patron = (
            re.compile(r"\b(" + "|".join(map(re.escape, ordenados)) + r")\b", re.IGNORECASE)
            if ordenados else None
        )

    def menciona_nombre(self, texto: str) -> bool:
        """¿Nombra el texto algo que aparece en un título de la wiki ('Frampt', 'Lothric')?

        Solo cuentan las palabras que empiezan con mayúscula (nombres propios),
        para que 'la capital de Francia' no coincida con 'Profaned Capital'.
        """
        return any(
            palabra.lower() in self.palabras
            for palabra in re.findall(r"\b[A-ZÁÉÍÓÚÑ][\w']{3,}", texto)
        )

    def detectar(self, texto: str) -> list[str]:
        """Juegos a los que se refiere el texto, del más al menos mencionado.

        Las menciones explícitas ("Dark Souls 3") mandan: si las hay, se ignoran
        los nombres propios.
        """
        explicitos = Counter(
            _NUMERO[(m.group(1) or m.group(2) or m.group(3)).lower()]
            for m in _EXPLICITO.finditer(texto)
        )
        if explicitos:
            return [j for j, _ in explicitos.most_common()]
        if self._patron is None:
            return []
        por_nombre = Counter(self.nombres[m.group(1).lower()] for m in self._patron.finditer(texto))
        return [j for j, _ in por_nombre.most_common()]
