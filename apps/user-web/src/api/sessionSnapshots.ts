import { createApiClient } from './client'
import { installAuthExpiryInterceptor } from './authExpiry'

const api = createApiClient({ baseURL: '/askai-api/api', timeout: 120000 })
installAuthExpiryInterceptor(api)

export interface SessionSnapshot {
  title: string
  created_at: string
  expires_at: string
  messages: Array<{ role: 'user' | 'assistant'; content: string; created_at?: string; author_name?: string }>
}

export async function createSessionSnapshot(sessionId: string, expiresInDays: number): Promise<{ id: string; url: string; expires_at: string }> {
  const response = await api.post(`/sessions/${sessionId}/snapshot-share`, { expiresInDays })
  return response.data.data
}

export async function readSessionSnapshot(token: string): Promise<SessionSnapshot> {
  const response = await api.get(`/session-snapshots/${encodeURIComponent(token)}`)
  return response.data.data
}

export async function revokeSessionSnapshot(id: string): Promise<void> {
  await api.delete(`/session-snapshots/${id}`)
}
