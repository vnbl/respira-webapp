# Mozilla Aire

## Project Structure
```
backend (django rest)
    * contains endpoints for retrieving data (coordinates and values) to be displayed in frontend map
frontend (react)
    * displays tables and maps with data from the backend
    * allows users to download data
database (mysql)
    * stores historical air quality observations

TBD:
    * host model in backend? spin up inference endpoint separately?
```

## Deployment with `docker`
```
docker compose build
docker compose up
```