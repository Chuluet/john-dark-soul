"""Ingesta: convierte los archivos de DOCS_PATH en vectores dentro de pgvector.

El pipeline es siempre el mismo, y es el corazón de cualquier sistema RAG:

    cargar -> fragmentar -> embeber -> almacenar

Cada formato (.md, .pdf, imagen, video) se carga directamente, sin archivos
intermedios, y sale con los mismos metadatos: title, juego, juegos, tipo y
seccion. Así todos los fragmentos llevan la misma cabecera
'Título (juego) > Sección' y la búsqueda los trata igual.

Ejecutar con (desde backend/):
    uv run python -m services.ingest_service
    uv run python -m services.ingest_service --reset      # reconstruye desde cero

Sin --reset, los archivos que no cambiaron desde la última ingesta se saltan
(así el video no se vuelve a transcribir). Si cambias cómo se fragmenta o se
cargan los archivos, usa --reset.
"""

from __future__ import annotations

import argparse
import os
import re
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
from services.juegos import JUEGOS, IndiceJuegos
from vectorstore import vectorstore as backend

console = Console()

SUFIJO_JUEGO = re.compile(r"__(DS1|DS2|DS3|general)$", re.IGNORECASE)
EXTENSIONES_PESADAS = {".mp4", ".mp3", ".jpg", ".jpeg", ".png"}


def _metadatos_base(ruta: Path, tipo: str) -> dict:
    """title/juego/tipo sacados del nombre del archivo.

    Usa la misma convención que la wiki: 'nombre__DS1.pdf' -> juego DS1.
    Sin sufijo el juego es 'general' (desconocido o de varios juegos); en ese
    caso _fragmentar intenta deducirlo del texto de cada fragmento.
    """
    sufijo = SUFIJO_JUEGO.search(ruta.stem)
    titulo = re.sub(r"[-_\s]+", " ", SUFIJO_JUEGO.sub("", ruta.stem)).strip() or ruta.stem
    juego = sufijo.group(1).upper() if sufijo and sufijo.group(1).lower() != "general" else "general"
    return {"title": titulo, "juego": juego, "tipo": tipo}


def _separar_frontmatter(documento: Document, base: dict) -> Document:
    """Pasa el bloque '---' de los .md de la wiki (title, juego, categoria, fuente) a metadata.

    `base` (sacado del nombre del archivo) se usa si el archivo no tiene
    frontmatter; lo que diga el frontmatter tiene prioridad.

    La 'fuente' del frontmatter (URL de la wiki) se guarda como 'url', porque
    'fuente' se reserva para la ruta del archivo (la usa backend.borrar_fuente).
    """
    documento.metadata.update(base)
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


PROMPT_TEXTO = (
    "Transcribe all the text in this image as Markdown. When a line is a section title "
    "(for example 'The Age of Fire:'), write it as a '## ' heading. "
    "If there is no text, answer only NO_TEXT."
)
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


MAX_LARGO_TITULO = 80


def _normalizar_titulos(texto: str) -> str:
    """Deja como '## ' solo lo que de verdad parece un título.

    El modelo de visión no marca los títulos de forma consistente: a veces
    convierte un párrafo entero en '## ' y a veces no marca nada. Una línea
    corta que termina en ':' ('The Age of Fire:') es un título; un '## ' más
    largo que MAX_LARGO_TITULO es un párrafo.
    """
    lineas = []
    for linea in texto.splitlines():
        limpia = linea.strip().lstrip("#").strip()
        if linea.lstrip().startswith("#") and len(limpia) > MAX_LARGO_TITULO:
            lineas.append(limpia)
        elif limpia.endswith(":") and 0 < len(limpia) <= MAX_LARGO_TITULO and not limpia[:-1].endswith((".", ",")):
            lineas.append(f"## {limpia[:-1]}")
        elif linea.lstrip().startswith("#") and limpia:
            lineas.append(f"## {limpia}")
        else:
            lineas.append(linea)
    return "\n".join(lineas)


