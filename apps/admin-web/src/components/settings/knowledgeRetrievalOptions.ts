import type { ExternalToolItem } from '@/api/tools';

export interface RetrievalOption {
  label: string;
  value: string;
  toolId: string;
  mcpToolName: string;
}

export function retrievalOptions(tools: ExternalToolItem[]): RetrievalOption[] {
  return tools.filter((tool) => tool.status === 'active').flatMap((tool) => {
    if (tool.type === 'http') {
      return [{ label: `${tool.name} (HTTP)`, value: JSON.stringify([tool.id, '']), toolId: tool.id, mcpToolName: '' }];
    }
    const enabled = new Set(tool.config?.enabledToolNames || []);
    return tool.discoveredTools.filter((method) => enabled.has(method.name)).map((method) => ({
      label: `${method.name} · ${tool.name} (MCP)`,
      value: JSON.stringify([tool.id, method.name]),
      toolId: tool.id,
      mcpToolName: method.name,
    }));
  });
}
