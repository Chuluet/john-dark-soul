"""Documentos que los usuarios suben para ampliar la base de conocimiento.

Flujo de carga (sección 2.4 del enunciado):

    recibir archivo -> extraer texto -> fragmentar -> embeber -> guardar en pgvector
    -> registrar en `documents` -> confirmar al usuario

La base de conocimiento es compartida: lo que sube un usuario le sirve al
agente para todos. Lo que es de cada usuario es la gestión: solo ve y borra
los archivos que subió él.
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO

from agents.tools import invalidar_titulos
from app import config, db
from services import ingest_service
from services.errores import (
    FALLOS_DE_SERVICIO,
    ArchivoDemasiadoGrande,
    ArchivoNoSoportado,
    ArchivoSinContenido,
    NoEncontrado,
    ServicioNoDisponible,
    fallos_de_servicio,
)
from vectorstore import vectorstore as backend

logger = logging.getLogger(__name__)

_BLOQUE = 1024 * 1024
_MAX_LARGO_NOMBRE = 150


def nombre_seguro(nombre: str | None) -> str:
    """Nombre de archivo sin rutas ni caracteres raros, conservando la extensión.

    Se conserva lo más posible porque la ingesta saca de él el título y el
    juego ('gael__DS3.pdf' -> título 'gael', juego DS3).
    """
    # El navegador puede mandar la ruta completa ('C:\\fakepath\\x.pdf').
    nombre = re.split(r"[\\/]", nombre or "")[-1]
    nombre = re.sub(r"[^\w.\- ()]", "_", nombre).strip(" .")
    if len(nombre) > _MAX_LARGO_NOMBRE:
        ruta = Path(nombre)
        nombre = ruta.stem[: _MAX_LARGO_NOMBRE - len(ruta.suffix)] + ruta.suffix
    return nombre or "archivo"


def _copiar_con_limite(origen: BinaryIO, destino: Path) -> int:
    """Copia el archivo subido a disco sin pasar de MAX_UPLOAD_MB; devuelve los bytes."""
    limite = config.MAX_UPLOAD_MB * 1024 * 1024
    total = 0
    with destino.open("wb") as salida:
        while bloque := origen.read(_BLOQUE):
            total += len(bloque)
            if total > limite:
                raise ArchivoDemasiadoGrande(
                    f"El archivo supera el máximo de {config.MAX_UPLOAD_MB} MB."
                )
            salida.write(bloque)
    return total


def subir(user_id: str, nombre: str | None, contenido: BinaryIO) -> dict:
    """Indexa un archivo subido y lo registra a nombre del usuario."""
    nombre = nombre_seguro(nombre)
    extension = Path(nombre).suffix.lower()
    if extension not in config.EXTENSIONES_SOPORTADAS:
        soportadas = ", ".join(sorted(config.EXTENSIONES_SOPORTADAS))
        raise ArchivoNoSoportado(
            f"Formato '{extension or 'sin extensión'}' no soportado. Formatos válidos: {soportadas}."
        )

    # `fuente` identifica los fragmentos en pgvector; el uuid evita chocar con
    # la wiki o con otro archivo del mismo nombre.
    fuente = f"uploads/{uuid.uuid4().hex}/{nombre}"

    # Los loaders (PDF, Whisper, docx...) leen desde una ruta: el archivo se
    # escribe en una carpeta temporal que se borra al terminar.
    carpeta = Path(tempfile.mkdtemp(prefix="upload-"))
    try:
        ruta = carpeta / nombre
        if _copiar_con_limite(contenido, ruta) == 0:
            raise ArchivoSinContenido("El archivo está vacío.")

        try:
            fragmentos = ingest_service.ingestar_archivo(ruta, fuente)
        except FALLOS_DE_SERVICIO as exc:
            raise ServicioNoDisponible(
                "No se pudo procesar el archivo: los modelos de Ollama o la base de datos no responden."
            ) from exc
        except Exception as exc:  # noqa: BLE001 - archivo dañado o ilegible para su loader
            logger.exception("No se pudo leer %s", nombre)
            raise ArchivoSinContenido(
                f"No se pudo leer el archivo ({type(exc).__name__}). ¿Está dañado?"
            ) from exc
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)

    if not fragmentos:
        raise ArchivoSinContenido(
            "No se encontró contenido útil en el archivo "
            "(¿PDF escaneado, imagen sin texto o audio sin voz?)."
        )

    juegos = sorted({juego for f in fragmentos for juego in f.metadata.get("juegos", [])})
    try:
        with fallos_de_servicio("No se pudo registrar el documento: la base de datos no responde."):
            return db.guardar_documento(
                user_id=user_id,
                filename=nombre,
                fuente=fuente,
                tipo=fragmentos[0].metadata.get("tipo", extension.lstrip(".")),
                juegos=juegos,
                chunks=len(fragmentos),
            )
    except Exception:
        # Sin fila en `documents` nadie podría borrar esos fragmentos.
        backend.borrar_fuente(None, fuente)
        raise


def listar(user_id: str) -> list[dict]:
    """Archivos que subió el usuario."""
    with fallos_de_servicio("No se pudo leer la lista de documentos: la base de datos no responde."):
        return db.listar_documentos(user_id)


def borrar(user_id: str, documento_id: int) -> None:
    """Borra el documento del usuario: primero sus fragmentos y luego la fila.

    En ese orden: si falla a mitad, el documento sigue en la lista y se puede
    reintentar, en vez de quedar fragmentos que el agente usa sin que nadie
    los vea.
    """
    with fallos_de_servicio("No se pudo borrar el documento: la base de datos no responde."):
        documento = db.obtener_documento(documento_id, user_id)
        if documento is None:
            raise NoEncontrado("El documento no existe.")
        backend.borrar_fuente(None, documento["fuente"], estricto=True)
        db.borrar_documento(documento_id)
    invalidar_titulos()
