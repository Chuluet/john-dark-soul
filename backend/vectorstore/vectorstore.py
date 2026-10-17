"""Almacén vectorial sobre PostgreSQL + pgvector.

Alternativa a `vectorstore.py` (Chroma). Expone exactamente la misma API
pública, de modo que la ingesta, las herramientas y el agente no cambian ni
una línea: solo se elige un módulo u otro con `VECTOR_BACKEND`.

**pgvector** es una extensión de PostgreSQL que añade el tipo de dato `vector`
y operadores de distancia (`<->` euclidiana, `<=>` coseno, `<#>` producto
interno), además de índices ANN (HNSW e IVFFlat). No es una base de datos
aparte: son vectores viviendo en tu Postgres de siempre, con transacciones,
JOINs, backups y permisos ya resueltos.

`langchain_postgres.PGVector` crea y usa dos tablas:

  langchain_pg_collection  -> una fila por colección (uuid, name, cmetadata)
  langchain_pg_embedding   -> un fila por fragmento (embedding, document,
                              cmetadata jsonb, collection_id)
"""

from __future__ import annotations

from langchain_postgres import PGVector
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app import config
from vectorstore.embedding import get_embeddings

# Modo efectivamente usado, para que la CLI lo informe (misma variable que en
# el módulo de Chroma).
modo_activo: str = "desconocido"

_motor: Engine | None = None


def _get_motor() -> Engine:
    """Engine de SQLAlchemy reutilizable para las consultas auxiliares."""
    global _motor
    if _motor is None:
        _motor = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    return _motor


def get_vectorstore() -> PGVector:
    """Almacén vectorial listo para indexar o consultar.

    En la primera llamada, PGVector ejecuta `CREATE EXTENSION IF NOT EXISTS
    vector` y crea sus tablas si no existen.
    """
    global modo_activo

    store = PGVector(
        embeddings=get_embeddings(),
        collection_name=config.PG_COLLECTION,
        connection=config.DATABASE_URL,
        # Guarda los metadatos como JSONB en vez de JSON: permite indexarlos
        # y filtrar por ellos con operadores nativos de Postgres.
        use_jsonb=True,
    )
    # Solo el detalle de conexión: quien lo imprime ya antepone el nombre
    # del backend (backend.NOMBRE).
    modo_activo = config.PG_COLLECTION
    return store


def comprobar_conexion() -> tuple[bool, str]:
    """¿Responde Postgres y tiene la extensión pgvector instalada?

    A diferencia de Chroma, aquí no hay respaldo embebido posible: Postgres es
    un servidor y si no está, no hay base vectorial.
    """
    try:
        with _get_motor().connect() as conexion:
            version = conexion.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar()
    except Exception as exc:  # noqa: BLE001
        return False, f"Postgres no responde ({type(exc).__name__})"

    if version is None:
        return True, "Postgres OK, pero la extensión 'vector' aún no está creada (se crea en la primera ingesta)"
    return True, f"Postgres OK, pgvector {version}"


def borrar_fuente(store: PGVector | None, fuente: str, estricto: bool = False) -> None:
    """Elimina los fragmentos de un archivo concreto.

    PGVector no expone borrado por filtro de metadatos, así que se hace con
    SQL sobre su propio esquema. `cmetadata->>'fuente'` extrae el campo del
    JSONB como texto.

    Con `estricto=True` los errores se propagan: al borrar un documento desde
    la API no puede quedar la fila borrada y sus fragmentos vivos.
    """
    sentencia = text(
        """
        DELETE FROM langchain_pg_embedding e
        USING langchain_pg_collection c
        WHERE e.collection_id = c.uuid
          AND c.name = :coleccion
          AND e.cmetadata->>'fuente' = :fuente
        """
    )
    try:
        with _get_motor().begin() as conexion:
            conexion.execute(
                sentencia,
                {"coleccion": config.PG_COLLECTION, "fuente": fuente},
            )
    except Exception:  # noqa: BLE001 - las tablas pueden no existir todavía
        if estricto:
            raise


def reiniciar_coleccion() -> PGVector:
    """Borra la colección entera y devuelve un store limpio."""
    store = get_vectorstore()
    try:
        store.delete_collection()
    except Exception:  # noqa: BLE001
        pass
    return get_vectorstore()


def contar_fragmentos(store: PGVector | None = None) -> int:
    """Número de fragmentos indexados en la colección."""
    sentencia = text(
        """
        SELECT count(*)
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
        WHERE c.name = :coleccion
        """
    )
    try:
        with _get_motor().connect() as conexion:
            return conexion.execute(
                sentencia, {"coleccion": config.PG_COLLECTION}
            ).scalar_one()
    except Exception:  # noqa: BLE001
        return 0


