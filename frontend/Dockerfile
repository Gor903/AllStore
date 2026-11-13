FROM node:22-slim AS base
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /srv/app

FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci

FROM deps AS dev
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

FROM deps AS builder
# Next inlines NEXT_PUBLIC_* into the browser bundle at build time, so these have to arrive
# here and not at `docker run`. Left unset they fall back to the local defaults in lib/env.ts,
# and the browser would look for cookies without the `__Host-` prefix the backend sets.
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_BASE_DOMAIN
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_SESSION_COOKIE
ARG NEXT_PUBLIC_CSRF_COOKIE
COPY . .
# `public/` в проекте нет — иконка и стили лежат в `src/app`, — а COPY ниже его ждёт. Пустой
# каталог стоит ничего и переживёт тот день, когда в проект положат первый статический файл.
RUN npm run build && mkdir -p public

FROM base AS prod
ENV NODE_ENV=production
COPY --from=builder /srv/app/public ./public
COPY --from=builder /srv/app/.next/standalone ./
COPY --from=builder /srv/app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
