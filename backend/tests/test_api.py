"""Endpoints de chat, historial y documentos (sin Keycloak, Ollama ni Postgres).

El usuario autenticado se inyecta con `dependency_overrides` y las capas de
abajo (grafo, tablas, pgvector) se sustituyen por dobles.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from sqlalchemy.exc import OperationalError

from app import config
from app.main import app
from app.security import Usuario, get_current_user
from services import chat_service, document_service, history_service, ingest_service
from vectorstore import vectorstore as backend

AHORA = datetime(2026, 10, 17, tzinfo=timezone.utc)
DEMO = Usuario(sub="sub-demo", username="demo")


@pytest.fixture
def cliente():
    app.dependency_overrides[get_current_user] = lambda: DEMO
    yield TestClient(app)
    app.dependency_overrides.clear()


def _postgres_caido(*_, **__):
    raise OperationalError("SELECT 1", {}, Exception("connection refused"))


# --- POST /chat ----------------------------------------------------------------

def test_chat_responde_con_fuentes_y_aisla_la_sesion_por_usuario(cliente, monkeypatch):
    llamadas = []

    def ask_falso(grafo, pregunta, sesion, user_id):
        llamadas.append((pregunta, sesion, user_id))
        return {"answer": "Artorias caminó por el Abismo.", "rejected": False, "error": None,
                "sources": [{"title": "Knight Artorias", "game": "DS1", "url": None}]}

    monkeypatch.setattr(chat_service, "ask", ask_falso)
    monkeypatch.setattr(chat_service, "_get_grafo", lambda: None)

    respuesta = cliente.post("/chat", json={"question": "  ¿Quién es Artorias? ", "session_id": "s1"})

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "answer": "Artorias caminó por el Abismo.",
        "sources": [{"title": "Knight Artorias", "game": "DS1", "url": None}],
        "rejected": False,
    }
    assert llamadas == [("¿Quién es Artorias?", "sub-demo:s1", "sub-demo")]


def test_chat_rechazo_es_200_con_rejected(cliente, monkeypatch):
    monkeypatch.setattr(chat_service, "_get_grafo", lambda: None)
    monkeypatch.setattr(chat_service, "ask", lambda *a: {
        "answer": "No tengo suficiente información...", "sources": [], "rejected": True, "error": None})

    respuesta = cliente.post("/chat", json={"question": "¿Cómo preparo sushi?"})

    assert respuesta.status_code == 200
    assert respuesta.json()["rejected"] is True


def test_chat_fallo_de_ollama_es_503_con_el_aviso_del_agente(cliente, monkeypatch):
    monkeypatch.setattr(chat_service, "_get_grafo", lambda: None)
    monkeypatch.setattr(chat_service, "ask", lambda *a: {
        "answer": "El servicio no está disponible.", "sources": [], "rejected": False,
        "error": "validate_intent: ConnectionError"})

    respuesta = cliente.post("/chat", json={"question": "¿Quién es Artorias?"})

    assert respuesta.status_code == 503
    assert respuesta.json() == {"detail": "El servicio no está disponible."}


@pytest.mark.parametrize("cuerpo", [{}, {"question": ""}, {"question": "x" * 2001}])
def test_chat_valida_la_pregunta(cliente, cuerpo):
    assert cliente.post("/chat", json=cuerpo).status_code == 422


# --- GET /chat/history ---------------------------------------------------------

def test_historial_del_usuario(cliente, monkeypatch):
    pedidos = []

    def listar_falso(user_id, limite):
        pedidos.append((user_id, limite))
        return [{"id": 1, "question": "q", "answer": "a", "rejected": False, "created_at": AHORA,
                 "sources": [{"title": "Knight Artorias", "game": "DS1", "url": None}]}]

    monkeypatch.setattr(history_service.db, "listar_mensajes", listar_falso)

    respuesta = cliente.get("/chat/history", params={"limit": 10})

    assert respuesta.status_code == 200
    assert respuesta.json()[0]["sources"][0]["title"] == "Knight Artorias"
    assert pedidos == [("sub-demo", 10)]


def test_historial_con_postgres_caido_es_503(cliente, monkeypatch):
    monkeypatch.setattr(history_service.db, "listar_mensajes", _postgres_caido)
    assert cliente.get("/chat/history").status_code == 503


def test_historial_valida_el_limite(cliente):
    assert cliente.get("/chat/history", params={"limit": 0}).status_code == 422
    assert cliente.get("/chat/history", params={"limit": 201}).status_code == 422


# --- POST /documents -----------------------------------------------------------

class StoreFalso:
    def __init__(self):
        self.agregados = []

    def add_documents(self, fragmentos):
        self.agregados.extend(fragmentos)


@pytest.fixture
def pgvector_falso(monkeypatch):
    """pgvector y la tabla `documents` en memoria; la ingesta real corre encima."""
    estado = SimpleNamespace(store=StoreFalso(), borrados=[], filas=[])
    monkeypatch.setattr(backend, "get_vectorstore", lambda: estado.store)
    monkeypatch.setattr(backend, "borrar_fuente",
                        lambda store, fuente, estricto=False: estado.borrados.append(fuente))
    monkeypatch.setattr(ingest_service, "_archivos_a_procesar", lambda: [])

    def guardar(**fila):
        estado.filas.append(fila)
        return {"id": len(estado.filas), "created_at": AHORA,
                **{k: fila[k] for k in ("filename", "tipo", "juegos", "chunks")}}

    monkeypatch.setattr(document_service.db, "guardar_documento", guardar)
    return estado


def _subir(cliente, nombre, contenido: bytes):
    return cliente.post("/documents", files={"archivo": (nombre, contenido)})


def test_subir_md_lo_indexa_y_registra(cliente, pgvector_falso):
    texto = "---\ntitle: Slave Knight Gael\njuego: DS3\n---\n\nGael sought the Dark Soul of the pygmies."

    respuesta = _subir(cliente, "gael__DS3.md", texto.encode())

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo | {"created_at": None} == {"id": 1, "filename": "gael__DS3.md", "tipo": "wiki",
                                             "juegos": ["DS3"], "chunks": 1, "created_at": None}
    fragmento = pgvector_falso.store.agregados[0]
    assert fragmento.page_content.startswith("Slave Knight Gael (DS3)")
    fila = pgvector_falso.filas[0]
    assert fila["user_id"] == "sub-demo"
    assert fila["fuente"] == fragmento.metadata["fuente"]
    assert fila["fuente"].startswith("uploads/") and fila["fuente"].endswith("/gael__DS3.md")


def test_subir_formato_no_soportado_es_415(cliente, pgvector_falso):
    respuesta = _subir(cliente, "virus.exe", b"MZ")
    assert respuesta.status_code == 415
    assert ".pdf" in respuesta.json()["detail"]


def test_subir_archivo_vacio_es_422(cliente, pgvector_falso):
    assert _subir(cliente, "vacio.txt", b"").status_code == 422


def test_subir_archivo_demasiado_grande_es_413(cliente, pgvector_falso, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 1)
    assert _subir(cliente, "grande.txt", b"a" * (1024 * 1024 + 1)).status_code == 413
    assert pgvector_falso.store.agregados == []


def test_subir_archivo_danado_es_422(cliente, pgvector_falso):
    respuesta = _subir(cliente, "roto.pdf", b"esto no es un pdf")
    assert respuesta.status_code == 422
    assert "dañado" in respuesta.json()["detail"]


def test_subir_con_ollama_caido_es_503(cliente, pgvector_falso, monkeypatch):
    def ollama_caido(_):
        raise ConnectionError("Failed to connect to Ollama")
    pgvector_falso.store.add_documents = ollama_caido

    assert _subir(cliente, "notas.txt", b"Artorias walked the Abyss.").status_code == 503


def test_si_no_se_registra_se_borran_los_fragmentos(cliente, pgvector_falso, monkeypatch):
    monkeypatch.setattr(document_service.db, "guardar_documento", _postgres_caido)

    assert _subir(cliente, "notas.txt", b"Artorias walked the Abyss.").status_code == 503
    fuente = pgvector_falso.store.agregados[0].metadata["fuente"]
    assert pgvector_falso.borrados[-1] == fuente


def test_nombre_seguro():
    assert document_service.nombre_seguro("C:\\fakepath\\gael__DS3.pdf") == "gael__DS3.pdf"
    assert document_service.nombre_seguro("../../etc/passwd") == "passwd"
    assert document_service.nombre_seguro("lore <final>?.md") == "lore _final__.md"
    assert document_service.nombre_seguro(None) == "archivo"
    largo = document_service.nombre_seguro("a" * 300 + ".pdf")
    assert len(largo) == 150 and largo.endswith(".pdf")


# --- GET /documents y DELETE /documents/{id} -----------------------------------

def test_listar_documentos_del_usuario(cliente, monkeypatch):
    monkeypatch.setattr(document_service.db, "listar_documentos", lambda user_id: [
        {"id": 7, "filename": "gael__DS3.pdf", "tipo": "pdf", "juegos": ["DS3"], "chunks": 4,
         "created_at": AHORA}] if user_id == "sub-demo" else [])

    respuesta = cliente.get("/documents")

    assert respuesta.status_code == 200
    assert [d["id"] for d in respuesta.json()] == [7]


def test_borrar_documento_ajeno_o_inexistente_es_404(cliente, monkeypatch):
    monkeypatch.setattr(document_service.db, "obtener_documento", lambda documento_id, user_id: None)
    assert cliente.delete("/documents/99").status_code == 404


def test_borrar_documento_quita_fragmentos_y_fila(cliente, monkeypatch):
    pasos = []
    monkeypatch.setattr(document_service.db, "obtener_documento",
                        lambda documento_id, user_id: {"id": documento_id, "fuente": "uploads/x/gael.pdf"})
    monkeypatch.setattr(backend, "borrar_fuente",
                        lambda store, fuente, estricto=False: pasos.append(("fragmentos", fuente, estricto)))
    monkeypatch.setattr(document_service.db, "borrar_documento", lambda i: pasos.append(("fila", i)))

    respuesta = cliente.delete("/documents/7")

    assert respuesta.status_code == 204
    assert pasos == [("fragmentos", "uploads/x/gael.pdf", True), ("fila", 7)]


def test_si_falla_borrar_fragmentos_la_fila_se_conserva(cliente, monkeypatch):
    filas_borradas = []
    monkeypatch.setattr(document_service.db, "obtener_documento",
                        lambda documento_id, user_id: {"id": documento_id, "fuente": "uploads/x/gael.pdf"})
    monkeypatch.setattr(backend, "borrar_fuente", lambda *a, **k: _postgres_caido())
    monkeypatch.setattr(document_service.db, "borrar_documento", filas_borradas.append)

    assert cliente.delete("/documents/7").status_code == 503
    assert filas_borradas == []
