FROM nginx:latest as base

FROM base AS local
COPY nginx.conf.local.template /etc/nginx/nginx.conf.template
COPY --chmod=0755 entrypoint.sh /entrypoint.sh
EXPOSE 80
CMD ["/bin/sh", "-c", "/entrypoint.sh"]

FROM base AS development
COPY nginx.conf.dev.template /etc/nginx/nginx.conf.dev.template
COPY --chmod=0755 entrypoint.sh /entrypoint.sh
EXPOSE 80
CMD ["/bin/sh", "-c", "/entrypoint.sh"]

FROM base AS production
COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY --chmod=0755 entrypoint.sh /entrypoint.sh
EXPOSE 80
EXPOSE 443
CMD ["/bin/sh", "-c", "/entrypoint.sh"]