def listar_fuentes(store: PGVector | None = None) -> list[str]:
    """Nombres de archivo distintos presentes en la colección."""
    sentencia = text(
        """
        SELECT DISTINCT e.cmetadata->>'fuente' AS fuente
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
        WHERE c.name = :coleccion
          AND e.cmetadata->>'fuente' IS NOT NULL
        ORDER BY fuente
        """
    )
    try:
        with _get_motor().connect() as conexion:
            filas = conexion.execute(sentencia, {"coleccion": config.PG_COLLECTION})
            return [fila.fuente for fila in filas]
    except Exception:  # noqa: BLE001
        return []

def huella_guardada(fuente: str) -> str | None:
    """Huella (tamaño + fecha) con la que se indexó un archivo, o None si no está.

    La ingesta la compara con la del archivo actual para saltarse los que no
    cambiaron (por ejemplo, no volver a transcribir un video).
    """
    sentencia = text(
        """
        SELECT e.cmetadata->>'huella'
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
        WHERE c.name = :coleccion
          AND e.cmetadata->>'fuente' = :fuente
        LIMIT 1
        """
    )
    try:
        with _get_motor().connect() as conexion:
            return conexion.execute(
                sentencia, {"coleccion": config.PG_COLLECTION, "fuente": fuente}
            ).scalar()
    except Exception:  # noqa: BLE001
        return None


# Los archivos subidos desde la web se guardan con fuente 'uploads/<uuid>/<nombre>';
# todo lo demás salió de la ingesta de DOCS_PATH (la base original).
PREFIJO_SUBIDOS = "uploads/"


def listar_documentos_base(fuente: str | None = None) -> list[dict]:
    """Archivos de la base original con su título, tipo, juegos y nº de fragmentos.

    Con `fuente` devuelve solo ese archivo (lista vacía si no es de la base).
    A diferencia de las otras consultas, los errores se propagan: la API los
    convierte en un 503.
    """
    sentencia = text(
        """
        SELECT e.cmetadata->>'fuente' AS fuente,
               min(e.cmetadata->>'title') AS title,
               min(e.cmetadata->>'tipo') AS tipo,
               count(DISTINCT e.id) AS chunks,
               array_remove(array_agg(DISTINCT j.juego ORDER BY j.juego), NULL) AS juegos
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
        LEFT JOIN LATERAL jsonb_array_elements_text(
            CASE WHEN jsonb_typeof(e.cmetadata->'juegos') = 'array'
                 THEN e.cmetadata->'juegos' ELSE '[]'::jsonb END
        ) AS j(juego) ON true
        WHERE c.name = :coleccion
          AND e.cmetadata->>'fuente' IS NOT NULL
          AND e.cmetadata->>'fuente' NOT LIKE :subidos
          AND (CAST(:fuente AS TEXT) IS NULL OR e.cmetadata->>'fuente' = :fuente)
        GROUP BY 1
        ORDER BY lower(min(e.cmetadata->>'title')), 1
        """
    )
    with _get_motor().connect() as conexion:
        filas = conexion.execute(
            sentencia,
            {"coleccion": config.PG_COLLECTION, "subidos": f"{PREFIJO_SUBIDOS}%", "fuente": fuente},
        )
        return [dict(fila._mapping) for fila in filas]


def textos_fragmentos() -> list[str]:
    """Texto de todos los fragmentos de la colección (para sacar sus nombres propios)."""
    sentencia = text(
        """
        SELECT e.document
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
        WHERE c.name = :coleccion
        """
    )
    try:
        with _get_motor().connect() as conexion:
            return [fila.document for fila in conexion.execute(sentencia, {"coleccion": config.PG_COLLECTION})]
    except Exception:  # noqa: BLE001
        return []


def listar_titulos() -> list[str]:
    """Títulos distintos de los documentos indexados (las páginas de la wiki)."""
    sentencia = text(
        """
        SELECT DISTINCT e.cmetadata->>'title' AS titulo
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
        WHERE c.name = :coleccion
          AND e.cmetadata->>'tipo' = 'wiki'
          AND e.cmetadata->>'title' IS NOT NULL
        """
    )
    try:
        with _get_motor().connect() as conexion:
            filas = conexion.execute(sentencia, {"coleccion": config.PG_COLLECTION})
            return [fila.titulo for fila in filas]
    except Exception:  # noqa: BLE001
        return []
