# Backend Environment Variables

All backend configuration is done at runtime. A single image runs across dev, staging, and production by changing only environment variables.

## Where to set these variables

| Context                                  | File to edit                                                                                                               |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **docker-compose** (full stack)          | `.env` in the repository root — all backend vars are declared there and passed to the backend container via `environment:` |
| **Backend standalone** (without compose) | `backend/.env` — read directly by Django via `python-dotenv`                                                               |

See [`.env.example`](../.env.example) for the docker-compose reference and [`backend/.env.example`](../backend/.env.example) for the standalone backend reference.

---

## Core Application

| Variable                       | Required          | Default                          | Where used                                    | Notes                                                                                                                                                                                                                                                                                                                                        |
| ------------------------------ | ----------------- | -------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `BACKEND_SECRET_KEY`           | Yes in production | `respira-backend-dev-secret-key` | `backend/backend/settings.py`                 | Django secret key. Generate a strong random value for production.                                                                                                                                                                                                                                                                            |
| `BACKEND_DEBUG`                | No                | `false`                          | `backend/backend/settings.py`                 | Django debug mode. Must be `false` in production.                                                                                                                                                                                                                                                                                            |
| `BACKEND_PORT`                 | No                | `8000`                           | `backend/entrypoint.sh`, `docker-compose.yml` | Port gunicorn binds to inside the container.                                                                                                                                                                                                                                                                                                 |
| `BACKEND_RUN_MIGRATIONS`       | No                | `true`                           | `backend/entrypoint.sh`                       | Set to `false` to skip automatic migrations on container start.                                                                                                                                                                                                                                                                              |
| `BACKEND_ALLOWED_HOSTS`        | No                | `""` (empty)                     | `backend/backend/settings.py`                 | Additional comma-separated hostnames appended to Django `ALLOWED_HOSTS`. Use hostnames only (no scheme or port), for example `demo.proyectorespira.net,backend`. Useful for reverse-proxy/container internal host routing (e.g. `backend:8000` requests). |
| `BACKEND_CORS_ALLOWED_ORIGINS` | No                | `""` (empty)                     | `backend/backend/settings.py`                 | Comma-separated list of origins allowed to make cross-site requests. In docker-compose, set to `http://frontend:4321` if frontend SSR makes direct backend calls. For local dev: `http://localhost:8000,http://127.0.0.1:8000`. The variable name `BACKEND_CORS_ALLOWED_ORIGINS` is required — `CORS_ALLOWED_ORIGINS` alone will be ignored. |

---

## GlitchTip Error Monitoring (optional)

Leave the DSN blank to disable monitoring. The backend sends only unexpected
server errors; request bodies, cookies, query strings, credentials, email
addresses, and usernames are excluded. Authenticated events contain only the
internal user ID and role.

| Variable | Required | Default | Where used | Notes |
| --- | --- | --- | --- | --- |
| `BACKEND_GLITCHTIP_DSN` | No | `""` | `backend/backend/settings.py` | Private DSN for the backend GlitchTip project. Leave blank locally and in tests to disable reporting. |
| `GLITCHTIP_ENVIRONMENT` | No | `""` | `backend/backend/settings.py` | Controlled deployment label, such as `production` or `demo`. Do not infer it from `BACKEND_DEBUG`. |
| `GLITCHTIP_RELEASE` | No | `""` | `backend/backend/settings.py` | Immutable release label shared with the frontend, normally the GitHub Release tag. |

See `docs/glitchtip-monitoring.md` for hosted-project setup, alerting, and source-map upload secrets.

---

## Database — PostgreSQL

All five core vars must be set together to enable PostgreSQL. If any is missing the backend falls back to SQLite (development only).

