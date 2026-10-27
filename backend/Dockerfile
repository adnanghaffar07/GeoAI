# Backend image, used by both the API and the Celery worker.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System libraries for PDF reports (WeasyPrint) and a font for the PDF text.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# PyTorch for the AI model, CPU-only build (much smaller than the GPU build; the app server has no GPU).
# Same version that trained the model. Its own layer, so it is downloaded only once.
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.14.1" "torchvision==0.29.1"

# Install dependencies first, so this layer is cached until pyproject.toml changes.
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py \
    && pip install -e ".[dev]"

COPY . .

# Run as a non-root user; give it the private storage folder.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data/storage \
    && chown -R appuser:appuser /data /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
