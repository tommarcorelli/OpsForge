# syntax=docker/dockerfile:1
# ============================================================
# OpsForge — Dockerfile .NET (multi-stage : build + runtime ASP.NET)
# ============================================================

# ---- Stage 1 : build (SDK complet) ----
FROM mcr.microsoft.com/dotnet/sdk:{version} AS build
WORKDIR {workdir}
COPY . .
RUN dotnet restore
RUN dotnet publish -c Release -o /out

# ---- Stage 2 : runtime (ASP.NET seul, sans le SDK) ----
FROM mcr.microsoft.com/dotnet/aspnet:{version}
WORKDIR {workdir}
RUN addgroup --system app && adduser --system --ingroup app app
COPY --from=build /out .
RUN chown -R app:app {workdir}
USER app
EXPOSE {port}
# NOTE : remplace {entrypoint} par le nom de ta DLL principale
# (ex: MonProjet.dll), genere par `dotnet publish`.
ENTRYPOINT ["dotnet", "{entrypoint}"]
