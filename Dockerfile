FROM postgres:18.3 AS postgres_tools
FROM python:3.14.8-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 liblz4-1 libzstd1 && rm -rf /var/lib/apt/lists/*
COPY --from=postgres_tools /usr/lib/postgresql/18/bin/pg_dump /usr/local/bin/pg_dump
COPY --from=postgres_tools /usr/lib/postgresql/18/bin/pg_restore /usr/local/bin/pg_restore
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home escalapro && mkdir -p instance tmp && chown -R escalapro:escalapro /app

FROM base AS test
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY --chown=escalapro:escalapro . .
USER escalapro
ENV PYTHON_DOTENV_DISABLED=1
CMD ["python", "-m", "pytest", "-q", "-W", "error"]

FROM base AS production
COPY --chown=escalapro:escalapro . .
USER escalapro
EXPOSE 10000
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:create_app()"]
