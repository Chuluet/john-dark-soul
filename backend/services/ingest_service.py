"""Ingesta: convierte los archivos de DOCS_PATH en vectores dentro de pgvector.

El pipeline es siempre el mismo, y es el corazón de cualquier sistema RAG:

    cargar -> fragmentar -> embeber -> almacenar

Ejecutar con (desde backend/):
    uv run python -m services.ingest_service
    uv run python -m services.ingest_service --reset      # reconstruye desde cero
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from langchain_community.document_loaders import (
    BSHTMLLoader,
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document
import ollama
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rich.console import Console
from rich.table import Table

from app import config
from vectorstore import vectorstore as backend

console = Console()


def _separar_frontmatter(documento: Document) -> Document:
    """Pasa el bloque '---' de los .md de la wiki (title, juego, categoria, fuente) a metadata.

    La 'fuente' del frontmatter (URL de la wiki) se guarda como 'url', porque
    'fuente' se reserva para la ruta del archivo (la usa backend.borrar_fuente).
    """
    texto = documento.page_content
    if not texto.startswith("---"):
        return documento
    _, cabecera, cuerpo = texto.split("---", 2)
    for linea in cabecera.strip().splitlines():
        clave, _, valor = linea.partition(":")
        documento.metadata[clave.strip()] = valor.strip()
    if "fuente" in documento.metadata:
        documento.metadata["url"] = documento.metadata.pop("fuente")
    documento.page_content = cuerpo.strip()
    return documento


PROMPT_TEXTO = "Transcribe all the text in this image. If there is no text, answer only NO_TEXT."
PROMPT_DESCRIPCION = (
    "Describe this image. If it shows a boss, character, location or item from a video game "
    "(especially Dark Souls), describe it in detail and name it if you recognize it. "
    "If it does not, answer only NONE."
)


def _preguntar_imagen(ruta: Path, prompt: str) -> str:
    """Envía la imagen al modelo de visión local con el cliente de ollama."""
    cliente = ollama.Client(host=config.OLLAMA_BASE_URL)
    return cliente.chat(
        model=config.VISION_MODEL,
        messages=[{"role": "user", "content": prompt, "images": [ruta.read_bytes()]}],
        options={"temperature": 0},
    ).message.content.strip()


def _describir_imagen(ruta: Path) -> list[Document]:
    """Indexa una imagen: primero su texto; si no tiene, su descripción.

    Si no tiene texto ni muestra algo de videojuego, no se indexa.
    """
    texto = _preguntar_imagen(ruta, PROMPT_TEXTO)
    if "NO_TEXT" not in texto:
        return [Document(page_content=texto, metadata={"tipo_imagen": "texto"})]

    descripcion = _preguntar_imagen(ruta, PROMPT_DESCRIPCION)
    if "NONE" in descripcion[:20]:
        return []
    return [Document(page_content=descripcion, metadata={"tipo_imagen": "descripcion"})]


def _transcribir(ruta: Path) -> list[Document]:
    """Transcribe el audio de un video o mp3 con Whisper local.

    Cada línea lleva su marca de tiempo para poder citar el minuto exacto.
    """
    # Import aquí: faster-whisper es pesado y solo se necesita para audio/video.
    from faster_whisper import WhisperModel

    # cpu_threads: usa todos los hilos del procesador (por defecto solo usa 4).
    modelo = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8", cpu_threads=os.cpu_count())
    segmentos, info = modelo.transcribe(str(ruta))
    lineas = [
        f"[{int(s.start // 60):02d}:{int(s.start % 60):02d}] {s.text.strip()}"
        for s in segmentos
    ]
    if not lineas:
        return []
    return [Document(page_content="\n".join(lineas), metadata={"tipo": "video", "idioma": info.language})]


def _cargar_archivo(ruta: Path) -> list[Document]:
    """Elige el loader adecuado según la extensión y devuelve los documentos."""
    sufijo = ruta.suffix.lower()

    if sufijo == ".pdf":
        # PyPDFLoader genera un Document por página, lo que da trazabilidad
        # de página en las citas.
        return PyPDFLoader(str(ruta)).load()
    if sufijo in {".jpg", ".jpeg", ".png"}:
        return _describir_imagen(ruta)
    if sufijo in {".mp4", ".mp3"}:
        return _transcribir(ruta)
    if sufijo == ".docx":
        return Docx2txtLoader(str(ruta)).load()
    if sufijo in {".html", ".htm"}:
        return BSHTMLLoader(str(ruta), open_encoding="utf-8").load()

    # .txt, .md, .tex y similares: texto plano.
    documentos = TextLoader(str(ruta), encoding="utf-8", autodetect_encoding=True).load()
    return [_separar_frontmatter(d) for d in documentos]


def _archivos_a_procesar() -> list[Path]:
    """Todos los archivos soportados dentro de DOCS_PATH, recursivamente."""
    if not config.DOCS_PATH.exists():
        return []

    return sorted(
        ruta
        for ruta in config.DOCS_PATH.rglob("*")
        if ruta.is_file()
        and ruta.suffix.lower() in config.EXTENSIONES_SOPORTADAS
        and not ruta.name.startswith(".")
    )


def _fragmentar(documentos: list[Document], fuente: str) -> list[Document]:
    """Parte los documentos en fragmentos indexables.

    RecursiveCharacterTextSplitter intenta cortar primero por párrafos, luego
    por líneas, luego por frases y solo al final por caracteres sueltos. Así
    los fragmentos tienden a respetar la estructura semántica del texto.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )
    fragmentos = splitter.split_documents(documentos)

    # Metadatos propios: permiten citar la fuente y borrar por archivo.
    for indice, fragmento in enumerate(fragmentos):
        fragmento.metadata["fuente"] = fuente
        fragmento.metadata["fragmento"] = indice
        # Se descartan metadatos con valor None.
        fragmento.metadata = {
            clave: valor
            for clave, valor in fragmento.metadata.items()
            if valor is not None
        }

    return fragmentos


