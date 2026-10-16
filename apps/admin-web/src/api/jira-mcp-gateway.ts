import { apiClient } from './client';

export type McpEndpointPreset = 'docker_internal' | 'host_loopback';

export interface JiraMcpGatewaySettings {
  mainId: string;
  enabled: boolean;
  jiraBaseUrl: string;
  personalAccessToken: string;
  gatewayKeyMasked: string;
  configVersion: number;
  mcpToolEndpointPreset: McpEndpointPreset;
  linkedToolId: string;
  resolvedMcpEndpoint: string;
  updatedAt: string;
  endpointPresets?: Record<McpEndpointPreset, string>;
}

export interface JiraMcpGatewaySavePayload {
  enabled: boolean;
  jiraBaseUrl: string;
  personalAccessToken: string;
  gatewayKey: string;
  mcpToolEndpointPreset: McpEndpointPreset;
}

export async function fetchJiraMcpGatewaySettings(): Promise<JiraMcpGatewaySettings> {
  const { data } = await apiClient.get<JiraMcpGatewaySettings>('/api/settings/jira-mcp-gateway');
  return data;
}

export async function saveJiraMcpGatewaySettings(payload: JiraMcpGatewaySavePayload): Promise<JiraMcpGatewaySettings> {
  const { data } = await apiClient.put<JiraMcpGatewaySettings>('/api/settings/jira-mcp-gateway', payload);
  return data;
}

export async function testJiraMcpGatewayJira(payload: { jiraBaseUrl?: string; personalAccessToken?: string }) {
  const { data } = await apiClient.post<Record<string, unknown>>('/api/settings/jira-mcp-gateway/test-jira', payload);
  return data;
}

export async function testJiraMcpGatewayMcp(payload: { gatewayKey?: string; mainId?: string } = {}) {
  const { data } = await apiClient.post<Record<string, unknown>>('/api/settings/jira-mcp-gateway/test-mcp', payload);
  return data;
}
