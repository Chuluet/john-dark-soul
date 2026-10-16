# Datos de ingesta

`wiki/` contiene lo que el agente puede consultar. Puedes añadir más archivos o
subcarpetas: la ingesta recorre `DOCS_PATH` (por defecto `data/wiki`)
recursivamente.

**Formatos soportados:** `.md`, `.txt`, `.pdf`, `.jpg`, `.jpeg`, `.png`, `.mp4`, `.mp3`

Cada formato se embebe directamente (sin archivos intermedios) y todos los
fragmentos salen con los mismos metadatos y una cabecera
`Título (juego) > Sección` al principio del texto:

| Formato | Cómo se lee | Sección |
|---|---|---|
| `.md` de la wiki | texto + frontmatter | el título `##` |
| `.pdf` | una página = un documento | `Página N` |
| imagen | el modelo de visión transcribe el texto (o describe la imagen si no tiene) | los títulos de la imagen |
| video / audio | Whisper, en bloques de 90 s | `mm:ss - mm:ss` |

## A qué juego pertenece cada archivo

- `.md` de la wiki: el `juego` del frontmatter.
- Cualquier otro archivo: el sufijo del nombre, igual que la wiki:
  `mi-documento__DS2.pdf`. Sin sufijo (o `__general`) el juego queda como
  `general` y se deduce **fragmento a fragmento** por los nombres que menciona
  (Lothric → DS3, Vendrick → DS2…). Así un video que habla de los tres juegos
  queda bien etiquetado por partes.

## Wiki (`.md`)

Los genera `firekeeper/ingest_wiki.py` ya limpios (sin imágenes, categorías,
enlaces a otros idiomas, secciones sin lore ni párrafos repetidos):

```bash
cd firekeeper
uv run python ingest_wiki.py --out ../john-dark-soul/backend/data/wiki
```

Ojo: borra los `.md` de la carpeta de salida antes de escribir (no toca
imágenes, PDF ni videos).

Frontmatter de cada `.md`:

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

- Sin `--reset`, los archivos que no cambiaron (mismo tamaño y fecha) se saltan:
  el video no se vuelve a transcribir. Si cambias cómo se fragmenta o cómo se
  carga un formato, usa `--reset`.
- Los archivos de texto se procesan primero y los que pasan por un modelo
  (imágenes, video) al final.
- Whisper usa la GPU si hay una (`WHISPER_DEVICE=auto`): 3 h de video tardan
  ~4 min en una RTX 4070 contra ~50 min en CPU. Necesita las librerías de CUDA,
  que se instalan con `uv sync --extra gpu` (un `uv sync` sin `--extra gpu`
  las desinstala). Si la GPU falla, la ingesta sigue en CPU y lo avisa.
- Los PDF escaneados (imágenes sin capa de texto) no producen texto
  extraíble.
- Este README está fuera de `wiki/` a propósito, para que no se indexe.
