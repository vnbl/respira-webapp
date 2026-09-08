# Backend

Developed using `django`

## Environment

Create `backend/.env` from `backend/.env.example`.

Required Postgres variables:

```env
BACKEND_SECRET_KEY=replace-me
BACKEND_DEBUG=true

BACKEND_POSTGRES_DB=replace-me
BACKEND_POSTGRES_USER=replace-me
BACKEND_POSTGRES_PASSWORD=replace-me
BACKEND_POSTGRES_HOST=replace-me
BACKEND_POSTGRES_PORT=5432
BACKEND_POSTGRES_SSLMODE=require

BACKEND_RUN_MIGRATIONS=false
BACKEND_CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

If your provider requires a CA bundle or client certificate, also set:

```env
BACKEND_POSTGRES_SSLROOTCERT=/app/certs/ca.pem
BACKEND_POSTGRES_SSLCERT=/app/certs/client.crt
BACKEND_POSTGRES_SSLKEY=/app/certs/client.key
```

## Run Locally

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate api --fake-initial
python manage.py runserver 0.0.0.0:8000
```

## Quality checks

From repository root:

```bash
pre-commit run mypy --all-files
pre-commit run django-checks --all-files
```

Notes:

- The `django-checks` hook uses `backend/.venv/bin/python`.
- Typing dependencies for `mypy` are managed by pre-commit, not by `backend/requirements.txt`.

## Build and Deploy using Docker

Without custom cert files:

```bash
cd backend
docker build -t respira-backend .
docker run --rm -p 8000:8000 --env-file .env respira-backend
```

With custom cert files in `backend/certs/`:

```bash
cd backend
docker build -t respira-backend .
docker run --rm -p 8000:8000 --env-file .env -v "$(pwd)/certs:/app/certs:ro" respira-backend
```

Then open:

- `http://localhost:8000/api/health/`
- `http://localhost:8000/api/stations/`
- `http://localhost:8000/api/regions/`
- `http://localhost:8000/api/map/?entity=region&id=<region_id>`
- `http://localhost:8000/api/stations/<station_id>/forecast/`
- `http://localhost:8000/api/schema/swagger-ui/`
