# syntax=docker/dockerfile:1
# ============================================================
# OpsForge — Dockerfile Ruby (multi-stage : build + runtime allege)
# ============================================================

# ---- Stage 1 : build (installe les gems) ----
FROM ruby:{version}-slim AS build
WORKDIR {workdir}
RUN apt-get update -qq \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*
COPY Gemfile Gemfile.lock* ./
RUN {install_cmd}
COPY . .

# ---- Stage 2 : runtime (sans outils de compilation) ----
FROM ruby:{version}-slim
WORKDIR {workdir}
RUN addgroup --system app && adduser --system --ingroup app app
COPY --from=build /usr/local/bundle /usr/local/bundle
COPY --from=build {workdir} {workdir}
RUN chown -R app:app {workdir}
USER app
EXPOSE {port}
CMD ["ruby", "{entrypoint}"]
