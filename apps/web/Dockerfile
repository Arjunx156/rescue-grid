# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS build
COPY --from=oven/bun:1.4.3 /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json bun.lock ./
# postinstall copies the MapLibre worker into public/
RUN mkdir -p public && bun install --frozen-lockfile
COPY . .
# NEXT_PUBLIC_* are inlined and rewrites are fixed at build time
ARG API_INTERNAL_URL=http://api:8000
# canonical URLs, the sitemap and social cards point here
ARG PUBLIC_BASE_URL=http://localhost
# shown on the privacy and terms pages when set
ARG CONTACT_EMAIL=
ARG NEXT_PUBLIC_MAP_STYLE_DARK=
ARG NEXT_PUBLIC_MAP_STYLE_LIGHT=
ENV API_INTERNAL_URL=$API_INTERNAL_URL \
    PUBLIC_BASE_URL=$PUBLIC_BASE_URL \
    CONTACT_EMAIL=$CONTACT_EMAIL \
    NEXT_PUBLIC_MAP_STYLE_DARK=$NEXT_PUBLIC_MAP_STYLE_DARK \
    NEXT_PUBLIC_MAP_STYLE_LIGHT=$NEXT_PUBLIC_MAP_STYLE_LIGHT
RUN bun run build

FROM node:24-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
