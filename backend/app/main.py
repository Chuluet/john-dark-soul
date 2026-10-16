"""Punto de entrada de la API.

Se ejecuta con `uv run uvicorn app.main:app --reload` desde `backend/`.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from controllers import auth_controller

app = FastAPI(
    title="john-dark-soul",
    description="Agente RAG sobre el lore de Dark Souls (DS1, DS2, DS3).",
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

# Cada router protege sus endpoints con `get_current_user`.
app.include_router(auth_controller.router)
