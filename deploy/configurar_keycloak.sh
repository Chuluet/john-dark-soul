#!/bin/sh
# Agrega la URL de Netlify (FRONTEND_URL del .env) al cliente `frontend` del
# realm: redirección del login, del logout y origen permitido (CORS de Keycloak).
#
# Se corre en la EC2, desde la raíz del repo, con Keycloak ya arriba:
#   sh deploy/configurar_keycloak.sh
#
# Se puede repetir sin problema (por ejemplo, si cambia la URL de Netlify):
# deja localhost:5173 para desarrollo y reemplaza la URL de producción.
set -eu

if [ ! -f .env ]; then
  echo "No hay .env en $(pwd): córrelo desde la raíz del repo." >&2
  exit 1
fi
set -a; . ./.env; set +a

: "${FRONTEND_URL:?Falta FRONTEND_URL en el .env}"
: "${KEYCLOAK_ADMIN:?Falta KEYCLOAK_ADMIN en el .env}"
: "${KEYCLOAK_ADMIN_PASSWORD:?Falta KEYCLOAK_ADMIN_PASSWORD en el .env}"
REALM="${KEYCLOAK_REALM:-john-dark-soul}"
CLIENTE="${KEYCLOAK_CLIENT_ID:-frontend}"
FRONTEND_URL="${FRONTEND_URL%/}"   # sin "/" final
LOCAL=http://localhost:5173

kcadm() {
  docker exec -i darksoul-keycloak /opt/keycloak/bin/kcadm.sh "$@"
}

echo "Esperando a Keycloak..."
intentos=0
until kcadm config credentials --server http://localhost:8080 --realm master \
    --user "$KEYCLOAK_ADMIN" --password "$KEYCLOAK_ADMIN_PASSWORD" >/dev/null 2>&1; do
  intentos=$((intentos + 1))
  if [ "$intentos" -ge 30 ]; then
    echo "Keycloak no responde o el usuario admin del .env no es válido." >&2
    exit 1
  fi
  sleep 5
done

id=$(kcadm get clients -r "$REALM" -q "clientId=$CLIENTE" --fields id --format csv --noquotes | tr -d '\r')
if [ -z "$id" ]; then
  echo "No existe el cliente '$CLIENTE' en el realm '$REALM'." >&2
  exit 1
fi

kcadm update "clients/$id" -r "$REALM" \
  -s "redirectUris=[\"$LOCAL/*\",\"$FRONTEND_URL/*\"]" \
  -s "webOrigins=[\"$LOCAL\",\"$FRONTEND_URL\"]" \
  -s "attributes.\"post.logout.redirect.uris\"=$LOCAL/*##$FRONTEND_URL/*"

echo "Cliente '$CLIENTE' actualizado:"
kcadm get "clients/$id" -r "$REALM" --fields redirectUris,webOrigins
# --fields no muestra los atributos anidados: se filtran del cliente completo.
kcadm get "clients/$id" -r "$REALM" | grep -E '"(post\.logout\.redirect\.uris|pkce\.code\.challenge\.method)"'
