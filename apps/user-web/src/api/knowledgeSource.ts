import { createApiClient } from './client'

const client = createApiClient({ baseURL: '/askai-api', timeout: 10000 })

export interface KnowledgeSourceSummary {
  mode: 'movo' | 'external'
  displayName: string
}

export async function fetchKnowledgeSourceSummary(): Promise<KnowledgeSourceSummary> {
  const { data } = await client.get<KnowledgeSourceSummary>('/api/knowledge/source/current')
  return data
}
