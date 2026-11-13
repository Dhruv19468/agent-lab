# =============================================================================
# Build: install packages and produce the static site in /app/dist
# =============================================================================
FROM node:22-alpine AS build

WORKDIR /app

# Packages first, so this layer is reused until package.json / package-lock.json change.
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .
RUN npm run build

# =============================================================================
# Runtime: nginx serves the static files and forwards /api to the backend
# =============================================================================
FROM nginx:1.27-alpine

# openssl hashes the optional site password at start-up (nginx/40-basic-auth.sh)
RUN apk add --no-cache openssl

# The image turns templates/*.template into conf.d/* at start, filling in ${BACKEND_URL}.
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --chmod=755 nginx/40-basic-auth.sh /docker-entrypoint.d/40-basic-auth.sh
COPY --from=build /app/dist /usr/share/nginx/html

ENV BACKEND_URL=http://backend:8080

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/healthz || exit 1
