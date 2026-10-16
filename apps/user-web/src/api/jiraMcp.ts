import { createApiClient } from './client'

const api = createApiClient({
  baseURL: '/askai-api/api',
  timeout: 120000,
})

export interface JiraMcpToolConnection {
  enabled: boolean
  toolName: string
  endpoint: string
  authType: 'bearer' | string
  authToken: string
  authTokenMasked: string
  mcpToolEndpointPreset: string
}

export interface JiraMcpUserSettings {
  mainId: string
  userId: string
  configured: boolean
  jiraBaseUrl: string
  personalAccessToken: string
  personalAccessTokenMasked?: string
  configVersion: number
  updatedAt: string
  mcpTool?: JiraMcpToolConnection
}

export interface JiraMcpUserSavePayload {
  jiraBaseUrl: string
  personalAccessToken: string
  validateJira?: boolean
}

interface ApiEnvelope<T> {
  code: number
  message?: string
  data: T
}

export async function fetchMyJiraMcpSettings(): Promise<JiraMcpUserSettings> {
  const { data } = await api.get<ApiEnvelope<JiraMcpUserSettings>>('/jira-mcp/my')
  return data.data
}

export async function saveMyJiraMcpSettings(payload: JiraMcpUserSavePayload): Promise<JiraMcpUserSettings> {
  const { data } = await api.put<ApiEnvelope<JiraMcpUserSettings>>('/jira-mcp/my', payload)
  return data.data
}

export async function deleteMyJiraMcpSettings(): Promise<JiraMcpUserSettings> {
  const { data } = await api.delete<ApiEnvelope<JiraMcpUserSettings>>('/jira-mcp/my')
  return data.data
}
