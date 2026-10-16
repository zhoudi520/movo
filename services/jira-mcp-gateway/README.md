# Jira MCP Gateway

将 `@parassolanki/jira-mcp-server`（stdio）以 **Streamable HTTP** 暴露给 MOVO，并按 `main_id` + `X-MOVO-User-ID` 多租户/多用户隔离。

## 启动（Compose profile）

```bash
docker compose --profile jira-mcp up -d --build jira-mcp-gateway
```

管理后台：**工具与 MCP → Jira MCP 网关** 填写企业默认 Jira URL、凭证与网关密钥；终端用户在 user-web **我的工具 → Jira 账号** 绑定个人站点与 Token（未绑定则回退企业默认）。

## 端点

- 对外（MOVO / 本机调试）：`http://127.0.0.1:8766/mcp`
- Compose 内 chat-api：`http://jira-mcp-gateway:8766/mcp`
- 健康检查：`GET /healthz`

## 配置拉取

- **轮询** `GET /api/internal/jira-mcp-gateway/runtime-config`：租户 `gatewayKey` 索引（约 15s）。
- **按需** `GET /api/internal/jira-mcp-gateway/effective-config?mainId=&userId=`：合并用户/企业 Jira 凭证，用于启动 supergateway 子进程（短 TTL 内存缓存）。

对外 **无需 Bearer**；请求需携带 MOVO 注入的 `X-MOVO-Main-ID`、`X-MOVO-User-ID`。网关向本机 supergateway 转发时自动注入内部密钥。

## 子进程与资源

- 每个 `(mainId, userId)` 可独立 supergateway 进程；超过 `MAX_SUBPROCESSES` 时 LRU 淘汰；`SUBPROCESS_IDLE_MS` 无请求则回收。
- 勿将 Token 写入仓库；根目录 `jira-mcp.json` 仅作本地 supergateway 试验参考，生产请用管理页与用户绑定页。
