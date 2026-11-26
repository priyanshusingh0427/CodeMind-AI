# Optional container for the CodeMind AI web app itself.
# Build:  docker build -t codemind-ai .
# Run:    docker run -p 8501:8501 -e OLLAMA_HOST=http://host.docker.internal:11434 codemind-ai
#
# Note: inside this container the Docker sandbox is not available (no Docker-in-Docker),
# so the app runs in static-analysis + LLM mode. For sandboxed test execution run the
# app directly on your machine (see README). The sandbox image is in sandbox/Dockerfile.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SANDBOX_ENABLED=false

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home codemind

COPY --chown=codemind:codemind . .
USER codemind
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
