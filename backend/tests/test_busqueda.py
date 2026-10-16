"""Detección de juego y reordenamiento de la búsqueda (sin Postgres)."""

from langchain_core.documents import Document

from services.juegos import IndiceJuegos
from services.retriever_service import reordenar

INDICE = IndiceJuegos([
    ("Vendrick", "DS2"), ("Lothric", "DS3"), ("Lordran", "DS1"), ("Solaire of Astora", "DS1"),
    ("Gwyn, Lord of Cinder", "DS1"), ("Gwyn, Lord of Cinder", "DS2"), ("Gwyn, Lord of Cinder", "DS3"),
    ("Boss", "DS1"), ("Valley of Drakes", "DS1"),
])


def test_detecta_mencion_explicita():
    assert INDICE.detectar("¿Qué pasa en Dark Souls 2?") == ["DS2"]
    assert INDICE.detectar("en el tercer juego") == ["DS3"]
    assert INDICE.detectar("DS1 y Dark Souls III") == ["DS1", "DS3"]
    assert INDICE.detectar("Dark Souls II") == ["DS2"]  # no confundir con "Dark Souls I"


def test_detecta_por_nombres_propios_de_un_solo_juego():
    assert INDICE.detectar("¿Quién es Vendrick?") == ["DS2"]
    assert INDICE.detectar("¿Quién es Solaire?") == ["DS1"]


def test_no_adivina_cuando_no_hay_pista():
    assert INDICE.detectar("¿Quién es Gwyn?") == []        # está en los tres juegos
    assert INDICE.detectar("Dark Souls es difícil") == []  # "Dark Souls" a secas es la saga
    assert INDICE.detectar("the boss in the valley") == []  # palabras comunes no cuentan


def _doc(fuente, juego="general", juegos=None):
    return Document(page_content=fuente, metadata={"fuente": fuente, "juego": juego, "juegos": juegos or []})


def test_umbral_descarta_y_lista_vacia_si_nada_llega():
    candidatos = [(_doc("a"), 0.40), (_doc("b"), 0.30)]
    assert reordenar(candidatos, [], k=4, umbral=0.5, bono=0, max_por_fuente=2) == []


def test_bono_de_juego_reordena_pero_no_descarta():
    candidatos = [(_doc("gwyn__DS1", "DS1"), 0.70), (_doc("gwyn__DS3", "DS3"), 0.68), (_doc("video", juegos=[]), 0.69)]

    resultados = reordenar(candidatos, ["DS3"], k=3, umbral=0.5, bono=0.03, max_por_fuente=2)

    assert [r.fuente for r in resultados] == ["gwyn__DS3", "video", "gwyn__DS1"]
    assert resultados[1].puntaje == resultados[1].similitud  # sin juego: ni sube ni baja


def test_fragmento_sin_juego_fijo_usa_los_deducidos():
    candidatos = [(_doc("video", juegos=["DS2"]), 0.60), (_doc("wiki__DS1", "DS1"), 0.61)]
    resultados = reordenar(candidatos, ["DS2"], k=2, umbral=0.5, bono=0.03, max_por_fuente=2)
    assert resultados[0].fuente == "video"


def test_maximo_por_fuente_diversifica():
    candidatos = [(_doc("lothric__DS3", "DS3"), 0.9 - i / 100) for i in range(4)] + [(_doc("otra", "DS3"), 0.7)]
    resultados = reordenar(candidatos, [], k=3, umbral=0.5, bono=0, max_por_fuente=2)
    assert [r.fuente for r in resultados] == ["lothric__DS3", "lothric__DS3", "otra"]


def test_menciona_nombre_solo_cuenta_nombres_propios():
    indice = IndiceJuegos([("Kingseeker Frampt", "DS1"), ("Profaned Capital", "DS3")])
    assert indice.menciona_nombre("¿Qué le cuenta Frampt al jugador?")
    assert not indice.menciona_nombre("¿Cuál es la capital de Francia?")


class _LLMFalso:
    def __init__(self, respuesta):
        self.respuesta = respuesta

    def __call__(self, host):
        return self

    def chat(self, **_):
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return type("R", (), {"message": type("M", (), {"content": self.respuesta})()})()


def _preparar(monkeypatch, respuesta, pregunta):
    from services import retriever_service as rs
    monkeypatch.setattr(rs, "_indice", IndiceJuegos([("Kingseeker Frampt", "DS1"), ("Vendrick", "DS2")]))
    monkeypatch.setattr(rs.ollama, "Client", _LLMFalso(respuesta))
    return rs.preparar(pregunta, traducir=True)


def test_preparar_traduce_y_detecta_juego(monkeypatch):
    c = _preparar(monkeypatch, '{"dark_souls": true, "en": "Who is Vendrick?"}', "¿Quién es Vendrick?")
    assert (c.en, c.en_tema, c.juegos) == ("Who is Vendrick?", True, ["DS2"])


def test_preparar_rechaza_fuera_de_tema(monkeypatch):
    c = _preparar(monkeypatch, '{"dark_souls": false, "en": "Capital of France?"}', "¿Capital de Francia?")
    assert c.en_tema is False


def test_preparar_no_rechaza_si_nombra_algo_de_la_wiki(monkeypatch):
    c = _preparar(monkeypatch, '{"dark_souls": false, "en": "What does Frampt say?"}', "¿Qué dice Frampt?")
    assert c.en_tema is True


def test_preparar_tolera_respuestas_raras_y_errores(monkeypatch):
    assert _preparar(monkeypatch, '{"otra_cosa": 1}', "¿Quién es Vendrick?").en_tema is True
    c = _preparar(monkeypatch, ConnectionError("ollama caído"), "¿Quién es Vendrick?")
    assert (c.en, c.en_tema, c.juegos) == (None, True, ["DS2"])
