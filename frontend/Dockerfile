# Multi-stage build for the Vite + React frontend.
# Stage 1: builder - install deps and build the production bundle.
# Stage 2: runtime - nginx serving the static bundle + proxying /api to backend.

# ── Stage 1: builder ──────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps separately to leverage Docker layer cache.
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY . .

# Build-time API base. With nginx proxying /api -> backend, an empty
# string tells axios to use the relative path (resolved by nginx).
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ── Stage 2: runtime (nginx) ─────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Drop the default config; ship our own.
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/app.conf

# Static assets from Vite's `dist/` directory.
COPY --from=builder /app/dist /usr/share/nginx/html

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
