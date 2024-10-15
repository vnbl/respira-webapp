FROM nginx:latest

RUN apt-get update && \
    apt-get install -y gettext-base

COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY entrypoint.sh /entrypoint.sh

EXPOSE 80

RUN chmod +x /entrypoint.sh

CMD ["/bin/sh", "-c", "/entrypoint.sh"]