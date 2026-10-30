# API de la web + pipeline (Fase 3). Contexto de build: la raíz del repositorio (la API usa src/folio).
# Railway: servicio «api», Dockerfile «api/Dockerfile», volumen montado en /datos, sin dominio público.
FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    FOLIO_DATOS=/datos
WORKDIR /app

# Dependencias (capa que se reutiliza mientras no cambie uv.lock)
COPY pyproject.toml uv.lock ./
COPY api/pyproject.toml api/pyproject.toml
RUN uv sync --frozen --no-dev --all-packages --no-install-workspace

# Chromium para el render y la exportación a PNG; ffmpeg para la portada en vídeo (folio render --video)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && uv run --no-sync playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*

# Código, configuración, prompts y diseño (los datos van al volumen /datos, no a la imagen)
COPY src src
COPY api api
COPY config config
COPY prompts prompts
COPY diseno diseno
RUN uv sync --frozen --no-dev --all-packages

EXPOSE 8000
# «::» para que la web la alcance por la red privada de Railway (IPv6)
CMD ["sh", "-c", "uv run --no-sync folio web --host :: --puerto ${PORT:-8000}"]