def _describir_imagen(ruta: Path) -> list[Document]:
    """Indexa una imagen: primero su texto (con secciones '##'); si no tiene, su descripción.

    Si no tiene texto ni muestra algo de videojuego, no se indexa.
    """
    texto = _preguntar_imagen(ruta, PROMPT_TEXTO)
    if "NO_TEXT" not in texto[:20]:
        return [Document(page_content=_normalizar_titulos(texto), metadata=_metadatos_base(ruta, "imagen"))]

    descripcion = _preguntar_imagen(ruta, PROMPT_DESCRIPCION)
    if "NONE" in descripcion[:20]:
        return []
    metadatos = _metadatos_base(ruta, "imagen") | {"seccion": "Descripción de la imagen"}
    return [Document(page_content=descripcion, metadata=metadatos)]


def _minuto(segundos: float) -> str:
    return f"{int(segundos // 3600)}:{int(segundos % 3600 // 60):02d}:{int(segundos % 60):02d}" \
        if segundos >= 3600 else f"{int(segundos // 60):02d}:{int(segundos % 60):02d}"


def _habilitar_dlls_cuda() -> None:
    """En Windows, deja que ctranslate2 encuentre cuBLAS/cuDNN de los paquetes nvidia-*.

    `uv sync --extra gpu` instala esas DLL dentro de site-packages/nvidia/*/bin,
    pero Windows no las busca ahí por su cuenta.
    """
    if sys.platform != "win32":
        return
    try:
        import nvidia
    except ImportError:
        return  # sin el extra gpu: se usarán las de un CUDA instalado en el sistema, si lo hay
    for base in nvidia.__path__:
        for carpeta in Path(base).glob("*/bin"):
            os.add_dll_directory(str(carpeta))
            os.environ["PATH"] = f"{carpeta}{os.pathsep}{os.environ['PATH']}"


def _dispositivo_whisper() -> str:
    """'cuda' o 'cpu' según WHISPER_DEVICE ('auto' usa la GPU si hay una)."""
    if config.WHISPER_DEVICE != "auto":
        return config.WHISPER_DEVICE
    import ctranslate2

    return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"


def _segmentos_whisper(ruta: Path, dispositivo: str):
    """Transcribe con Whisper en el dispositivo dado; devuelve (segmentos, idioma)."""
    # Import aquí: faster-whisper es pesado y solo se necesita para audio/video.
    from faster_whisper import WhisperModel

    if dispositivo == "cuda":
        _habilitar_dlls_cuda()
    modelo = WhisperModel(
        config.WHISPER_MODEL,
        device=dispositivo,
        compute_type="float16" if dispositivo == "cuda" else "int8",
        # cpu_threads: usa todos los hilos del procesador (por defecto solo usa 4).
        cpu_threads=os.cpu_count(),
    )
    # hotwords: nombres propios que Whisper escribiría mal ("Framped" en vez de "Frampt").
    segmentos, info = modelo.transcribe(str(ruta), hotwords=config.WHISPER_HOTWORDS)
    # list(): la transcripción es perezosa; así los errores de CUDA salen aquí.
    return list(segmentos), info.language


def _transcribir(ruta: Path) -> list[Document]:
    """Transcribe el audio de un video o mp3 con Whisper local.

    Los segmentos se agrupan en bloques de VIDEO_BLOQUE_SEGUNDOS; cada bloque es
    un Document con su rango de tiempo como sección ('12:30 - 13:59'), para
    poder citar el minuto exacto. Los bloques se fragmentan después con el
    mismo tamaño que el resto de documentos.

    Con GPU es ~7 veces más rápido que con CPU. Si la GPU falla (faltan las
    librerías de CUDA o no hay memoria), se repite en CPU.
    """
    dispositivo = _dispositivo_whisper()
    try:
        segmentos, idioma = _segmentos_whisper(ruta, dispositivo)
    except RuntimeError as exc:
        if dispositivo != "cuda":
            raise
        console.print(f"[yellow]Whisper no pudo usar la GPU ({exc}); se usa la CPU.[/yellow]")
        segmentos, idioma = _segmentos_whisper(ruta, "cpu")

    bloques: list[list] = []
    for segmento in segmentos:
        if not bloques or segmento.start - bloques[-1][0].start >= config.VIDEO_BLOQUE_SEGUNDOS:
            bloques.append([])
        bloques[-1].append(segmento)

    documentos = []
    for bloque in bloques:
        metadatos = _metadatos_base(ruta, "video") | {
            "idioma": idioma,
            "seccion": f"{_minuto(bloque[0].start)} - {_minuto(bloque[-1].end)}",
            "segundo": int(bloque[0].start),
        }
        texto = " ".join(s.text.strip() for s in bloque)
        documentos.append(Document(page_content=texto, metadata=metadatos))
    return documentos


