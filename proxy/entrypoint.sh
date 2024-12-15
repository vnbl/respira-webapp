#!/bin/sh
envsubst '$BACKEND_HOST $BACKEND_PORT $CERT_NAME $PIPELINE_HOST $PIPELINE_PORT $FRONTEND_PORT $FRONTEND_HOST $SERVER_HOST' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf
nginx -g 'daemon off;'