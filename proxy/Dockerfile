FROM nginx:latest as base

ENV BACKEND_HOST=${BACKEND_HOST}
ENV BACKEND_PORT=${BACKEND_PORT}
ENV CERT_NAME=${CERT_NAME} 

FROM base AS local
COPY nginx.conf.local.template /etc/nginx/nginx.conf.template
COPY --chmod=0755 entrypoint.sh /entrypoint.sh
EXPOSE 80
CMD ["/bin/sh", "-c", "/entrypoint.sh"]

FROM base AS production
COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY --chmod=0755 entrypoint.sh /entrypoint.sh
EXPOSE 80
EXPOSE 443
CMD ["/bin/sh", "-c", "/entrypoint.sh"]


