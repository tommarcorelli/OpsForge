# syntax=docker/dockerfile:1
# ============================================================
# OpsForge — Dockerfile PHP / Apache (deps Composer + runtime Apache)
# ============================================================

# ---- Stage 1 : dependances (Composer) ----
FROM composer:2 AS deps
WORKDIR {workdir}
COPY composer.json composer.lock* ./
RUN composer install --no-dev --no-interaction --no-scripts --optimize-autoloader || true

# ---- Stage 2 : runtime (Apache + PHP) ----
FROM php:{version}-apache
# NOTE : le docroot d'Apache est fixe (/var/www/html), independant de {workdir}.
WORKDIR /var/www/html
RUN a2enmod rewrite
COPY --from=deps {workdir}/vendor ./vendor
COPY . .
EXPOSE 80
