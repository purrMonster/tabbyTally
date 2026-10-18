FROM python:3.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY processing/pyproject.toml ./
COPY processing/src ./src
RUN pip install --no-cache-dir . && useradd --create-home processor
USER processor
ENTRYPOINT ["tabby-processing"]
CMD ["--help"]
