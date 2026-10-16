"""Endpoints de autenticación. El registro y el login los gestiona Keycloak."""

from fastapi import APIRouter, Depends

from app.security import Usuario, get_current_user

router = APIRouter(tags=["auth"])


@router.get("/me")
def me(usuario: Usuario = Depends(get_current_user)) -> Usuario:
    """Devuelve el usuario dueño del token."""
    return usuario
