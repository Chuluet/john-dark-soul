# syntax=docker/dockerfile:1

# Etapa 1: compilar la app. Las VITE_* se fijan en tiempo de build.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=http://localhost:8000
ARG VITE_KEYCLOAK_URL=http://localhost:8080
ARG VITE_KEYCLOAK_REALM=john-dark-soul
ARG VITE_KEYCLOAK_CLIENT_ID=frontend
ARG VITE_USE_MOCKS=false
RUN npm run build

# Etapa 2: servir los archivos estáticos con nginx.
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
