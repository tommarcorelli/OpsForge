# syntax=docker/dockerfile:1
# ============================================================
# OpsForge — Dockerfile Java / Maven (multi-stage : build + runtime JRE)
# ============================================================

# ---- Stage 1 : build (Maven) ----
FROM maven:3.9-eclipse-temurin-{version} AS build
WORKDIR {workdir}
COPY pom.xml .
RUN mvn -B dependency:go-offline
COPY src ./src
RUN mvn -B package -DskipTests

# ---- Stage 2 : runtime (JRE seul, pas le JDK/Maven) ----
FROM eclipse-temurin:{version}-jre
WORKDIR {workdir}
RUN addgroup --system app && adduser --system --ingroup app app
COPY --from=build {workdir}/target/*.jar app.jar
USER app
EXPOSE {port}
ENTRYPOINT ["java", "-jar", "app.jar"]
