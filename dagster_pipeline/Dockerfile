FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY dagster_pipeline/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the sentence-transformers model so it's baked into the image
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy application code
COPY dagster_pipeline/ dagster_pipeline/
COPY data/ data/

# Dagster webserver port
EXPOSE 3000

# Create tables then start Dagster webserver
# Tables must exist before pipeline assets can truncate them
CMD ["sh", "-c", "python -m dagster_pipeline.models.database && dagster dev -m dagster_pipeline -h 0.0.0.0 -p 3000"]
