ARG PYTHON_VERSION=3.12-slim-bookworm

FROM python:${PYTHON_VERSION} AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VENV_PATH=/opt/venv

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/

RUN set -ex && \
    python -m venv ${VENV_PATH} && \
    ${VENV_PATH}/bin/pip install --upgrade pip && \
    ${VENV_PATH}/bin/pip install -r /app/requirements.txt && \
    rm -rf /root/.cache/

FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VENV_PATH=/opt/venv
ENV PATH="${VENV_PATH}/bin:${PATH}"

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl gosu && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1001 appgroup && \
    useradd --system --uid 1001 --gid appgroup appuser

WORKDIR /app

COPY --from=builder ${VENV_PATH} ${VENV_PATH}
COPY . /app/

RUN chmod +x /app/entrypoint.sh && \
    chown -R appuser:appgroup /app

EXPOSE 8000

CMD ["/bin/sh", "-c", "/app/entrypoint.sh"]
