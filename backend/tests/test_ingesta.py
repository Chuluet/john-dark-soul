"""Ingesta: cada formato sale con los mismos metadatos y la misma cabecera.

No usan Postgres, Ollama ni Whisper: los modelos se sustituyen por dobles.
"""

import sys
import types
from types import SimpleNamespace as NS

import pytest
from langchain_core.documents import Document
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app import config
from services import ingest_service as ing
from services.juegos import IndiceJuegos

INDICE = IndiceJuegos([("Lothric", "DS3"), ("Vendrick", "DS2"), ("Lordran", "DS1"), ("Gwyn, Lord of Cinder", "DS1"),
                       ("Gwyn, Lord of Cinder", "DS3")])


def test_metadatos_base_lee_el_juego_del_nombre(tmp_path):
    assert ing._metadatos_base(tmp_path / "lore-ds2__DS2.pdf", "pdf") == {"title": "lore ds2", "juego": "DS2", "tipo": "pdf"}
    assert ing._metadatos_base(tmp_path / "Mi Documento.pdf", "pdf")["juego"] == "general"
    assert ing._metadatos_base(tmp_path / "x__general.pdf", "pdf")["juego"] == "general"


def test_md_con_frontmatter_lleva_cabecera_y_seccion(tmp_path):
    ruta = tmp_path / "lothric__DS3.md"
    cuerpo = "## Royal Madness\n\n" + "The royal family fell. " * 80 + "\n\n## Lothric's Refusal\n\nHe refused to link the fire."
    ruta.write_text(f"---\ntitle: Lothric\njuego: DS3\ncategoria: X\nfuente: https://wiki/Lothric\n---\n\n# Lothric (DS3)\n\n{cuerpo}",
                    encoding="utf-8")

    fragmentos = ing._fragmentar(ing._cargar_archivo(ruta), ruta.name, INDICE)

    ultimo = fragmentos[-1]
    assert ultimo.page_content.startswith("Lothric (DS3) > Lothric's Refusal\n\n")
    esperado = {"title": "Lothric", "juego": "DS3", "juegos": ["DS3"], "tipo": "wiki",
                "seccion": "Lothric's Refusal", "url": "https://wiki/Lothric", "fuente": "lothric__DS3.md"}
    assert ultimo.metadata.items() >= esperado.items()
    assert fragmentos[1].metadata["seccion"] == "Royal Madness"


def test_el_tamano_de_los_fragmentos_no_cambia(tmp_path):
    ruta = tmp_path / "largo__DS1.md"
    ruta.write_text("---\ntitle: Largo\njuego: DS1\n---\n\n" + "palabra " * 2000, encoding="utf-8")
    for fragmento in ing._fragmentar(ing._cargar_archivo(ruta), ruta.name, INDICE):
        cuerpo = fragmento.page_content.split("\n\n", 1)[1]
        assert len(cuerpo) <= config.CHUNK_SIZE


def test_sin_juego_se_deduce_de_cada_fragmento():
    documentos = [Document(page_content="Vendrick ruled Drangleic.", metadata={"title": "Notas", "juego": "general"}),
                  Document(page_content="Then the prince of Lothric refused.", metadata={"title": "Notas", "juego": "general"}),
                  Document(page_content="Nothing about any game.", metadata={"title": "Notas", "juego": "general"})]

    fragmentos = ing._fragmentar(documentos, "notas.pdf", INDICE)

    assert [f.metadata["juegos"] for f in fragmentos] == [["DS2"], ["DS3"], []]
    assert fragmentos[0].page_content.startswith("Notas (DS2)\n\n")
    assert fragmentos[2].page_content.startswith("Notas\n\n")
    assert all(f.metadata["juego"] == "general" for f in fragmentos)


def _pdf(ruta, paginas):
    escritor = PdfWriter()
    for texto in paginas:
        pagina = escritor.add_blank_page(300, 300)
        fuente = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                                   NameObject("/BaseFont"): NameObject("/Helvetica")})
        pagina[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): fuente})})
        contenido = DecodedStreamObject()
        contenido.set_data(f"BT /F1 12 Tf 20 150 Td ({texto}) Tj ET".encode())
        pagina[NameObject("/Contents")] = escritor._add_object(contenido)
    escritor.write(ruta)


def test_pdf_sin_juego_cita_la_pagina_y_deduce_el_juego(tmp_path):
    ruta = tmp_path / "apuntes.pdf"
    _pdf(ruta, ["Vendrick was the king.", "", "Lordran is old."])

    fragmentos = ing._fragmentar(ing._cargar_archivo(ruta), ruta.name, INDICE)

    assert [f.metadata["seccion"] for f in fragmentos] == ["Página 1", "Página 3"]
    assert [f.metadata["juegos"] for f in fragmentos] == [["DS2"], ["DS1"]]
    assert fragmentos[0].page_content.startswith("apuntes (DS2) > Página 1\n\n")


