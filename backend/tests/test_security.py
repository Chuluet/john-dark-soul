"""Pruebas de la validación de tokens sin depender de un Keycloak real.

Se firma con una llave RSA generada aquí y se reemplaza el cliente JWKS
para que devuelva su llave pública.
"""

import re
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import config, security
from app.main import app

LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTRA_LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def jwks_falso(monkeypatch):
    llave_publica = SimpleNamespace(key=LLAVE.public_key())
    monkeypatch.setattr(
        security._jwks, "get_signing_key_from_jwt", lambda token: llave_publica
    )


@pytest.fixture
def cliente():
    return TestClient(app)


def _token(llave=LLAVE, **cambios) -> str:
    ahora = int(time.time())
    claims = {
        "sub": "1234",
        "preferred_username": "demo",
        "email": "demo@john-dark-soul.local",
        "iss": config.KEYCLOAK_ISSUER,
        "azp": config.KEYCLOAK_CLIENT_ID,
        "iat": ahora,
        "exp": ahora + 300,
        "realm_access": {"roles": ["user"]},
    }
    claims.update(cambios)
    return jwt.encode(claims, llave, algorithm="RS256")


def _get_me(cliente, token):
    return cliente.get("/me", headers={"Authorization": f"Bearer {token}"})


def test_me_con_token_valido(cliente):
    respuesta = _get_me(cliente, _token())
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "sub": "1234",
        "username": "demo",
        "email": "demo@john-dark-soul.local",
        "roles": ["user"],
    }


def test_sin_token_devuelve_401(cliente):
    respuesta = cliente.get("/me")
    assert respuesta.status_code == 401
    assert respuesta.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda: _token(exp=int(time.time()) - 10), id="expirado"),
        pytest.param(lambda: _token(iss="http://otro/realms/x"), id="otro-emisor"),
        pytest.param(lambda: _token(azp="otro-cliente"), id="otro-cliente"),
        pytest.param(lambda: _token(llave=OTRA_LLAVE), id="firma-invalida"),
        pytest.param(lambda: "no-es-un-jwt", id="basura"),
    ],
)
def test_tokens_rechazados(cliente, token):
    assert _get_me(cliente, token()).status_code == 401


def test_todas_las_rutas_exigen_token(cliente):
    """El enunciado exige que ningún endpoint quede expuesto sin autenticación."""
    rutas = app.openapi()["paths"]
    assert rutas
    for ruta, metodos in rutas.items():
        for metodo in metodos:
            respuesta = cliente.request(metodo, re.sub(r"\{\w+\}", "1", ruta))
            assert respuesta.status_code == 401, f"{metodo} {ruta} quedó expuesto"
