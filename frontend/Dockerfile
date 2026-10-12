# Front en production sur Railway (DEPLOYMENT.md). Alternative : Vercel,
# configuré par vercel.json (mêmes en-têtes).
#
# Étape 1 : build Vite. VITE_API_BASE_URL est figée DANS le bundle au build
# (variable publique, jamais un secret) : sur Railway, déclarez-la dans les
# variables du service, elle est transmise ici comme argument de build.
FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# Étape 2 : serveur statique minimal (Caddy), sans Node à l'exécution.
FROM caddy:2.8-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
EXPOSE 8080
