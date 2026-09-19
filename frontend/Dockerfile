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
COPY . .
RUN npm run build

FROM base AS prod
ENV NODE_ENV=production
COPY --from=builder /srv/app/public ./public
COPY --from=builder /srv/app/.next/standalone ./
COPY --from=builder /srv/app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