| Variable                    | Required         | Default        | Where used                    | Notes                                                                   |
| --------------------------- | ---------------- | -------------- | ----------------------------- | ----------------------------------------------------------------------- |
| `BACKEND_POSTGRES_DB`       | Yes (PostgreSQL) | —              | `backend/backend/settings.py` | Database name.                                                          |
| `BACKEND_POSTGRES_USER`     | Yes (PostgreSQL) | —              | `backend/backend/settings.py` | Database user.                                                          |
| `BACKEND_POSTGRES_PASSWORD` | Yes (PostgreSQL) | —              | `backend/backend/settings.py` | Database password.                                                      |
| `BACKEND_POSTGRES_HOST`     | Yes (PostgreSQL) | —              | `backend/backend/settings.py` | Database host.                                                          |
| `BACKEND_POSTGRES_PORT`     | Yes (PostgreSQL) | —              | `backend/backend/settings.py` | Database port.                                                          |
| `BACKEND_POSTGRES_SCHEMA`   | No               | (empty)        | `backend/backend/settings.py` | Extra schemas appended to `search_path`, after the fixed `django_admin, respira_gold, public` prefix. Does **not** control table resolution — see below. |

Table ownership between Django-owned data (`django_admin`) and the data pipeline's tables (`respira_gold`) is a fixed contract, not something `BACKEND_POSTGRES_SCHEMA` can change: `search_path` always resolves `django_admin` first, then `respira_gold`, then `public`, regardless of what this variable is set to. Every gold model (`Regions`, `Stations`, `StationReadingsGold`, `RegionReadings`, `InferenceRuns`, `InferenceResults`) additionally mixes in `api.gold.ReadOnlyGoldModel`, which rejects writes from the backend ORM outright — the pipeline (dbt, or the Prefect inference flow) is the only writer. `BACKEND_POSTGRES_SCHEMA` exists only to append unrelated extra schemas (e.g. a Postgres extension's schema) after that fixed prefix.

---

## Database — SSL (optional)

All four are optional. Set only the ones your database provider requires.

| Variable                       | Required | Default | Where used                    | Notes                                   |
| ------------------------------ | -------- | ------- | ----------------------------- | --------------------------------------- |
| `BACKEND_POSTGRES_SSLMODE`     | No       | —       | `backend/backend/settings.py` | Added to PostgreSQL `OPTIONS` when set. |
| `BACKEND_POSTGRES_SSLROOTCERT` | No       | —       | `backend/backend/settings.py` | Path to CA certificate file.            |
| `BACKEND_POSTGRES_SSLCERT`     | No       | —       | `backend/backend/settings.py` | Path to client certificate file.        |
| `BACKEND_POSTGRES_SSLKEY`      | No       | —       | `backend/backend/settings.py` | Path to client key file.                |

---

## Migrations & Process (optional)

| Variable            | Required | Default    | Where used              | Notes                                                                           |
| ------------------- | -------- | ---------- | ----------------------- | ------------------------------------------------------------------------------- |
| `BACKEND_APP_USER`  | No       | `appuser`  | `backend/entrypoint.sh` | OS user gunicorn drops privileges to. Only used when container starts as root.  |
| `BACKEND_APP_GROUP` | No       | `appgroup` | `backend/entrypoint.sh` | OS group gunicorn drops privileges to. Only used when container starts as root. |

---

## Gunicorn Tuning (optional)

| Variable | Required | Default | Where used | Notes |
|---|---|---|---|---|
| `BACKEND_GUNICORN_WORKERS` | No | `4` | `backend/entrypoint.sh` | Number of gunicorn worker processes. Rule of thumb: `2 × CPU cores + 1`. Reduce to `2` on low-memory servers (≤1GB RAM). |
| `BACKEND_GUNICORN_TIMEOUT` | No | `30` | `backend/entrypoint.sh` | Seconds before a worker is killed and restarted. Increase if endpoints are slow due to remote DB latency. |
| `BACKEND_GUNICORN_MAX_REQUESTS` | No | `1000` | `backend/entrypoint.sh` | Worker is recycled after serving this many requests, preventing memory leaks. |
| `BACKEND_GUNICORN_MAX_REQUESTS_JITTER` | No | `100` | `backend/entrypoint.sh` | Random jitter added to `MAX_REQUESTS` so all workers don't restart simultaneously. |
| `BACKEND_APP_GROUP` | No | `appgroup` | `backend/entrypoint.sh` | OS group gunicorn drops privileges to. Only used when container starts as root. |

