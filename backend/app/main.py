"""Punto de entrada de la API.

Se ejecuta con `uv run uvicorn app.main:app --reload` desde `backend/`.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config
from controllers import auth_controller, chat_controller, documents_controller
from services.errores import ErrorDeServicio

app = FastAPI(
    title="john-dark-soul",
    description="RAG agent about the lore of Dark Souls (DS1, DS2, DS3). Every endpoint requires a Keycloak Bearer token.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    # El frontend envía el token en `Authorization`.
    allow_headers=["*"],
)


@app.exception_handler(ErrorDeServicio)
def _error_de_servicio(_: Request, exc: ErrorDeServicio) -> JSONResponse:
    """Los servicios lanzan errores de negocio; aquí se convierten en HTTP."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.mensaje})


# Cada router protege sus endpoints con `get_current_user`.
app.include_router(auth_controller.router)
app.include_router(chat_controller.router)
app.include_router(documents_controller.router)