def test_imagen_con_texto_usa_los_titulos_como_secciones(tmp_path, monkeypatch):
    ruta = tmp_path / "lore-1-de-5__DS1.jpg"
    ruta.write_bytes(b"jpg")
    monkeypatch.setattr(ing, "_preguntar_imagen", lambda r, p: "## The Age of Fire:\n\nGwyn rose.")

    fragmentos = ing._fragmentar(ing._cargar_archivo(ruta), ruta.name, INDICE)

    assert fragmentos[0].page_content.startswith("lore 1 de 5 (DS1) > The Age of Fire\n\n")
    assert fragmentos[0].metadata["tipo"] == "imagen"


def test_imagen_sin_texto_ni_juego_no_se_indexa(tmp_path, monkeypatch):
    ruta = tmp_path / "gato.png"
    ruta.write_bytes(b"png")
    respuestas = iter(["NO_TEXT", "NONE"])
    monkeypatch.setattr(ing, "_preguntar_imagen", lambda r, p: next(respuestas))
    assert ing._cargar_archivo(ruta) == []


@pytest.fixture
def whisper_falso(monkeypatch):
    """Whisper que 'dice' una frase cada 20 s durante 5 minutos; DS2 al minuto 2, DS3 al 4."""
    llamadas = {"dispositivos": []}
    monkeypatch.setattr(config, "WHISPER_DEVICE", "cpu")

    class Modelo:
        def __init__(self, *a, device, **k):
            self.device = device
            llamadas["dispositivos"].append(device)

        def transcribe(self, ruta, **opciones):
            if self.device == "cuda" and llamadas.get("cuda_falla"):
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
            llamadas.update(opciones)
            textos = {120: " Vendrick waited in Drangleic.", 240: " Lothric refused the flame."}
            segmentos = [NS(start=t, end=t + 19, text=textos.get(t, f" Frase {t}.")) for t in range(0, 300, 20)]
            return iter(segmentos), NS(language="en")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Modelo))
    return llamadas


def test_video_de_varios_juegos_se_parte_por_minutos(tmp_path, whisper_falso):
    ruta = tmp_path / "Retrospectiva.mp4"
    ruta.write_bytes(b"mp4")

    fragmentos = ing._fragmentar(ing._cargar_archivo(ruta), ruta.name, INDICE)

    assert "Frampt" in whisper_falso["hotwords"]
    assert [f.metadata["seccion"] for f in fragmentos] == ["00:00 - 01:39", "01:40 - 03:19", "03:20 - 04:59"]
    assert [f.metadata["juegos"] for f in fragmentos] == [[], ["DS2"], ["DS3"]]
    assert fragmentos[1].page_content.startswith("Retrospectiva (DS2) > 01:40 - 03:19\n\n")
    assert fragmentos[1].metadata["segundo"] == 100


def test_minuto_con_horas():
    assert ing._minuto(75) == "01:15"
    assert ing._minuto(3725) == "1:02:05"


def test_archivos_pesados_van_al_final(tmp_path, monkeypatch):
    for nombre in ["The Video.mp4", "a.jpg", "b__DS1.md", "c.pdf"]:
        (tmp_path / nombre).write_bytes(b"x")
    monkeypatch.setattr(config, "DOCS_PATH", tmp_path)
    assert [r.name for r in ing._archivos_a_procesar()] == ["b__DS1.md", "c.pdf", "a.jpg", "The Video.mp4"]


def test_titulos_de_imagen_se_normalizan():
    texto = "## " + "Un párrafo larguísimo que el modelo marcó como título por error. " * 3 + "\nThe Age of Fire:\n\nAfter the defeat...\n# Boletaria"
    normalizado = ing._normalizar_titulos(texto).splitlines()
    assert not normalizado[0].startswith("#")
    assert normalizado[1] == "## The Age of Fire"
    assert normalizado[-1] == "## Boletaria"


def test_los_fragmentos_no_empiezan_con_punto(tmp_path):
    ruta = tmp_path / "frases__DS1.md"
    ruta.write_text("---\ntitle: Frases\njuego: DS1\n---\n\n" + "Esta es una frase bastante larga sobre Gwyn. " * 60, encoding="utf-8")
    for fragmento in ing._fragmentar(ing._cargar_archivo(ruta), ruta.name, INDICE):
        assert not fragmento.page_content.split("\n\n", 1)[1].startswith(".")


def test_video_vuelve_a_cpu_si_la_gpu_falla(tmp_path, whisper_falso, monkeypatch):
    ruta = tmp_path / "Retrospectiva.mp4"
    ruta.write_bytes(b"mp4")
    monkeypatch.setattr(config, "WHISPER_DEVICE", "cuda")
    monkeypatch.setattr(ing, "_habilitar_dlls_cuda", lambda: None)
    whisper_falso["cuda_falla"] = True

    documentos = ing._cargar_archivo(ruta)

    assert whisper_falso["dispositivos"] == ["cuda", "cpu"]
    assert len(documentos) == 3
