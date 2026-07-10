# syntax=docker/dockerfile:1
# ============================================================
# OpsForge — Dockerfile Rust (multi-stage : build + runtime minimal)
# ============================================================

# ---- Stage 1 : build (compilation en mode release) ----
FROM rust:{version}-slim AS build
WORKDIR {workdir}
COPY Cargo.toml Cargo.lock* ./
# Cache les dependances avant de copier le vrai code source.
RUN mkdir src && echo "fn main() {}" > src/main.rs \
 && cargo build --release \
 && rm -rf src
COPY . .
RUN touch src/main.rs && cargo build --release

# ---- Stage 2 : runtime (image minimale, juste le binaire) ----
FROM debian:bookworm-slim
WORKDIR {workdir}
RUN apt-get update -qq \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && addgroup --system app && adduser --system --ingroup app app
# NOTE : remplace {entrypoint} par le nom du binaire compile
# (champ [package].name dans ton Cargo.toml).
COPY --from=build {workdir}/target/release/{entrypoint} ./{entrypoint}
USER app
EXPOSE {port}
CMD ["./{entrypoint}"]
