# Jira MCP Gateway

将 `@parassolanki/jira-mcp-server`（stdio）以 **Streamable HTTP** 暴露给 MOVO，并按 `main_id` 多租户隔离。

## 启动（Compose profile）

```bash
docker compose --profile jira-mcp up -d --build jira-mcp-gateway
```

管理后台：**工具与 MCP → Jira MCP 网关** 填写 Jira URL、凭证与网关密钥；保存后容器约 15s 内热重载对应租户子进程。

## 端点

- 对外（MOVO / 本机调试）：`http://127.0.0.1:8766/mcp`
- Compose 内 chat-api：`http://jira-mcp-gateway:8766/mcp`
- 健康检查：`GET /healthz`

## 凭证

- Jira 凭证与网关密钥保存在 **admin-api / Mongo**（加密），由本服务轮询 `/api/internal/jira-mcp-gateway/runtime-config` 拉取。
- 勿将 Token 写入仓库；根目录 `jira-mcp.json` 仅作本地 supergateway 试验参考，生产请用管理页。
