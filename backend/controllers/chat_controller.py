"""Endpoints del chat con el agente."""

from fastapi import APIRouter, Depends, Query

from app.schemas import ChatRequest, ChatResponse, MessageOut
from app.security import Usuario, get_current_user
from services import chat_service, history_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponse,
    summary="Ask the agent",
    description=(
        "Sends a question to the agent. If there is not enough information, `rejected` is true "
        "and `answer` holds the rejection message. Answers follow the language of the question "
        "(English by default). Returns 503 if Ollama or the database are down."
    ),
)
def preguntar(
    peticion: ChatRequest, usuario: Usuario = Depends(get_current_user)
) -> dict:
    """Envía una pregunta al agente.

    Si no hay información suficiente, `rejected` es true y `answer` trae el
    mensaje de rechazo. Si Ollama o la base de datos fallan, responde 503.
    """
    return chat_service.preguntar(usuario.sub, peticion.question, peticion.session_id)


@router.get(
    "/history",
    response_model=list[MessageOut],
    summary="Chat history",
    description="The user's previous questions and answers, most recent first.",
)
def historial(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of messages to return."),
    usuario: Usuario = Depends(get_current_user),
) -> list[dict]:
    """Historial del usuario, del mensaje más reciente al más antiguo."""
    return history_service.listar(usuario.sub, limit)
