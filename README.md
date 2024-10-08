# Mozilla Aire

## Project Structure

* `backend` (`django-rest`)
* `frontend` (`react`)
* `database` (`postgres`)
* `proxy` (`nginx`)


## Deployment with `docker`
Create `.env` file:
```
POSTGRES_DB="<db>"
POSTGRES_USER="<user>"
POSTGRES_PASSWORD="<password>"
POSTGRES_PORT="<default:5432>"
BACKEND_SECRET_KEY="<django-insecure-...>"
BACKEND_PORT="<default:8000>"
PROXY_PORT="<default:80>"
```
Build containers, run them:
```
docker compose build
docker compose -d up
```

## System Architecture
![final_system_architecture](https://github.com/user-attachments/assets/38adc07b-9431-4aa8-b102-fef3cb6ee2e7)

