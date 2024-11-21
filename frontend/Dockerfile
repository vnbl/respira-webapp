FROM node:lts AS base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"

ARG PUBLIC_BACKEND_URL
ARG PUBLIC_REGION_DEFAULT_ID
ARG SITE_URL

RUN corepack enable
COPY . /app
WORKDIR /app

FROM base AS prod-deps
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --prod --frozen-lockfile

FROM base AS build
RUN --mount=type=cache,id=pnpm,target=/pnpm/store  pnpm install --frozen-lockfile
RUN echo SITE_URL=$SITE_URL >> .env
RUN echo PUBLIC_BACKEND_URL=$PUBLIC_BACKEND_URL >> .env
RUN echo PUBLIC_REGION_DEFAULT_ID=$PUBLIC_REGION_DEFAULT_ID >> .env
RUN echo SMTP_KEY=$SMTP_KEY >> .env
RUN echo SMTP_SENDER=$SMTP_SENDER >> .env

RUN pnpm run build

FROM base
COPY --from=prod-deps /app/node_modules /app/node_modules

FROM base AS runtime
COPY --from=prod-deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist

ENV HOST=0.0.0.0
ENV PORT=${FRONTEND_PORT}

EXPOSE ${FRONTEND_PORT}
CMD export PORT=${FRONTEND_PORT} && node ./dist/server/entry.mjs