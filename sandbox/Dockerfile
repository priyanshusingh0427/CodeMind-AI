# Isolated test-execution image for CodeMind AI.
# Build:  docker build -t codemind-sandbox:latest sandbox/
# The application runs containers from this image with: no network, non-root
# user, read-only root filesystem, CPU/memory/PID limits, a small tmpfs and a
# hard timeout. Nothing from the host is mounted except a temporary, read-only
# directory that holds the code under test.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir "pytest>=8,<10" \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin sandbox

USER 10001
WORKDIR /work
CMD ["python", "/work/runner.py"]
