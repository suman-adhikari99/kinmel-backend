FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Minimal OS deps (curl useful for healthchecks/debug)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Run as non-root (production best practice)
RUN useradd -m appuser \
  && mkdir -p /app/uploads/reports /app/uploads/avatars \
  && chown -R appuser:appuser /app/uploads
USER appuser

EXPOSE 8000

# Entrypoint lives under /app/src, so use the package-qualified path.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
