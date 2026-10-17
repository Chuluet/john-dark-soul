"""Endpoints de los documentos que amplían la base de conocimiento."""

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from app.schemas import DocumentOut
from app.security import Usuario, get_current_user
from services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def subir(
    archivo: UploadFile = File(description="PDF, TXT, MD, DOCX, CSV, JPG, PNG, MP3 o MP4."),
    usuario: Usuario = Depends(get_current_user),
) -> dict:
    """Sube un archivo, lo procesa y guarda sus embeddings.

    Responde cuando el archivo ya está indexado: desde ese momento el agente
    puede usarlo. Audio y video tardan más porque se transcriben.
    """
    return document_service.subir(usuario.sub, archivo.filename, archivo.file)


@router.get("", response_model=list[DocumentOut])
def listar(usuario: Usuario = Depends(get_current_user)) -> list[dict]:
    """Archivos subidos por el usuario."""
    return document_service.listar(usuario.sub)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar(id: int, usuario: Usuario = Depends(get_current_user)) -> Response:
    """Borra un documento del usuario y sus fragmentos de la base vectorial."""
    document_service.borrar(usuario.sub, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
