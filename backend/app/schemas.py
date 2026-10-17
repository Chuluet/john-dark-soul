"""Modelos Pydantic de entrada y salida de la API."""

from datetime import datetime

from pydantic import BaseModel, Field


class Fuente(BaseModel):
    """Documento de la base de conocimiento que respalda una respuesta."""

    title: str
    game: str | None = None
    # Archivo del que salieron los fragmentos ("knight-artorias__DS1.md").
    # Los mensajes guardados antes de añadirlo no lo traen.
    document: str | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000, description="Question for the agent.")
    session_id: str = Field(
        default="default",
        min_length=1,
        max_length=100,
        description="User conversation; each one keeps its own state in the agent graph.",
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
    session_id: str = Field(description="Conversation the message belongs to.")
    question: str
    answer: str
    sources: list[Fuente]
    rejected: bool
    created_at: datetime


class ConversationOut(BaseModel):
    """Una conversación del usuario: sus mensajes comparten `session_id`."""

    session_id: str
    title: str = Field(description="First question of the conversation.")
    updated_at: datetime = Field(description="Date of the last message.")
    messages: int = Field(description="Number of questions in the conversation.")


class DocumentOut(BaseModel):
    """Archivo subido por el usuario e indexado en la base vectorial."""

    id: int
    filename: str
    tipo: str = Field(description="Format it was processed as: pdf, wiki, texto, imagen, video...")
    juegos: list[str] = Field(description="Games detected in the content (DS1, DS2, DS3).")
    chunks: int = Field(description="Chunks stored in the vector database.")
    active: bool = Field(description="False if the user disabled it: the agent does not use it.")
    created_at: datetime


class BaseDocumentOut(BaseModel):
    """Archivo de la base de conocimiento original (indexado con la ingesta)."""

    source: str = Field(description="File name; identifies the document.")
    title: str
    tipo: str = Field(description="Format it was processed as: wiki, pdf, imagen, video...")
    juegos: list[str] = Field(description="Games detected in the content (DS1, DS2, DS3).")
    chunks: int = Field(description="Chunks stored in the vector database.")
    active: bool = Field(description="False if the user disabled it: the agent does not use it.")


class DocumentState(BaseModel):
    active: bool = Field(description="True to let the agent use the document, false to disable it.")


class BaseDocumentState(DocumentState):
    source: str = Field(min_length=1, description="`source` of the knowledge base document.")
