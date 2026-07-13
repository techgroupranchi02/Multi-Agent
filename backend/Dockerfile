# Use official lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

# Set work directory
WORKDIR /app

# Install system dependencies (including git for GitPython)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml
COPY pyproject.toml .

# Install dependencies (installing package itself in editable mode or standard)
# First install the project dependencies to utilize layer caching
RUN pip install --no-cache-dir .

# Copy backend code
COPY src/ ./src/
COPY prompts/ ./prompts/

# Copy Google credential files conditionally (won't fail if they don't exist since pyproject.toml is guaranteed to exist)
COPY pyproject.toml google_oauth_client.json* google_oauth_token.json* google_service_account.json* ./


# Create directory structure for runner/workspace
RUN mkdir -p workspace

# Expose FastAPI port
EXPOSE 8000

# Command to run
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
