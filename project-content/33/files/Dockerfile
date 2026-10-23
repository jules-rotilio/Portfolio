FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Europe/Paris
WORKDIR /app

# Aucune dépendance externe : bibliothèque standard uniquement.
COPY jobwatch/ ./jobwatch/

RUN useradd --create-home --uid 1000 jobwatch && mkdir -p /app/data && chown jobwatch /app/data
USER jobwatch

CMD ["python", "-m", "jobwatch", "--config", "/app/config.toml"]
