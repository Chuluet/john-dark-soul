#!/bin/sh
# Llena la base vectorial con backend/data/embeddings.dump si está vacía.
#
# Lo ejecuta el servicio `db-seed` de docker-compose.yml en cada
# `docker compose up -d`, antes de arrancar el backend. Si la colección ya tiene
# fragmentos (ingesta previa o documentos subidos desde la web) no toca nada.
set -eu

DUMP=/seed/embeddings.dump

# Dos consultas: Postgres valida las tablas al planificar, así que un count(*)
# sobre una tabla que no existe falla aunque vaya dentro de un CASE.
fragmentos=0
if [ "$(psql -tAc "SELECT to_regclass('public.langchain_pg_embedding') IS NOT NULL")" = "t" ]; then
  fragmentos=$(psql -tAc "SELECT count(*) FROM langchain_pg_embedding")
fi

if [ "$fragmentos" -gt 0 ]; then
  echo "La base vectorial ya tiene $fragmentos fragmentos: no se restaura."
  exit 0
fi

if [ ! -f "$DUMP" ]; then
  echo "No existe $DUMP: la base queda vacía (usa la ingesta para llenarla)."
  exit 0
fi

echo "Base vectorial vacía: restaurando $DUMP..."
psql -c "CREATE EXTENSION IF NOT EXISTS vector"
pg_restore --no-owner --clean --if-exists -d "$PGDATABASE" "$DUMP"
echo "Listo: $(psql -tAc 'SELECT count(*) FROM langchain_pg_embedding') fragmentos restaurados."
