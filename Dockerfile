# syntax=docker/dockerfile:1
FROM python:3.13.18-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72 AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH
WORKDIR /app
RUN python -m venv /opt/venv \
    && groupadd --gid 10001 sdw \
    && useradd --uid 10001 --gid sdw --no-create-home --shell /usr/sbin/nologin sdw
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --no-user -r /tmp/requirements.txt
COPY --chown=10001:10001 app/ app/
COPY --chown=10001:10001 migrations/ migrations/
COPY --chown=10001:10001 dev/ dev/
COPY --chown=10001:10001 alembic.ini ./
COPY scripts/build_locales.py scripts/build_locales.py
RUN python scripts/build_locales.py
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM runtime AS test
USER root
COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --no-cache-dir --no-user -r /tmp/requirements-dev.txt
COPY --chown=10001:10001 tests/ tests/
COPY --chown=10001:10001 scripts/dev.py scripts/dev.py
COPY --chown=10001:10001 compose*.yaml Dockerfile .dockerignore /app/
USER 10001:10001
CMD ["python", "-m", "dev.run_tests"]
