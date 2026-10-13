import { apiClient } from './client';

export interface KnowledgeSourceMapping {
  answerPath: string;
  sourcesPath: string;
  titlePath: string;
  documentUrlPath: string;
  snippetPath: string;
}

export interface KnowledgeSourceSettings {
  mode: 'movo' | 'external';
  displayName: string;
  toolId: string;
  mcpToolName: string;
  queryArgument: string;
  mapping: KnowledgeSourceMapping;
}

export async function fetchKnowledgeSource(): Promise<KnowledgeSourceSettings> {
  const { data } = await apiClient.get<KnowledgeSourceSettings>('/api/settings/knowledge/source');
  return data;
}

export async function saveKnowledgeSource(payload: KnowledgeSourceSettings): Promise<KnowledgeSourceSettings> {
  const { data } = await apiClient.put<KnowledgeSourceSettings>('/api/settings/knowledge/source', payload);
  return data;
}
