# pgvector for message embeddings plus PostGIS for spatial queries, in one database.
FROM pgvector/pgvector:0.8.0-pg16
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-postgis-3 \
    && rm -rf /var/lib/apt/lists/*
COPY init.sql /docker-entrypoint-initdb.d/20-extensions.sql
