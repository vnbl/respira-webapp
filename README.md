# Mozilla Aire

## Project Structure

* `backend` (`django-rest`)
* `frontend` (`react`)
* `database` (`postgres`)
* `proxy` (`nginx`)


## Running the project locally

Since the project uses a proxy it's necessary to set the .env with
```
ENVIRONMENT="local"
```
otherwise the project will fail due to a missing SSL certificate.

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
docker compose up -d
```

## Deployment with ssl
The deployment with ssl is done in two parts 

First it's necessary to set up the acme challenge on the http port for that comment out the 443 ssl server and run

```
docker compose build
docker compose up -d
docker compose run --rm  certbot certonly --webroot --webroot-path /var/www/certbot/ --dry-run -d dev.proyectorespira.org
```
if the dry-run completes successfully then execute

```
docker compose run --rm  certbot certonly --webroot --webroot-path /var/www/certbot/ -d dev.proyectorespira.org
docker compose restart 
```
Uncomment the https server on the `nginx.conf.template` and run

```
docker compose build
docker compose up -d
```
To renew the certifcate run 

```
docker compose run --rm certbot renew
docker compose restart
```

## System Architecture
![final_system_architecture](https://github.com/user-attachments/assets/38adc07b-9431-4aa8-b102-fef3cb6ee2e7)

## Database Architecture (full)
![data_retriever_v4(2)](https://github.com/user-attachments/assets/ebf11e69-8501-425e-b403-120dc5b3f6c0)

## Database Architecture (partial - necessary for API)
![data_retriever_only_front](https://github.com/user-attachments/assets/ec49ab22-fa49-460d-a7e9-9757922dda38)

