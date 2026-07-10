# syntax=docker/dockerfile:1
# ============================================================
# OpsForge — Dockerfile Node.js (multi-stage : build + runtime allege)
# ============================================================

# ---- Stage 1 : build (installe les dependances) ----
FROM node:{version}-alpine AS build
WORKDIR {workdir}
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./
RUN {install_cmd}
COPY . .
# Decommente si ton projet a un script de build (React, Vue, TS...) :
# RUN npm run build

# ---- Stage 2 : runtime (image finale) ----
FROM node:{version}-alpine
WORKDIR {workdir}
ENV NODE_ENV=production
RUN addgroup -S app && adduser -S -G app app
COPY --from=build {workdir} {workdir}
RUN chown -R app:app {workdir}
USER app
EXPOSE {port}
CMD ["node", "{entrypoint}"]
