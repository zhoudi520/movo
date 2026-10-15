#!/usr/bin/env node
/**
 * Tenant-aware HTTP front for supergateway + parassolanki Jira MCP.
 * Validates Bearer (per-tenant gateway key) and X-MOVO-Main-ID, proxies to local supergateway instances.
 */

import { spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import { URL } from "node:url";

const PUBLIC_PORT = Number(process.env.PUBLIC_PORT || 8766);
const PUBLIC_HOST = process.env.PUBLIC_HOST || "0.0.0.0";
const ADMIN_API_BASE_URL = (process.env.ADMIN_API_BASE_URL || "http://admin-api:8100").replace(/\/$/, "");
const CONFIG_POLL_INTERVAL_SECONDS = Number(process.env.CONFIG_POLL_INTERVAL_SECONDS || 15);
const RUNTIME_ENV_PATH = process.env.RUNTIME_ENV_PATH || "/run/askai-secrets/runtime.env";
const TENANT_PORT_BASE = Number(process.env.TENANT_PORT_BASE || 19000);
const TENANT_PORT_SPAN = Number(process.env.TENANT_PORT_SPAN || 8000);

/** @type {Map<string, { configVersion: number, port: number, process: import('node:child_process').ChildProcess | null, gatewayKey: string }>} */
const tenants = new Map();
/** @type {Map<string, string>} */
const gatewayKeyToMainId = new Map();

/**
 * Load KEY=VALUE lines from bootstrap runtime.env.
 * @returns {Record<string, string>}
 */
function loadRuntimeEnvFile(path) {
  if (!fs.existsSync(path)) {
    return {};
  }
  const out = {};
  for (const line of fs.readFileSync(path, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf("=");
    if (idx <= 0) continue;
    out[trimmed.slice(0, idx)] = trimmed.slice(idx + 1);
  }
  return out;
}

/**
 * Resolve admin-api service token from env file or process env.
 * @returns {string}
 */
function resolveServiceToken() {
  const fromFile = loadRuntimeEnvFile(RUNTIME_ENV_PATH);
  return (
    process.env.ADMIN_BACKEND_SERVICE_TOKEN ||
    fromFile.ADMIN_BACKEND_SERVICE_TOKEN ||
    process.env.ASKAI_ADMIN_BACKEND_SERVICE_TOKEN ||
    fromFile.ASKAI_ADMIN_BACKEND_SERVICE_TOKEN ||
    ""
  ).trim();
}

/**
 * Stable local port for a tenant main id.
 * @param {string} mainId
 * @returns {number}
 */
function portForMainId(mainId) {
  const hash = crypto.createHash("sha256").update(mainId).digest();
  const offset = hash.readUInt32BE(0) % TENANT_PORT_SPAN;
  return TENANT_PORT_BASE + offset;
}

/**
 * @param {string} message
 */
function logInfo(message) {
  console.log(`[jira-mcp-gateway] ${message}`);
}

/**
 * @param {string} message
 */
function logError(message) {
  console.error(`[jira-mcp-gateway] ${message}`);
}

/**
 * Fetch tenant runtime configs from admin-api.
 * @param {string} serviceToken
 * @returns {Promise<{ globalVersion: number, tenants: Array<{ mainId: string, configVersion: number, jiraBaseUrl: string, personalAccessToken: string, gatewayKey: string }> }>}
 */
async function fetchRuntimeConfig(serviceToken) {
  const url = `${ADMIN_API_BASE_URL}/api/internal/jira-mcp-gateway/runtime-config`;
  const response = await fetch(url, {
    headers: { "X-MOVO-Service-Token": serviceToken },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`runtime-config HTTP ${response.status}: ${body.slice(0, 200)}`);
  }
  return response.json();
}

/**
 * Stop a tenant supergateway child if running.
 * @param {string} mainId
 */
function stopTenantProcess(mainId) {
  const entry = tenants.get(mainId);
  if (!entry?.process) return;
  try {
    entry.process.kill("SIGTERM");
  } catch {
    // ignore
  }
  entry.process = null;
}

/**
 * Start supergateway for one tenant on a dedicated localhost port.
 * @param {string} mainId
 * @param {{ configVersion: number, jiraBaseUrl: string, personalAccessToken: string, gatewayKey: string }} cfg
 */
function ensureTenantProcess(mainId, cfg) {
  const port = portForMainId(mainId);
  let entry = tenants.get(mainId);
  if (entry && entry.configVersion === cfg.configVersion && entry.process) {
    return;
  }
  if (entry) {
    stopTenantProcess(mainId);
  }
  const args = [
    "-y",
    "supergateway",
    "--stdio",
    "npx -y @parassolanki/jira-mcp-server@latest",
    "--outputTransport",
    "streamableHttp",
    "--stateful",
    "--sessionTimeout",
    "600000",
    "--protocolVersion",
    "2025-06-18",
    "--port",
    String(port),
    "--host",
    "127.0.0.1",
    "--apiKey",
    cfg.gatewayKey,
    "--healthEndpoint",
    "/healthz",
  ];
  const child = spawn("npx", args, {
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      JIRA_PERSONAL_ACCESS_TOKEN: cfg.personalAccessToken,
      JIRA_BASE_URL: cfg.jiraBaseUrl,
    },
  });
  child.stdout?.on("data", (chunk) => {
    logInfo(`[${mainId}] ${String(chunk).trim()}`);
  });
  child.stderr?.on("data", (chunk) => {
    logError(`[${mainId}] ${String(chunk).trim()}`);
  });
  child.on("exit", (code, signal) => {
    logInfo(`[${mainId}] supergateway exited code=${code} signal=${signal || ""}`);
    const current = tenants.get(mainId);
    if (current) {
      current.process = null;
    }
  });
  tenants.set(mainId, {
    configVersion: cfg.configVersion,
    port,
    process: child,
    gatewayKey: cfg.gatewayKey,
  });
  logInfo(`[${mainId}] started supergateway on 127.0.0.1:${port} configVersion=${cfg.configVersion}`);
}

/**
 * Rebuild gateway key index and reconcile tenant processes.
 * @param {{ globalVersion: number, tenants: Array<{ mainId: string, configVersion: number, jiraBaseUrl: string, personalAccessToken: string, gatewayKey: string }> }} payload
 */
function applyRuntimeConfig(payload) {
  gatewayKeyToMainId.clear();
  const seen = new Set();
  for (const item of payload.tenants || []) {
    const mainId = String(item.mainId || "").trim();
    if (!mainId) continue;
    seen.add(mainId);
    const gatewayKey = String(item.gatewayKey || "").trim();
    if (gatewayKey) {
      gatewayKeyToMainId.set(gatewayKey, mainId);
    }
    ensureTenantProcess(mainId, item);
  }
  for (const mainId of tenants.keys()) {
    if (!seen.has(mainId)) {
      stopTenantProcess(mainId);
      tenants.delete(mainId);
    }
  }
  logInfo(`runtime-config applied globalVersion=${payload.globalVersion || 0} tenants=${seen.size}`);
}

/**
 * Parse Bearer token from Authorization header.
 * @param {string | undefined} authorization
 * @returns {string}
 */
function parseBearerToken(authorization) {
  const raw = String(authorization || "").trim();
  if (!raw.toLowerCase().startsWith("bearer ")) return "";
  return raw.slice(7).trim();
}

/**
 * Constant-time string compare when lengths match.
 * @param {string} a
 * @param {string} b
 * @returns {boolean}
 */
function safeEqual(a, b) {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  if (left.length !== right.length) return false;
  return crypto.timingSafeEqual(left, right);
}

/**
 * Resolve tenant from request headers.
 * @param {import('node:http').IncomingMessage} req
 * @returns {{ mainId: string, port: number } | null}
 */
function resolveTenant(req) {
  const token = parseBearerToken(req.headers.authorization);
  if (!token) return null;
  const mainId = gatewayKeyToMainId.get(token);
  if (!mainId) return null;
  const entry = tenants.get(mainId);
  if (!entry || !entry.process) return null;
  if (!safeEqual(token, entry.gatewayKey)) return null;
  const headerMainId = String(req.headers["x-movo-main-id"] || req.headers["x-askai-main-id"] || "").trim();
  if (headerMainId && headerMainId !== mainId) {
    return { forbidden: true };
  }
  return { mainId, port: entry.port };
}

/**
 * Proxy HTTP request to tenant supergateway.
 * @param {import('node:http').IncomingMessage} req
 * @param {import('node:http').ServerResponse} res
 * @param {number} port
 */
function proxyRequest(req, res, port) {
  const targetPath = req.url || "/mcp";
  const headers = { ...req.headers, host: `127.0.0.1:${port}` };
  const upstream = http.request(
    {
      hostname: "127.0.0.1",
      port,
      path: targetPath,
      method: req.method,
      headers,
    },
    (upstreamRes) => {
      res.writeHead(upstreamRes.statusCode || 502, upstreamRes.headers);
      upstreamRes.pipe(res);
    },
  );
  upstream.on("error", (err) => {
    logError(`proxy error port=${port}: ${err.message}`);
    if (!res.headersSent) {
      res.writeHead(502, { "Content-Type": "text/plain" });
    }
    res.end("Bad Gateway");
  });
  req.pipe(upstream);
}

/**
 * Poll admin-api and refresh tenant processes.
 * @param {string} serviceToken
 */
async function pollConfigLoop(serviceToken) {
  for (;;) {
    try {
      const payload = await fetchRuntimeConfig(serviceToken);
      applyRuntimeConfig(payload);
    } catch (err) {
      logError(`config poll failed: ${err instanceof Error ? err.message : String(err)}`);
    }
    await new Promise((resolve) => setTimeout(resolve, CONFIG_POLL_INTERVAL_SECONDS * 1000));
  }
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
  if (req.method === "GET" && url.pathname === "/healthz") {
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("ok");
    return;
  }
  if (!url.pathname.startsWith("/mcp")) {
    res.writeHead(404, { "Content-Type": "text/plain" });
    res.end("Not Found");
    return;
  }
  const resolved = resolveTenant(req);
  if (!resolved) {
    res.writeHead(401, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "unauthorized" }));
    return;
  }
  if (resolved.forbidden) {
    res.writeHead(403, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "main_id_mismatch" }));
    return;
  }
  proxyRequest(req, res, resolved.port);
});

server.listen(PUBLIC_PORT, PUBLIC_HOST, () => {
  logInfo(`listening on ${PUBLIC_HOST}:${PUBLIC_PORT}`);
});

const serviceToken = resolveServiceToken();
if (!serviceToken) {
  logError("missing ADMIN_BACKEND_SERVICE_TOKEN; config poll will fail until secrets volume is mounted");
} else {
  pollConfigLoop(serviceToken).catch((err) => {
    logError(`poll loop crashed: ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  });
}
