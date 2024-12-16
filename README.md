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

## Nginx configuration 
The proxy configuration is done by the `/proxy` docker container. There are three `nginx.conf[environment].template` that have the specific configuration for all the environemnts ('local', 'development', 'production').
This can be configured by the `ENVIRONMENT` env variable.

#### SSL configuration

By default the dev and prod example redirect to use SSL for the server meaning a certificate has to be configured. This can be done using the certbot image that is included in the docker compose.

**Prerequisites**
- The DNS has to have a A record for the domain `domain.net`  pointing to the server
- Access to the server

**Steps**
> [!IMPORTANT]
> This example uses `domain.net` as the default domain to create the certs for, REPLACE WITH THE CORRECT DOMAIN BEFORE RUNNING THE STEPS BELOW!


1. Replace the `nginx.conf[environment].template` relevant to the environment you are deploying to with the following content. At this moment we want to serve the acme challenge url so the cerbot can resolve the certificate. 

```
worker_processes 8;
user root;
error_log  /var/log/nginx/error.log;
pid /var/run/nginx.pid;

events {}

http {
    include mime.types;
    server {
        listen 80;
        server_name $SERVER_HOST;

        location /static/ {
            alias /static/;
            autoindex on;
            access_log off;
        }
        
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }        
    }
}
```

2. Run the following commands from the root of the repository

```
docker compose build
docker compose up -d
docker compose run --rm  certbot certonly --webroot --webroot-path /var/www/certbot/ --dry-run -d domain.net
```
3. if the dry-run completes successfully then execute the following command, this will create the certificate files in the machine

```
docker compose run --rm  certbot certonly --webroot --webroot-path /var/www/certbot/ -d domain.net
```
4. Restore `nginx.conf[environment].template` to default values and run 

```
docker compose build
docker compose up -d
```
**Certificate renewal**

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

