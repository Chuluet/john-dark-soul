"""Errores de negocio que los servicios lanzan y la API traduce a HTTP.

Los servicios no conocen FastAPI: cada error solo declara qué código HTTP le
corresponde, y `app.main` registra un único manejador que lo convierte en la
respuesta `{"detail": mensaje}`.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import ollama
from sqlalchemy.exc import SQLAlchemyError


class ErrorDeServicio(Exception):
    """Base de los errores que deben llegar al usuario con su mensaje."""

    status_code = 500

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class ServicioNoDisponible(ErrorDeServicio):
    """Ollama o Postgres no responden: no es culpa del usuario."""

    status_code = 503


class NoEncontrado(ErrorDeServicio):
    """El recurso no existe o no pertenece al usuario."""

    status_code = 404


class ArchivoNoSoportado(ErrorDeServicio):
    """La extensión del archivo subido no se puede procesar."""

    status_code = 415


class ArchivoDemasiadoGrande(ErrorDeServicio):
    """El archivo supera MAX_UPLOAD_MB."""

    status_code = 413


class ArchivoSinContenido(ErrorDeServicio):
    """El archivo se leyó pero no tiene texto indexable (vacío, PDF escaneado...)."""

    status_code = 422


# Fallos de infraestructura: Ollama caído o sin el modelo, Postgres caído.
FALLOS_DE_SERVICIO = (ConnectionError, httpx.HTTPError, ollama.ResponseError, SQLAlchemyError)


@contextmanager
def fallos_de_servicio(mensaje: str) -> Iterator[None]:
    """Convierte los fallos de Ollama o Postgres del bloque en `ServicioNoDisponible`."""
    try:
        yield
    except FALLOS_DE_SERVICIO as exc:
        raise ServicioNoDisponible(mensaje) from exc