def ingestar(reset: bool = False) -> int:
    """Indexa todos los documentos. Devuelve el total de fragmentos añadidos."""
    archivos = _archivos_a_procesar()

    if not archivos:
        console.print(
            f"[yellow]No hay archivos soportados en {config.DOCS_PATH}.[/yellow]\n"
            f"Copia tus documentos en la carpeta [bold]{config.DOCS_PATH}[/bold] "
            f"({', '.join(sorted(config.EXTENSIONES_SOPORTADAS))}) y vuelve a ejecutar."
        )
        return 0

    if reset:
        console.print("[yellow]Borrando la colección. Reconstruyendo…[/yellow]")
        store = backend.reiniciar_coleccion()
    else:
        store = backend.get_vectorstore()

    console.print(f"[dim]pgvector, colección: {backend.modo_activo}[/dim]")

    tabla = Table(title="Ingesta de documentos", show_lines=False)
    tabla.add_column("Archivo", style="cyan", overflow="fold")
    tabla.add_column("Fragmentos", justify="right", style="green")

    total = 0
    for ruta in archivos:
        fuente = str(ruta.relative_to(config.DOCS_PATH))

        try:
            documentos = _cargar_archivo(ruta)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]✗ {fuente}: {type(exc).__name__}: {exc}[/red]")
            continue

        fragmentos = _fragmentar(documentos, fuente)
        if not fragmentos:
            console.print(f"[yellow]· {fuente}: sin contenido útil (¿PDF escaneado o imagen sin texto ni personaje?)[/yellow]")
            continue

        # Reingesta idempotente: borramos los fragmentos previos de este
        # archivo antes de insertar los nuevos, para no duplicar.
        backend.borrar_fuente(store, fuente)

        # Aquí es donde se llama al modelo de embeddings: cada fragmento se
        # convierte en un vector y se guarda junto a su texto y metadatos.
        with console.status(f"Embebiendo {fuente} ({len(fragmentos)} fragmentos)…"):
            store.add_documents(fragmentos)

        tabla.add_row(fuente, str(len(fragmentos)))
        total += len(fragmentos)

    console.print(tabla)
    console.print(
        f"[bold green]✓ {total} fragmentos indexados.[/bold green] "
        f"Total en la colección: {backend.contar_fragmentos(store)}"
    )
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Indexa DOCS_PATH en la base de datos vectorial.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Borra la colección antes de indexar (reconstrucción completa).",
    )
    args = parser.parse_args()

    try:
        ingestar(reset=args.reset)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]Error en la ingesta:[/bold red] {type(exc).__name__}: {exc}")
        console.print(
            "[dim]Comprueba que Ollama está arriba y que el modelo de embeddings "
            f"'{config.EMBED_MODEL}' está descargado.[/dim]"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())