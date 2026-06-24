# ---------- builder ----------
FROM python:3.13-slim AS builder

WORKDIR /build

# Install pinned, hash-verified dependencies first (reproducible builds), then
# the application package itself without re-resolving its dependency tree.
COPY requirements.lock ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --require-hashes -r requirements.lock

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps .

# ---------- runtime ----------
FROM python:3.13-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src/ .

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
