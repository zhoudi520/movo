#!/usr/bin/env node
/**
 * Tenant-aware HTTP front for supergateway + parassolanki Jira MCP.
 * Routes by X-MOVO-Main-ID and X-MOVO-User-ID; injects internal Bearer only toward local supergateway.
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
const EFFECTIVE_CONFIG_CACHE_TTL_MS = Number(process.env.EFFECTIVE_CONFIG_CACHE_TTL_MS || 45000);
const MAX_SUBPROCESSES = Number(process.env.MAX_SUBPROCESSES || 32);
const SUBPROCESS_IDLE_MS = Number(process.env.SUBPROCESS_IDLE_MS || 30 * 60 * 1000);

/** @type {Set<string>} */
const enabledMainIds = new Set();
/** @type {Map<string, string>} */
const gatewayKeyToMainId = new Map();

/**
 * @typedef {Object} SubprocessEntry
 * @property {number} configVersion
 * @property {number} port
 * @property {import('node:child_process').ChildProcess | null} process
 * @property {string} gatewayKey
 * @property {number} lastUsedAt
 */

/** @type {Map<string, SubprocessEntry>} */
const subprocesses = new Map();

/** @type {Map<string, { expiresAt: number, cfg: object }>} */
const effectiveConfigCache = new Map();

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
 * Stable local port for a subprocess cache key.
 * @param {string} cacheKey
 * @returns {number}
 */
function portForCacheKey(cacheKey) {
  const hash = crypto.createHash("sha256").update(cacheKey).digest();
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
 * Fetch tenant runtime configs from admin-api (gateway keys only).
 * @param {string} serviceToken
 * @returns {Promise<{ globalVersion: number, tenants: Array<{ mainId: string, gatewayKey: string }> }>}
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
 * Fetch effective Jira credentials for one tenant user.
 * @param {string} serviceToken
 * @param {string} mainId
 * @param {string} userId
 * @returns {Promise<{ jiraBaseUrl: string, personalAccessToken: string, configVersion: number, gatewayKey: string }>}
 */
async function fetchEffectiveConfig(serviceToken, mainId, userId) {
  const cacheKey = `${mainId}:${userId}`;
  const cached = effectiveConfigCache.get(cacheKey);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.cfg;
  }
  const params = new URLSearchParams({ mainId, userId });
  const url = `${ADMIN_API_BASE_URL}/api/internal/jira-mcp-gateway/effective-config?${params}`;
  const response = await fetch(url, {
    headers: { "X-MOVO-Service-Token": serviceToken },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`effective-config HTTP ${response.status}: ${body.slice(0, 300)}`);
  }
  const cfg = await response.json();
  effectiveConfigCache.set(cacheKey, { expiresAt: Date.now() + EFFECTIVE_CONFIG_CACHE_TTL_MS, cfg });
  return cfg;
}

/**
 * Stop a supergateway child if running.
 * @param {string} cacheKey
 */
function stopSubprocess(cacheKey) {
  const entry = subprocesses.get(cacheKey);
  if (!entry?.process) return;
  try {
    entry.process.kill("SIGTERM");
  } catch {
    // ignore
  }
  entry.process = null;
}

/**
 * Evict least-recently-used subprocess when at capacity.
 */
function evictIfNeeded() {
  if (subprocesses.size < MAX_SUBPROCESSES) return;
  let oldestKey = "";
  let oldestUsed = Infinity;
  for (const [key, entry] of subprocesses) {
    if (entry.lastUsedAt < oldestUsed) {
      oldestUsed = entry.lastUsedAt;
      oldestKey = key;
    }
  }
  if (oldestKey) {
    stopSubprocess(oldestKey);
    subprocesses.delete(oldestKey);
    logInfo(`evicted subprocess ${oldestKey}`);
  }
}

/**
 * Start supergateway for one cache key on a dedicated localhost port.
 * @param {string} cacheKey
 * @param {{ configVersion: number, jiraBaseUrl: string, personalAccessToken: string, gatewayKey: string }} cfg
 */
function ensureSubprocess(cacheKey, cfg) {
  const port = portForCacheKey(cacheKey);
  let entry = subprocesses.get(cacheKey);
  if (entry && entry.configVersion === cfg.configVersion && entry.process) {
    entry.lastUsedAt = Date.now();
    return;
  }
  if (entry) {
    stopSubprocess(cacheKey);
  } else {
    evictIfNeeded();
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
    logInfo(`[${cacheKey}] ${String(chunk).trim()}`);
  });
  child.stderr?.on("data", (chunk) => {
    logError(`[${cacheKey}] ${String(chunk).trim()}`);
  });
  child.on("exit", (code, signal) => {
    logInfo(`[${cacheKey}] supergateway exited code=${code} signal=${signal || ""}`);
    const current = subprocesses.get(cacheKey);
    if (current) {
      current.process = null;
    }
  });
  subprocesses.set(cacheKey, {
    configVersion: cfg.configVersion,
    port,
    process: child,
    gatewayKey: cfg.gatewayKey,
    lastUsedAt: Date.now(),
  });
  logInfo(`[${cacheKey}] started supergateway on 127.0.0.1:${port} configVersion=${cfg.configVersion}`);
}

/**
 * Rebuild gateway key index from tenant runtime config (no subprocess spawn).
 * @param {{ globalVersion: number, tenants: Array<{ mainId: string, gatewayKey: string }> }} payload
 */
