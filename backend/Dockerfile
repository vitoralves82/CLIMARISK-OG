FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (GDAL 3.10.x no Debian Bookworm)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    postgresql-client \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Pin GDAL Python to match system libgdal version
RUN GDAL_VERSION=$(gdal-config --version) && \
    pip install --no-cache-dir "gdal==${GDAL_VERSION}"

# Copy and install requirements (sem GDAL, já instalado acima)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
