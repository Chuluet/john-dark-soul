"""Endpoints de los documentos que amplían la base de conocimiento."""

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from app.schemas import BaseDocumentOut, BaseDocumentState, DocumentOut, DocumentState
from app.security import Usuario, get_current_user
from services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
    description=(
        "Uploads a file, processes it and stores its embeddings. Responds once the file is "
        "indexed, so the agent can use it right away. Audio and video take longer because "
        "they are transcribed."
    ),
)
def subir(
    archivo: UploadFile = File(description="PDF, TXT, MD, DOCX, CSV, JPG, PNG, MP3 or MP4."),
    usuario: Usuario = Depends(get_current_user),
) -> dict:
    """Sube un archivo, lo procesa y guarda sus embeddings.

    Responde cuando el archivo ya está indexado: desde ese momento el agente
    puede usarlo. Audio y video tardan más porque se transcriben.
    """
    return document_service.subir(usuario.sub, archivo.filename, archivo.file)


@router.get("", response_model=list[DocumentOut], summary="List documents", description="Files uploaded by the user.")
def listar(usuario: Usuario = Depends(get_current_user)) -> list[dict]:
    """Archivos subidos por el usuario."""
    return document_service.listar(usuario.sub)


# Las rutas de /knowledge-base van antes que /{id}: si no, FastAPI intentaría
# leer "knowledge-base" como el id numérico de un documento.
@router.get(
    "/knowledge-base",
    response_model=list[BaseDocumentOut],
    summary="List knowledge base documents",
    description="Files of the original knowledge base, with whether the user has them enabled.",
)
def listar_base(usuario: Usuario = Depends(get_current_user)) -> list[dict]:
    """Archivos de la base original, con su estado para el usuario."""
    return document_service.listar_base(usuario.sub)


@router.patch(
    "/knowledge-base",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Enable or disable a knowledge base document",
    description="Only affects the user's answers: a disabled document is not used by the agent.",
)
def cambiar_estado_base(
    estado: BaseDocumentState, usuario: Usuario = Depends(get_current_user)
) -> Response:
    """Activa o desactiva un archivo de la base original para el usuario."""
    document_service.cambiar_estado_base(usuario.sub, estado.source, estado.active)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Enable or disable an uploaded document",
    description="Only affects the user's answers: a disabled document is not used by the agent.",
)
def cambiar_estado(
    id: int, estado: DocumentState, usuario: Usuario = Depends(get_current_user)
) -> Response:
    """Activa o desactiva uno de los archivos que subió el usuario."""
    document_service.cambiar_estado(usuario.sub, id, estado.active)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    description="Deletes one of the user's documents and its chunks from the vector database.",
)
def borrar(id: int, usuario: Usuario = Depends(get_current_user)) -> Response:
    """Borra un documento del usuario y sus fragmentos de la base vectorial."""
    document_service.borrar(usuario.sub, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