---

## Device Followers & Sensor Alerts (optional)

The device-follower endpoints are unauthenticated by design (the app has no login), so the throttle and the follow cap are what bound abuse of them rather than product limits — expect to tune them per environment.

| Variable                               | Required | Default    | Where used                       | Notes                                                                                                                                                                                              |
| -------------------------------------- | -------- | ---------- | -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `BACKEND_DEVICE_FOLLOWER_THROTTLE`     | No       | `120/min`  | `backend/backend/settings.py`    | DRF rate for the `device_followers` scope, counted per client IP. Deliberately generous: mobile carriers put many phones behind one CGNAT address, and a tight limit cuts off a whole network.      |
| `BACKEND_MAX_FOLLOWS_PER_INSTALLATION` | No       | `10`       | `backend/backend/settings.py`    | How many stations one installation may follow. Exceeding it returns 400 with `"code": "max_follows_reached"`.                                                                                       |
| `BACKEND_SENSOR_ALERTS_ENABLED`        | No       | `false`    | `backend/backend/settings.py`    | Whether `send_sensor_alerts` actually delivers push notifications. Off by default so a freshly deployed environment cannot start notifying real devices; the command still offers `--dry-run`/`--force`. Setting it to `true` is not enough on its own — the command also has to be scheduled, see [Per-sensor push alerts](sensor-alerts.md). |

---

## Model Column Overrides (optional)

Override these only if your database schema uses different column names than the defaults.

| Variable                               | Required | Default          | Where used              | Notes                                             |
| -------------------------------------- | -------- | ---------------- | ----------------------- | ------------------------------------------------- |
| `BACKEND_STATION_READINGS_DATE_COLUMN` | No       | `date_localtime` | `backend/api/models.py` | Column mapped to `StationReadingsGold.date_utc`.  |
| `BACKEND_INFERENCE_RESULTS_6H_COLUMN`  | No       | `forecast_6h`    | `backend/api/models.py` | Column mapped to the 6-hour forecast JSON field.  |
| `BACKEND_INFERENCE_RESULTS_12H_COLUMN` | No       | `forecast_12h`   | `backend/api/models.py` | Column mapped to the 12-hour forecast JSON field. |

---

## Admin — Default Superuser (bootstrap)

If both variables are set, `entrypoint.sh` runs `manage.py bootstrap_superuser`
on start and creates this Django Admin superuser. Idempotent: an existing
account is never modified (its password is not reset), so it is safe on every
deploy. Leave unset to skip. Intended to seed the first `/admin/` login on
staging/production — change the password after first login.

| Variable                     | Required | Default | Where used                                            | Notes                                                       |
| ---------------------------- | -------- | ------- | ----------------------------------------------------- | ----------------------------------------------------------- |
| `BACKEND_SUPERUSER_EMAIL`    | No       | —       | `accounts/management/commands/bootstrap_superuser.py` | Email/login of the superuser to create.                     |
| `BACKEND_SUPERUSER_PASSWORD` | No       | —       | `accounts/management/commands/bootstrap_superuser.py` | Password for that superuser. Use a strong value; rotate it. |

---

## Admin — Authentication & Sessions (optional)

Session and cookie behaviour for the `/admin/` backoffice. Secure cookie flags
default to **on whenever `BACKEND_DEBUG=false`**, so most of these can stay unset
in production. See `docs/admin-auth-configuration.md`.

