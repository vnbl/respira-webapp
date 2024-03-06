ARG PYTHON_VERSION=3.8-slim-buster

FROM python:${PYTHON_VERSION}

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt /app/
RUN set -ex && \
    pip install --upgrade pip && \
    pip install -r /app/requirements.txt && \
    rm -rf /root/.cache/

COPY . /app/

# RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "--bind", ":8000", "--workers", "2", "backend.wsgi:application"]