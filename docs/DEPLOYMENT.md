# Despliegue: frontend en Netlify, backend en AWS EC2

URLs actuales:

| Servicio | URL |
|---|---|
| Frontend (Netlify) | https://johndarksoul.netlify.app |
| API (Swagger) | https://api.13-58-191-152.sslip.io/docs |
| Keycloak | https://auth.13-58-191-152.sslip.io |

```
Navegador ──HTTPS──► Netlify (frontend React, archivos estáticos)
    │
    ├──HTTPS──► EC2 (Elastic IP 13.58.191.152) ── Caddy :443
    │                 ├── api.13-58-191-152.sslip.io  → backend (FastAPI + LangGraph)
    │                 └── auth.13-58-191-152.sslip.io → Keycloak
    │               red interna de Docker: backend → Ollama (CPU), Postgres + pgvector
```

- **HTTPS es obligatorio.** Netlify sirve en HTTPS y el navegador bloquea las
  llamadas a un backend HTTP (contenido mixto). Además `keycloak-js` necesita
  HTTPS para PKCE. Caddy saca los certificados de Let's Encrypt solo.
- **No hace falta comprar dominio.** [sslip.io](https://sslip.io) resuelve
  `api.1-2-3-4.sslip.io` a la IP `1.2.3.4`.
- Solo Caddy (80/443) queda expuesto a internet. Postgres, Ollama, Keycloak y el
  backend solo se ven dentro de la red de Docker.

Archivos de producción:

| Archivo | Para qué |
|---|---|
| `netlify.toml` | Build del frontend (`frontend/`, `npm run build`, `dist`) y redirección de la SPA a `index.html` |
| `docker-compose.prod.yml` | Se aplica encima de `docker-compose.yml`: agrega Caddy, quita los puertos públicos, Ollama sin GPU, Keycloak en modo producción detrás del proxy guardando en Postgres (esquema `keycloak`, lo crea la tarea `keycloak-schema`) y no levanta el contenedor del frontend |
| `deploy/Caddyfile` | Proxy inverso y HTTPS para `api.` y `auth.` |
| `deploy/.env.production.example` | Plantilla del `.env` del servidor |
| `deploy/configurar_keycloak.sh` | Agrega la URL de Netlify al cliente `frontend` del realm |

El backend no lee `KEYCLOAK_URL` ni `CORS_ORIGINS` del `.env` en producción: el
compose las deriva de `AUTH_DOMAIN` y `FRONTEND_URL`, así no se desincronizan.

---

## 1. Netlify: crear el sitio

1. **Add new site → Import an existing project → GitHub** → `Chuluet/john-dark-soul`.
2. Configuración del build (`netlify.toml` ya la define; si la interfaz la pide):

   | Campo | Valor |
   |---|---|
   | Branch to deploy | `main` |
   | Base directory | `frontend` |
   | Build command | `npm run build` |
   | Publish directory | `frontend/dist` (o `dist` si la interfaz ya muestra `frontend/` delante) |
   | Functions directory | vacío |

3. Variables que no dependen de la EC2 (**Site configuration → Environment variables**):
   `VITE_KEYCLOAK_REALM=john-dark-soul`, `VITE_KEYCLOAK_CLIENT_ID=frontend`,
   `VITE_USE_MOCKS=false`. Las dos URLs se ponen en el paso 4.
4. **Site configuration → Change site name** y anotar la URL (aquí,
   `https://johndarksoul.netlify.app`): va en `FRONTEND_URL` del servidor.

## 2. AWS: crear la EC2

1. **EC2 → Launch instances**
   - AMI: **Ubuntu Server 24.04 LTS** (64-bit x86).
   - Tipo: se usó **`m7i-flex.large`** (2 vCPU, 8 GB), la más grande del plan
     gratuito. Alcanza para todo el stack con `qwen2.5:7b` en CPU, pero las
     respuestas tardan (ver "Limitaciones"). Con plan de pago, `t3.xlarge`
     (16 GB) da más margen de memoria.
   - Key pair: crear uno (`.pem`) y guardarlo; sin él no se entra al servidor.
   - Disco: **30–50 GB gp3**. Lo ocupado: imagen de Ollama 9,4 GB, backend 1,1 GB,
     Keycloak + Postgres + Caddy 1,4 GB, modelos 5,9 GB (+3 GB si se baja el de
     visión), caché de build y Ubuntu.
   - Security group, reglas de entrada:
     - SSH 22 → **My IP**
     - HTTP 80 → **0.0.0.0/0** (Let's Encrypt valida por aquí)
     - HTTPS 443 → **0.0.0.0/0**
2. **Elastic IPs → Allocate → Associate** a la instancia. Así la IP no cambia al
   apagarla y encenderla, y los dominios de sslip.io siguen sirviendo.
3. Conectarse:
   ```powershell
   ssh -i john-dark-soul.pem ubuntu@13.58.191.152
   ```
   Si Windows se queja de los permisos del `.pem`:
   `icacls john-dark-soul.pem /inheritance:r /grant:r "$($env:USERNAME):R"`

> **Costos:** apagar la instancia (**Stop**, nunca *Terminate*) cuando no se use.
> Conviene una alerta en **Billing → Budgets**. AWS cobra un poco por la Elastic IP
> mientras la instancia está apagada.

## 3. EC2: levantar el backend

```bash
# Sistema al día (si pide reinicio: sudo reboot y volver a entrar)
sudo apt update && sudo apt upgrade -y

# Docker + Compose (Compose >= 2.24: el compose de producción usa !reset/!override)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && newgrp docker

# Código
git clone https://github.com/Chuluet/john-dark-soul.git
cd john-dark-soul

# Variables
cp deploy/.env.production.example .env
nano .env
```

En el `.env`: la Elastic IP **con guiones** en `API_DOMAIN` y `AUTH_DOMAIN`
(`13.58.191.152` → `api.13-58-191-152.sslip.io`), la URL de Netlify en
`FRONTEND_URL` (sin `/` final) y las contraseñas (`POSTGRES_PASSWORD`,
`KEYCLOAK_ADMIN_PASSWORD` y la de `DATABASE_URL`).

Levantar todo (la primera vez tarda: compila el backend y descarga imágenes):

```bash
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
$COMPOSE up -d --build
```

`db-seed` restaura `backend/data/embeddings.dump` (4196 fragmentos) si la base
vectorial está vacía, así que **no hay que hacer la ingesta en el servidor**.

Modelos de Ollama (una sola vez, quedan en un volumen):

```bash
$COMPOSE exec ollama ollama pull qwen2.5:7b     # el de LLM_MODEL
$COMPOSE exec ollama ollama pull bge-m3         # embeddings: el mismo que generó el dump
$COMPOSE exec ollama ollama pull qwen2.5vl:3b   # solo si se van a subir imágenes
```

Dar de alta la URL de Netlify en Keycloak (redirección del login y del logout,
y origen permitido). Se puede repetir si cambia la URL:

```bash
sh deploy/configurar_keycloak.sh
```

> **Usuario de prueba:** el realm trae `demo` / `demo`. En un servidor público
> conviene cambiarle la contraseña o borrarlo desde la consola de Keycloak
> (`https://auth.13-58-191-152.sslip.io/admin`, realm `john-dark-soul` → Users).

Comprobar:

```bash
$COMPOSE ps                                   # todo "Up"; db-seed y keycloak-schema "Exited (0)"
$COMPOSE logs db-seed                         # "fragmentos restaurados"
$COMPOSE logs caddy | grep -i "certificate obtained"
curl -I https://api.13-58-191-152.sslip.io/docs     # 200
curl -s https://api.13-58-191-152.sslip.io/me       # 401 {"detail":"Missing access token."}
```

## 4. Netlify: conectar el frontend

| Variable | Valor |
|---|---|
| `VITE_API_URL` | `https://api.13-58-191-152.sslip.io` |
| `VITE_KEYCLOAK_URL` | `https://auth.13-58-191-152.sslip.io` |
| `VITE_KEYCLOAK_REALM` | `john-dark-soul` |
| `VITE_KEYCLOAK_CLIENT_ID` | `frontend` |
| `VITE_USE_MOCKS` | `false` |

Luego **Deploys → Trigger deploy → Clear cache and deploy site**. Vite fija las
`VITE_*` al compilar: cada vez que cambien hay que volver a desplegar.

## 5. Probar el flujo de la sustentación

En https://johndarksoul.netlify.app:

1. Registrarse o iniciar sesión.
2. Pregunta con respuesta: "Who is Artorias?" (debe mostrar fuentes).
3. Pregunta fuera del tema: "What is the best sushi recipe?" → rechazo.
4. Subir un documento pequeño y hacer una pregunta que dependa de él.
5. Historial, documentos, cerrar sesión.

## Actualizar después de un cambio

```bash
cd ~/john-dark-soul && git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

El frontend se redespliega solo en Netlify con cada push a `main`.

## Limitaciones

- **Velocidad del modelo.** La `m7i-flex.large` no tiene GPU: `qwen2.5:7b` en CPU
  tarda del orden de minutos por respuesta (en local, con GPU, son segundos).
  El frontend espera sin límite de tiempo y Caddy no corta la petición.
- **No usar `qwen2.5:3b` para ahorrar tiempo.** En las pruebas, el nodo
  `evaluate_context` rechazaba con él todas las preguntas, incluso con
  fragmentos de puntaje alto.
- **Memoria justa.** 8 GB para el modelo de 7b, Keycloak, Postgres y el backend.
  Si Ollama se reinicia por falta de memoria, cerrar lo que no se use o pasar a
  una instancia de 16 GB.

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| El navegador da *timed out* en `api.` o `auth.` | IP mal escrita en el `.env` o en Netlify (sslip.io resuelve **exactamente** lo escrito: un dígito distinto apunta a otro servidor), o puertos 80/443 cerrados en el security group |
| Caddy: `Timeout during connect (likely firewall problem)` | Lo mismo: Let's Encrypt no llega al servidor. Revisar la IP del `.env` y el security group, luego `$COMPOSE restart caddy` |
| Keycloak: "Invalid redirect uri" al iniciar sesión | Falta `sh deploy/configurar_keycloak.sh`, o `FRONTEND_URL` no es exactamente la URL de Netlify |
| El frontend dice "Could not connect to the server" | `VITE_API_URL` mal escrita o sin redesplegar Netlify |
| Error de CORS en la consola del navegador | `FRONTEND_URL` del `.env` no es exactamente la URL de Netlify (sin `/` al final). Tras cambiarla: `up -d` y `sh deploy/configurar_keycloak.sh` |
| La API responde 401 "Invalid token." con sesión iniciada | El `iss` del token no coincide con `https://$AUTH_DOMAIN`: revisar `AUTH_DOMAIN` y recrear `keycloak` y `backend` con `up -d` |
| Keycloak no arranca: `schema "keycloak" does not exist` | `keycloak-schema` no terminó bien: `$COMPOSE logs keycloak-schema` |
| El agente responde 503 | Falta `ollama pull` del modelo de `LLM_MODEL` o de `bge-m3`. Ver `$COMPOSE logs backend` |
| Ollama se reinicia / "out of memory" | Poca RAM para el modelo (ver "Limitaciones") |
| Recargar `/chat` en Netlify da 404 | Falta `netlify.toml` en la raíz del repo |
| No se puede elegir `t3.xlarge` | La cuenta está en el plan gratuito: solo permite instancias *free tier eligible* |
