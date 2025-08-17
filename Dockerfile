# Single-stage Dockerfile for KCO Operator
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_HOME="/opt/poetry" \
    POETRY_CACHE_DIR=/opt/poetry/cache \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_NO_INTERACTION=1
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="$POETRY_HOME/bin:$PATH"

# Create non-root user
RUN groupadd -g 1000 kco && \
    useradd -r -u 1000 -g kco -s /bin/bash -d /app kco

# Set work directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install dependencies only (no dev dependencies)
RUN poetry install --only=main --no-root

# Copy application code
COPY kco_operator/ ./kco_operator/
RUN chown -R kco:kco /app

# Switch to non-root user
USER kco

# Expose ports for metrics and health checks
EXPOSE 8080 8081

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8081/healthz || exit 1

# Set environment variables
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Run the operator using poetry
CMD ["poetry", "run", "python", "-m", "kco_operator.main"]