def _cargar_pdf(ruta: Path) -> list[Document]:
    """Un Document por página, con 'Página N' como sección para poder citarla."""
    documentos = []
    for pagina in PyPDFLoader(str(ruta)).load():
        if not pagina.page_content.strip():
            continue  # página escaneada sin capa de texto
        numero = pagina.metadata.get("page", 0) + 1
        metadatos = _metadatos_base(ruta, "pdf") | {"seccion": f"Página {numero}", "pagina": numero}
        documentos.append(Document(page_content=pagina.page_content, metadata=metadatos))
    return documentos


def _cargar_archivo(ruta: Path) -> list[Document]:
    """Elige el loader adecuado según la extensión y devuelve los documentos.

    Todos salen con los mismos metadatos (title, juego, tipo y, si aplica,
    seccion), así _fragmentar les pone la misma cabecera sin importar el formato.
    """
    sufijo = ruta.suffix.lower()

    if sufijo == ".pdf":
        return _cargar_pdf(ruta)
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
    tipo = "wiki" if sufijo == ".md" else "texto"
    return [_separar_frontmatter(d, _metadatos_base(ruta, tipo)) for d in documentos]


def _archivos_a_procesar() -> list[Path]:
    """Todos los archivos soportados dentro de DOCS_PATH, recursivamente.

    Los de texto van primero y los que pasan por un modelo (imágenes, video)
    al final: así la wiki queda indexada aunque la transcripción tarde.
    """
    if not config.DOCS_PATH.exists():
        return []

    return sorted(
        (
            ruta
            for ruta in config.DOCS_PATH.rglob("*")
            if ruta.is_file()
            and ruta.suffix.lower() in config.EXTENSIONES_SOPORTADAS
            and not ruta.name.startswith(".")
        ),
        key=lambda ruta: (ruta.suffix.lower() in EXTENSIONES_PESADAS, str(ruta).lower()),
    )


def _indice_juegos(archivos: list[Path]) -> IndiceJuegos:
    """Índice de nombres propios por juego, a partir del frontmatter de los .md."""
    pares = []
    for ruta in archivos:
        if ruta.suffix.lower() != ".md":
            continue
        cabecera = ruta.read_text(encoding="utf-8", errors="replace").split("---", 2)
        if len(cabecera) < 3:
            continue
        campos = dict(re.findall(r"(?m)^(title|juego):\s*(.+?)\s*$", cabecera[1]))
        if "title" in campos and "juego" in campos:
            pares.append((campos["title"], campos["juego"]))
    return IndiceJuegos(pares)


TITULO_SECCION = re.compile(r"^(##+) (.+)$", re.MULTILINE)


def _seccion_en(texto: str, posicion: int) -> str | None:
    """Sección ('Lore' o 'Lore > Dark Souls') vigente en esa posición del texto."""
    ruta: dict[int, str] = {}
    for titulo in TITULO_SECCION.finditer(texto):
        if titulo.start() > posicion:
            break
        nivel = len(titulo.group(1))
        ruta = {n: t for n, t in ruta.items() if n < nivel}
        ruta[nivel] = titulo.group(2).strip().rstrip(":")
    return " > ".join(ruta[n] for n in sorted(ruta)) or None