| Variable                                  | Required                | Default              | Where used                    | Notes                                                                     |
| ----------------------------------------- | ----------------------- | -------------------- | ----------------------------- | ------------------------------------------------------------------------- |
| `BACKEND_CSRF_TRUSTED_ORIGINS`            | Yes behind HTTPS proxy  | `""` (empty)         | `backend/backend/settings.py` | Comma-separated HTTPS origins trusted for admin POSTs. Required behind the proxy or login is rejected. |
| `BACKEND_SESSION_COOKIE_AGE`              | No                      | `28800` (8h)         | `backend/backend/settings.py` | Session lifetime in seconds.                                              |
| `BACKEND_SESSION_EXPIRE_AT_BROWSER_CLOSE` | No                      | `false`              | `backend/backend/settings.py` | Delete the session cookie when the browser closes.                       |
| `BACKEND_SESSION_SAVE_EVERY_REQUEST`      | No                      | `false`              | `backend/backend/settings.py` | Refresh session expiry on every request (sliding session).              |
| `BACKEND_SESSION_COOKIE_SECURE`           | No                      | `true` when not DEBUG | `backend/backend/settings.py` | Send the session cookie over HTTPS only.                                 |
| `BACKEND_CSRF_COOKIE_SECURE`              | No                      | `true` when not DEBUG | `backend/backend/settings.py` | Send the CSRF cookie over HTTPS only.                                    |
| `BACKEND_SESSION_COOKIE_SAMESITE`         | No                      | `Lax`                | `backend/backend/settings.py` | SameSite policy for the session cookie.                                  |
| `BACKEND_CSRF_COOKIE_SAMESITE`            | No                      | `Lax`                | `backend/backend/settings.py` | SameSite policy for the CSRF cookie.                                     |

---

## Admin — Security Hardening (optional)

Login rate limiting (django-axes), password policy and HTTPS/HSTS. Production
values default from `BACKEND_DEBUG`; override only to diverge. See
`docs/admin-security-hardening.md`.

| Variable                                 | Required | Default               | Where used                    | Notes                                                            |
| ---------------------------------------- | -------- | --------------------- | ----------------------------- | ---------------------------------------------------------------- |
| `BACKEND_AXES_ENABLED`                   | No       | `true`                | `backend/backend/settings.py` | Master switch for login rate limiting.                           |
| `BACKEND_AXES_FAILURE_LIMIT`             | No       | `5`                   | `backend/backend/settings.py` | Failed logins before lockout.                                    |
| `BACKEND_AXES_COOLOFF_HOURS`             | No       | `1`                   | `backend/backend/settings.py` | Lockout duration in hours.                                       |
| `BACKEND_PASSWORD_MIN_LENGTH`            | No       | `10`                  | `backend/backend/settings.py` | Minimum password length.                                         |
| `BACKEND_PASSWORD_REQUIRE_SPECIAL`       | No       | `true`                | `backend/backend/settings.py` | Require a special character in passwords.                        |
| `BACKEND_SECURE_SSL_REDIRECT`            | No       | `true` when not DEBUG | `backend/backend/settings.py` | Redirect HTTP to HTTPS.                                          |
| `BACKEND_SECURE_HSTS_SECONDS`            | No       | `31536000` when not DEBUG | `backend/backend/settings.py` | HSTS max-age (0 disables).                                    |
| `BACKEND_SECURE_HSTS_INCLUDE_SUBDOMAINS` | No       | `true` when not DEBUG | `backend/backend/settings.py` | Apply HSTS to subdomains.                                        |
| `BACKEND_SECURE_HSTS_PRELOAD`            | No       | `true` when not DEBUG | `backend/backend/settings.py` | Set the HSTS preload flag.                                       |
| `BACKEND_SECURE_PROXY_SSL_HEADER`        | No       | `true` when not DEBUG | `backend/backend/settings.py` | Trust `X-Forwarded-Proto` from the TLS-terminating proxy.        |
| `BACKEND_X_FRAME_OPTIONS`                | No       | `DENY`                | `backend/backend/settings.py` | Clickjacking protection header value.                            |

---

## Admin — Email / Password Reset (optional)

