# syntax=docker/dockerfile:1
# ============================================================
# OpsForge — Dockerfile Java / Gradle (multi-stage : build + runtime JRE)
# ============================================================

# ---- Stage 1 : build (Gradle wrapper) ----
FROM gradle:8-jdk{version} AS build
WORKDIR {workdir}
COPY build.gradle* settings.gradle* gradle.properties* ./
COPY gradle ./gradle
COPY gradlew ./
RUN chmod +x gradlew
COPY src ./src
RUN ./gradlew build -x test --no-daemon

# ---- Stage 2 : runtime (JRE seul, pas le JDK/Gradle) ----
FROM eclipse-temurin:{version}-jre
WORKDIR {workdir}
RUN addgroup --system app && adduser --system --ingroup app app
COPY --from=build {workdir}/build/libs/*.jar app.jar
USER app
EXPOSE {port}
ENTRYPOINT ["java", "-jar", "app.jar"]
