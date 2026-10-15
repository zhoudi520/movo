$env:JIRA_PERSONAL_ACCESS_TOKEN = "lasean.zhou@afe.hk:ATATT3xFfGF05yukPCCPQz3fO_YLRmm3IFyRlqnatAzSDgTQNlyJfJ5JyUS8piqkfMwIHD3H_bYRP37PU4kiyLYBOnFVWMuNja07QTdTYKWL8cJlvaf-GiAyWf164ga66xiZB-MUdttAhKq9e4OrkyZaCNWsK26-CWQyK4DHg0-ZciXF287KApc=0624DFE8"
$env:JIRA_BASE_URL = "https://n2nafe.atlassian.net"
$env:MCP_GATEWAY_KEY = "随机长密钥"


npx -y supergateway `
  --stdio "npx.cmd -y @parassolanki/jira-mcp-server@latest" `
  --outputTransport streamableHttp `
  --stateful `
  --sessionTimeout 600000 `
  --protocolVersion 2025-06-18 `
  --port 8766 `
  --host 127.0.0.1 `
  --apiKey $env:MCP_GATEWAY_KEY