FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir mcp pydantic pydantic-settings httpx python-dotenv structlog tenacity anyio "pydantic[email]"

# Copy source code
COPY src/ ./src/

# Copy env example as default (override with real .env in production)
COPY .env.example .env

EXPOSE 8000

CMD ["python", "src/server.py"]
