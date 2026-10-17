"""Endpoints del chat con el agente."""

from fastapi import APIRouter, Depends, Query

from app.schemas import ChatRequest, ChatResponse, MessageOut
from app.security import Usuario, get_current_user
from services import chat_service, history_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def preguntar(
    peticion: ChatRequest, usuario: Usuario = Depends(get_current_user)
) -> dict:
    """Envía una pregunta al agente.

    Si no hay información suficiente, `rejected` es true y `answer` trae el
    mensaje de rechazo. Si Ollama o la base de datos fallan, responde 503.
    """
    return chat_service.preguntar(usuario.sub, peticion.question, peticion.session_id)


@router.get("/history", response_model=list[MessageOut])
def historial(
    limit: int = Query(50, ge=1, le=200, description="Máximo de mensajes a devolver."),
    usuario: Usuario = Depends(get_current_user),
) -> list[dict]:
    """Historial del usuario, del mensaje más reciente al más antiguo."""
    return history_service.listar(usuario.sub, limit)
