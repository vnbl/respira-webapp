#!/bin/sh
envsubst '$BACKEND_HOST $BACKEND_PORT $CERT_NAME $PIPELINE_HOST $PIPELINE_PORT' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf
nginx -g 'daemon off;'