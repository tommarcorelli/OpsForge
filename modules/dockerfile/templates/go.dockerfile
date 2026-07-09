# syntax=docker/dockerfile:1
# ============================================================
# OpsForge — Dockerfile Go (multi-stage : build + runtime minimal)
# ============================================================

# ---- Stage 1 : build (binaire statique) ----
FROM golang:{version}-alpine AS build
WORKDIR {workdir}
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/{entrypoint} .

# ---- Stage 2 : runtime (image minimale, juste le binaire) ----
FROM alpine:3.20
WORKDIR {workdir}
RUN apk add --no-cache ca-certificates \
 && addgroup -S app && adduser -S -G app app
COPY --from=build /out/{entrypoint} ./{entrypoint}
USER app
EXPOSE {port}
CMD ["./{entrypoint}"]
