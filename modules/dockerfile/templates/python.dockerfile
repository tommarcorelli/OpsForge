# syntax=docker/dockerfile:1
# ============================================================
# OpsForge — Dockerfile Python (multi-stage : build + runtime allege)
# ============================================================

# ---- Stage 1 : build (installe les dependances) ----
FROM python:{version}-slim AS build
WORKDIR {workdir}
COPY requirements.txt* pyproject.toml* poetry.lock* Pipfile* Pipfile.lock* ./
RUN {install_cmd}
COPY . .

# ---- Stage 2 : runtime (image finale, sans outils de build) ----
FROM python:{version}-slim
WORKDIR {workdir}
RUN addgroup --system app && adduser --system --ingroup app app
COPY --from=build /usr/local /usr/local
COPY --from=build {workdir} {workdir}
RUN chown -R app:app {workdir}
USER app
EXPOSE {port}
CMD ["python", "{entrypoint}"]
