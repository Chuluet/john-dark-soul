"""Modelos Pydantic de entrada y salida de la API."""

from datetime import datetime

from pydantic import BaseModel, Field


class Fuente(BaseModel):
    """Documento de la base de conocimiento que respalda una respuesta."""

    title: str
    game: str | None = None
    url: str | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000, description="Pregunta para el agente.")
    session_id: str = Field(
        default="default",
        min_length=1,
        max_length=100,
        description="Conversación del usuario; cada una tiene su propio estado en el grafo.",
    )


class ChatResponse(BaseModel):
    answer: str
    sources: list[Fuente]
    # True cuando el agente no encontró información suficiente y respondió
    # con el mensaje de rechazo.
    rejected: bool


class MessageOut(BaseModel):
    """Una interacción del historial."""

    id: int
    question: str
    answer: str
    sources: list[Fuente]
    rejected: bool
    created_at: datetime


class DocumentOut(BaseModel):
    """Archivo subido por el usuario e indexado en la base vectorial."""

    id: int
    filename: str
    tipo: str = Field(description="Formato con el que se procesó: pdf, wiki, texto, imagen, video...")
    juegos: list[str] = Field(description="Juegos detectados en el contenido (DS1, DS2, DS3).")
    chunks: int = Field(description="Fragmentos guardados en la base vectorial.")
    created_at: datetime
