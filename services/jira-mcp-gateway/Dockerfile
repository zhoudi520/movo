FROM node:20-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl ca-certificates \
  && rm -rf /var/lib/apt/lists/* \
  && npm install -g supergateway@4.1.0 \
  && npm cache clean --force

WORKDIR /app
COPY server.mjs /app/server.mjs

# Warm npm cache for Jira MCP server package.
RUN npx -y @parassolanki/jira-mcp-server@latest --help >/dev/null 2>&1 || true

ENV PUBLIC_PORT=8766 \
  PUBLIC_HOST=0.0.0.0 \
  ADMIN_API_BASE_URL=http://admin-api:8100 \
  CONFIG_POLL_INTERVAL_SECONDS=15 \
  RUNTIME_ENV_PATH=/run/askai-secrets/runtime.env

EXPOSE 8766

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=30s \
  CMD curl -fsS http://127.0.0.1:8766/healthz || exit 1

CMD ["node", "/app/server.mjs"]