Enables Django's email password-reset flow when SMTP is configured. In dev
(`BACKEND_DEBUG=true`) emails print to the console. See
`docs/admin-password-management.md`.

| Variable                     | Required | Default                                     | Where used                    | Notes                                             |
| ---------------------------- | -------- | ------------------------------------------- | ----------------------------- | ------------------------------------------------- |
| `BACKEND_EMAIL_BACKEND`      | No       | console (dev) / SMTP (prod)                 | `backend/backend/settings.py` | Django email backend dotted path.                 |
| `BACKEND_EMAIL_HOST`         | No       | `""`                                        | `backend/backend/settings.py` | SMTP host.                                        |
| `BACKEND_EMAIL_PORT`         | No       | `587`                                       | `backend/backend/settings.py` | SMTP port.                                        |
| `BACKEND_EMAIL_HOST_USER`    | No       | `""`                                        | `backend/backend/settings.py` | SMTP username.                                    |
| `BACKEND_EMAIL_HOST_PASSWORD`| No       | `""`                                        | `backend/backend/settings.py` | SMTP password.                                    |
| `BACKEND_EMAIL_USE_TLS`      | No       | `true`                                      | `backend/backend/settings.py` | Use STARTTLS.                                     |
| `BACKEND_DEFAULT_FROM_EMAIL` | No       | `no-reply@proyectorespira.net`              | `backend/backend/settings.py` | Default From address for outgoing admin emails.   |
| `BACKEND_PASSWORD_RESET_TIMEOUT_HOURS` | No | `24` | `backend/backend/settings.py` | How long a reset link stays valid, for both the admin and institutional flows. Django's own default is 72 hours. |
| `BACKEND_INSTITUTION_PASSWORD_RESET_URL` | No | `/institucion/restablecer-clave` | `backend/backend/settings.py` | Where the institutional reset email points. A path by default, so scheme and host come from the request and the link resolves per environment; an absolute URL overrides that, for a deployment where the site and the API are on different origins. |
| `BACKEND_PASSWORD_RESET_THROTTLE` | No | `10/hour` | `backend/backend/settings.py` | DRF rate for `POST /api/institution/password-reset/`, per client IP. This endpoint sends mail to an address the caller chose, so the rate is what stops it being used to flood an inbox. |
| `BACKEND_PASSWORD_RESET_CONFIRM_THROTTLE` | No | `30/hour` | `backend/backend/settings.py` | DRF rate for `POST /api/institution/password-reset/confirm/`, per client IP. Looser than the request above — a visitor may need several tries to satisfy the password rules — but still bounds token guessing. |

---

## Build-Time Variables

| Variable         | Required | Default              | Where used                   | Notes                                                                         |
| ---------------- | -------- | -------------------- | ---------------------------- | ----------------------------------------------------------------------------- |
| `PYTHON_VERSION` | No       | `3.10-slim-bookworm` | `backend/Dockerfile` (`ARG`) | Selects the base Python image. Not environment-specific — keep as build-time. |

---

## Notes

- The `BACKEND_CORS_ALLOWED_ORIGINS` variable name is what Django settings reads. Do not use `CORS_ALLOWED_ORIGINS` — it will be silently ignored.
- `BACKEND_ALLOWED_HOSTS` accepts bare hostnames only. Do not include protocol (`https://`) or port (`:8000`).
- Optional backend settings may be either omitted or left blank. The backend treats blank (including whitespace-only) values for optional string, integer, and boolean settings as unset and falls back to the documented defaults.
- `docker-compose.yml` passes many optional vars with `${VAR:-}` syntax, so Compose resolves missing values to empty strings before the container starts. The backend settings layer normalizes those empty strings back to the built-in defaults.
- Example env files are templates, not safe deploy-ready configs. Replace placeholder secrets such as `BACKEND_SECRET_KEY`, database passwords, bootstrap admin passwords, and SMTP/API credentials before any shared or production deployment.
