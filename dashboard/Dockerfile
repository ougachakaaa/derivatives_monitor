FROM scratch AS context-audit
COPY . /

FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/index.html dashboard/vite.config.js ./
COPY dashboard/src/ ./src/
COPY dashboard/tests/ ./tests/
RUN npm test && npm run build

FROM nginx:stable-alpine AS runtime
COPY dashboard/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
USER 65532:65532
EXPOSE 8080
STOPSIGNAL SIGQUIT
ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