function applyRuntimeConfig(payload) {
  enabledMainIds.clear();
  gatewayKeyToMainId.clear();
  for (const item of payload.tenants || []) {
    const mainId = String(item.mainId || "").trim();
    if (!mainId) continue;
    enabledMainIds.add(mainId);
    const gatewayKey = String(item.gatewayKey || "").trim();
    if (gatewayKey) {
      gatewayKeyToMainId.set(gatewayKey, mainId);
    }
  }
  for (const cacheKey of subprocesses.keys()) {
    const mainId = cacheKey.split(":")[0];
    if (!enabledMainIds.has(mainId)) {
      stopSubprocess(cacheKey);
      subprocesses.delete(cacheKey);
    }
  }
  logInfo(`runtime-config applied globalVersion=${payload.globalVersion || 0} tenants=${enabledMainIds.size}`);
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
 * Refresh enabled tenant ids from admin-api.
 * @param {string} serviceToken
 */
async function refreshRuntimeConfig(serviceToken) {
  const payload = await fetchRuntimeConfig(serviceToken);
  applyRuntimeConfig(payload);
}

/**
 * Resolve tenant main id from MOVO tenant header (no public Bearer required).
 * @param {import('node:http').IncomingMessage} req
 * @returns {{ mainId: string } | { forbidden: true } | { missingHeader: true } | { unknownMainId: string }}
 */
function resolveMainIdFromRequest(req) {
  const headerMainId = String(req.headers["x-movo-main-id"] || req.headers["x-askai-main-id"] || "").trim();
  if (!headerMainId) {
    return { missingHeader: true };
  }
  if (!enabledMainIds.has(headerMainId)) {
    return { unknownMainId: headerMainId };
  }
  const token = parseBearerToken(req.headers.authorization);
  if (token) {
    const bearerMainId = gatewayKeyToMainId.get(token);
    if (bearerMainId && bearerMainId !== headerMainId) {
      return { forbidden: true };
    }
  }
  return { mainId: headerMainId };
}

/**
 * Proxy HTTP request to tenant supergateway.
 * @param {import('node:http').IncomingMessage} req
 * @param {import('node:http').ServerResponse} res
 * @param {number} port
 */
function proxyRequest(req, res, port, internalApiKey) {
  const targetPath = req.url || "/mcp";
  const headers = { ...req.headers, host: `127.0.0.1:${port}` };
  if (internalApiKey) {
    headers.authorization = `Bearer ${internalApiKey}`;
  }
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
 * Poll admin-api and refresh gateway key index.
 * @param {string} serviceToken
 */
async function pollConfigLoop(serviceToken) {
  for (;;) {
    try {
      await refreshRuntimeConfig(serviceToken);
    } catch (err) {
      logError(`config poll failed: ${err instanceof Error ? err.message : String(err)}`);
    }
    await new Promise((resolve) => setTimeout(resolve, CONFIG_POLL_INTERVAL_SECONDS * 1000));
  }
}

/**
 * Stop idle subprocesses periodically.
 */
function idleSweepLoop() {
  setInterval(() => {
    const now = Date.now();
    for (const [cacheKey, entry] of subprocesses) {
      if (entry.process && now - entry.lastUsedAt > SUBPROCESS_IDLE_MS) {
        stopSubprocess(cacheKey);
        subprocesses.delete(cacheKey);
        logInfo(`idle stop ${cacheKey}`);
      }
    }
  }, Math.min(SUBPROCESS_IDLE_MS, 60_000));
}

const serviceToken = resolveServiceToken();

const server = http.createServer(async (req, res) => {
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

  let resolved = resolveMainIdFromRequest(req);
  if (resolved.unknownMainId && serviceToken) {
    try {
      await refreshRuntimeConfig(serviceToken);
      resolved = resolveMainIdFromRequest(req);
    } catch (err) {
      logError(`runtime refresh failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
  if (resolved.missingHeader) {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "missing_main_id_header", detail: "需要 X-MOVO-Main-ID" }));
    return;
  }
  if (resolved.unknownMainId) {
    logError(`unknown main_id=${resolved.unknownMainId} enabled=${[...enabledMainIds].join(",")}`);
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "unknown_main_id", mainId: resolved.unknownMainId }));
    return;
  }
  if (resolved.forbidden) {
    res.writeHead(403, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "main_id_mismatch" }));
    return;
  }

  if (!serviceToken) {
    res.writeHead(503, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "gateway_misconfigured" }));
    return;
  }

  const userIdRaw = String(req.headers["x-movo-user-id"] || "").trim();
  const userId = userIdRaw || "__default__";
  const cacheKey = `${resolved.mainId}:${userId}`;

  try {
    const cfg = await fetchEffectiveConfig(serviceToken, resolved.mainId, userId);
    ensureSubprocess(cacheKey, cfg);
    const entry = subprocesses.get(cacheKey);
    if (!entry?.process) {
      res.writeHead(503, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "subprocess_unavailable" }));
      return;
    }
    entry.lastUsedAt = Date.now();
    proxyRequest(req, res, entry.port, String(cfg.gatewayKey || entry.gatewayKey || ""));
  } catch (err) {
    logError(`resolve failed mainId=${resolved.mainId} userId=${userId}: ${err instanceof Error ? err.message : String(err)}`);
    res.writeHead(503, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "jira_config_unavailable", detail: String(err instanceof Error ? err.message : err).slice(0, 200) }));
  }
});

server.listen(PUBLIC_PORT, PUBLIC_HOST, () => {
  logInfo(`listening on ${PUBLIC_HOST}:${PUBLIC_PORT}`);
});

idleSweepLoop();

if (!serviceToken) {
  logError("missing ADMIN_BACKEND_SERVICE_TOKEN; config poll will fail until secrets volume is mounted");
} else {
  pollConfigLoop(serviceToken).catch((err) => {
    logError(`poll loop crashed: ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  });
}
