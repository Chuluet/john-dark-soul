# Datos de ingesta

`wiki/` contiene los artículos de la wiki de Dark Souls que el agente puede
consultar. Puedes añadir más archivos o subcarpetas: la ingesta recorre
`DOCS_PATH` (por defecto `data/wiki`) recursivamente.

**Formatos soportados:** `.md`, `.txt`, `.pdf`

Los `.md` pueden llevar un frontmatter que se guarda como metadata de cada
fragmento:

```markdown
---
title: Abyss
juego: DS1
categoria: Dark Souls: Locations
fuente: https://darksouls.fandom.com/wiki/Abyss
---
```

## Indexar

Desde `backend/`:

```bash
uv run python -m services.ingest_service
uv run python -m services.ingest_service --reset   # reconstruye desde cero
```

Con Docker:

```bash
docker compose run --rm backend python -m services.ingest_service
```

## Notas

- La reingesta es idempotente: volver a ejecutarla no duplica fragmentos,
  reemplaza los del archivo que cambió.
- Los PDF escaneados (imágenes sin capa de texto) no producen texto
  extraíble.
- Este README está fuera de `wiki/` a propósito, para que no se indexe.
