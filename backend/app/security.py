"""Autenticación: valida los JWT emitidos por Keycloak.

El registro y el login los hace Keycloak; el backend solo comprueba que el
token del header `Authorization: Bearer <token>` esté firmado por el realm,
no haya expirado y haya sido emitido para el cliente del frontend.
"""

from dataclasses import dataclass, field

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config

# auto_error=False: sin header devolvemos 401 (con WWW-Authenticate) y no el
# 403 que FastAPI usa por defecto.
_bearer = HTTPBearer(auto_error=False)

# Descarga y cachea las llaves públicas del realm; si llega un token firmado
# con una llave nueva (rotación), vuelve a consultar el JWKS.
_jwks = jwt.PyJWKClient(config.KEYCLOAK_JWKS_URL, cache_keys=True, timeout=5)


@dataclass(frozen=True)
class Usuario:
    """Usuario autenticado, extraído de los claims del token."""

    sub: str
    username: str
    email: str | None = None
    roles: list[str] = field(default_factory=list)


def _no_autorizado(detalle: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalle,
        headers={"WWW-Authenticate": "Bearer"},
    )


def decodificar_token(token: str) -> dict:
    """Verifica firma, expiración, emisor y cliente; devuelve los claims."""
    try:
        llave = _jwks.get_signing_key_from_jwt(token)
    except jwt.PyJWKClientConnectionError as error:
        # Keycloak caído o inalcanzable: no es culpa del cliente.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo contactar al servidor de autenticación.",
        ) from error
    except jwt.PyJWTError as error:
        raise _no_autorizado("Token inválido.") from error

    try:
        claims = jwt.decode(
            token,
            llave.key,
            algorithms=["RS256"],
            issuer=config.KEYCLOAK_ISSUER,
            # Keycloak pone `aud: account` en los access tokens de clientes
            # públicos; el cliente que pidió el token va en `azp`.
            options={"verify_aud": False, "require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as error:
        raise _no_autorizado("El token expiró.") from error
    except jwt.PyJWTError as error:
        raise _no_autorizado("Token inválido.") from error

    if claims.get("azp") != config.KEYCLOAK_CLIENT_ID:
        raise _no_autorizado("El token no fue emitido para esta aplicación.")
    return claims


def get_current_user(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Usuario:
    """Dependencia de FastAPI: todos los endpoints la usan."""
    if credenciales is None:
        raise _no_autorizado("Falta el token de acceso.")

    claims = decodificar_token(credenciales.credentials)
    return Usuario(
        sub=claims["sub"],
        username=claims.get("preferred_username", claims["sub"]),
        email=claims.get("email"),
        roles=claims.get("realm_access", {}).get("roles", []),
    )
