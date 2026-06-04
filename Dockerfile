FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
    python3-dev \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN pip install uv

# Copy project files
COPY . /app

# Install dependencies and project in editable mode
RUN uv pip install --system -e .

# Expose port 8000 for the FastAPI OpenAI-compatible API
EXPOSE 8000

# Run Uvicorn server
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]