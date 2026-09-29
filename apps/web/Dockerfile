FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY apps/extension/package.json apps/extension/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN npm ci --workspace @job-search-assistant/web --include-workspace-root

COPY apps/web apps/web
RUN npm run build:web

FROM nginx:1.27-alpine

COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=5s \
  CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
