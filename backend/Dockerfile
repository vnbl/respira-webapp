ARG PYTHON_VERSION=3.10-slim-buster

FROM python:${PYTHON_VERSION}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install curl -y

WORKDIR /app

COPY requirements.txt /app/

RUN set -ex && \
    pip install --upgrade pip && \
    pip install -r /app/requirements.txt && \
    rm -rf /root/.cache/

COPY . /app/

EXPOSE 8000

RUN chmod +x /app/entrypoint.sh

CMD ["/bin/sh", "-c", "/app/entrypoint.sh"]