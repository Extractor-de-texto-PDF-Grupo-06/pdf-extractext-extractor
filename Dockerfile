# syntax=docker/dockerfile:1

# Etapa de construcción: uv instala exactamente las versiones de uv.lock (12-Factor II).
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Imagen final: solo el entorno virtual y el código, sin uv ni herramientas de construcción.
FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY extractor_service ./extractor_service
# La imagen oficial de Python no trae el bytecode de la biblioteca estándar, y el usuario
# sin privilegios no puede escribirlo: sin esto, cada proceso nuevo (los del pool y el del
# healthcheck, cada 5 s) recompila todo y le quita CPU a la extracción.
RUN python -m compileall -q -j 0 /usr/local/lib/python3.12 /app/extractor_service
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=5 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ['PORT']}/health\", timeout=2)"]
# exec deja a uvicorn como PID 1, así recibe el SIGTERM de `docker stop` y cierra en orden.
# Las demás opciones de uvicorn se pasan con variables UVICORN_* (por ejemplo
# UVICORN_TIMEOUT_KEEP_ALIVE), que su línea de comandos lee sola.
CMD ["sh", "-c", "exec uvicorn extractor_service.main:app --host 0.0.0.0 --port \"$PORT\""]