def _fragmentar(documentos: list[Document], fuente: str, indice: IndiceJuegos | None = None) -> list[Document]:
    """Parte los documentos en fragmentos indexables.

    RecursiveCharacterTextSplitter intenta cortar primero por párrafos, luego
    por líneas, luego por frases y solo al final por caracteres sueltos. Así
    los fragmentos tienden a respetar la estructura semántica del texto. El
    tamaño (CHUNK_SIZE/CHUNK_OVERLAP) es el mismo para todos los formatos.

    Cada fragmento empieza con una cabecera 'Título (juego) > Sección': así el
    embedding sabe de qué trata aunque el título haya quedado en otro fragmento.

    'juegos' (lista) queda en todos los fragmentos: el juego del archivo si se
    conoce, o los que se deducen del texto del propio fragmento si no (el video
    habla de los tres juegos, un PDF puede no decirlo). Puede quedar vacía.
    """
    indice = indice or IndiceJuegos()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        # El separador se queda al final del trozo: el punto acompaña a su
        # frase en vez de abrir el fragmento siguiente con ". ".
        keep_separator="end",
        length_function=len,
        add_start_index=True,
    )

    fragmentos = []
    for documento in documentos:
        for fragmento in splitter.split_documents([documento]):
            metadatos = fragmento.metadata
            # Sección por los '##' del texto (wiki, imágenes); si no hay, la que
            # trae el loader (página del PDF, minuto del video).
            seccion = _seccion_en(documento.page_content, metadatos.pop("start_index", 0)) \
                or metadatos.get("seccion")

            juego = metadatos.get("juego")
            juegos = [juego] if juego in JUEGOS else indice.detectar(fragmento.page_content)
            metadatos["juegos"] = juegos

            cabecera = metadatos.get("title") or Path(fuente).stem
            if juegos:
                cabecera += f" ({', '.join(juegos)})"
            if seccion:
                metadatos["seccion"] = seccion
                cabecera += f" > {seccion}"
            fragmento.page_content = f"{cabecera}\n\n{fragmento.page_content}"
            fragmentos.append(fragmento)

    # Metadatos propios: permiten citar la fuente y borrar por archivo.
    for indice_fragmento, fragmento in enumerate(fragmentos):
        fragmento.metadata["fuente"] = fuente
        fragmento.metadata["fragmento"] = indice_fragmento
        # Se descartan metadatos con valor None.
        fragmento.metadata = {
            clave: valor
            for clave, valor in fragmento.metadata.items()
            if valor is not None
        }

    return fragmentos


def _huella(ruta: Path) -> str:
    """Identifica una versión del archivo (tamaño + fecha de modificación)."""
    estado = ruta.stat()
    return f"{estado.st_size}-{estado.st_mtime_ns}"


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
    indice = _indice_juegos(archivos)

    tabla = Table(title="Ingesta de documentos", show_lines=False)
    tabla.add_column("Archivo", style="cyan", overflow="fold")
    tabla.add_column("Fragmentos", justify="right", style="green")

    total = saltados = 0
    for ruta in archivos:
        fuente = str(ruta.relative_to(config.DOCS_PATH))
        huella = _huella(ruta)

        if not reset and backend.huella_guardada(fuente) == huella:
            saltados += 1
            continue

        try:
            with console.status(f"Cargando {fuente}…"):
                documentos = _cargar_archivo(ruta)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]✗ {fuente}: {type(exc).__name__}: {exc}[/red]")
            continue

        fragmentos = _fragmentar(documentos, fuente, indice)
        if not fragmentos:
            console.print(f"[yellow]· {fuente}: sin contenido útil (¿PDF escaneado o imagen sin texto ni personaje?)[/yellow]")
            continue
        for fragmento in fragmentos:
            fragmento.metadata["huella"] = huella

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
    if saltados:
        console.print(f"[dim]{saltados} archivos sin cambios se saltaron (usa --reset para rehacerlos).[/dim]")
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
