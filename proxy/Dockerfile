FROM nginx:latest

ENV BACKEND_HOST=${BACKEND_HOST}
ENV BACKEND_PORT=${BACKEND_PORT}

RUN apt-get update && \
    apt-get install -y gettext-base

COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY entrypoint.sh /entrypoint.sh

EXPOSE ${PROXY_PORT}

RUN chmod +x /entrypoint.sh

CMD ["/bin/sh", "-c", "/entrypoint.sh"]