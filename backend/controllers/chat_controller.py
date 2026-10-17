"""Endpoints del chat con el agente."""

from fastapi import APIRouter, Depends, Path, Query

from app.schemas import ChatRequest, ChatResponse, ConversationOut, MessageOut
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


@router.get(
    "/conversations",
    response_model=list[ConversationOut],
    summary="Conversations",
    description="The user's conversations (messages grouped by `session_id`), most recent first.",
)
def conversaciones(
    limit: int = Query(20, ge=1, le=100, description="Maximum number of conversations to return."),
    usuario: Usuario = Depends(get_current_user),
) -> list[dict]:
    """Conversaciones del usuario, de la más reciente a la más antigua."""
    return history_service.conversaciones(usuario.sub, limit)


@router.get(
    "/conversations/{session_id}",
    response_model=list[MessageOut],
    summary="Conversation messages",
    description="Messages of one of the user's conversations, oldest first. 404 if it does not exist.",
)
def conversacion(
    session_id: str = Path(min_length=1, max_length=100),
    usuario: Usuario = Depends(get_current_user),
) -> list[dict]:
    """Mensajes de una conversación del usuario, en el orden en que se hicieron."""
    return history_service.conversacion(usuario.sub, session_id)
