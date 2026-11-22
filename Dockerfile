# syntax=docker/dockerfile:1
# Twelve-Factor V (build, release, run): a separate BUILD stage compiles wheels,
# the RUN stage only installs them - no compilers or caches in the final image.
# The image is the "build"; the "release" is image + env vars (compose/k8s).

# ---------- build stage -----------------------------------------------------
FROM python:3.12-slim AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# ---------- run stage -------------------------------------------------------
FROM python:3.12-slim AS run
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
    PORT=8000 DATA_DIR=/app/data
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels
COPY app ./app
COPY scripts ./scripts
COPY data ./data
USER app
EXPOSE 8000
# Liveness only (no dependency calls) so a slow Neo4j doesn't kill the pod.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=2)"
# Port comes from $PORT (Factor VII). Same image runs the worker:
#   command: ["python", "-m", "app.worker"]
CMD ["python", "-m", "app"]
