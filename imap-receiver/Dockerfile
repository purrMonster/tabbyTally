FROM python:3.14-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home receiver

COPY src ./src
COPY migrations ./migrations

COPY tests ./tests
USER receiver

ENTRYPOINT ["python", "-m", "src.cli"]
CMD ["--help"]
