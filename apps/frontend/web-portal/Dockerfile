FROM node:20-alpine AS builder

WORKDIR /app

COPY apps/frontend/web-portal/package*.json ./
RUN npm ci

COPY apps/frontend/web-portal ./
RUN npm run build

FROM nginx:1.27-alpine

COPY apps/frontend/web-portal/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 3100

HEALTHCHECK --interval=30s --timeout=5s --retries=5 --start-period=10s \
  CMD wget -q --spider http://127.0.0.1:3100/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
