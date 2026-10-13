import type { ExternalToolItem } from '@/api/tools';

export interface InputOption { label: string; value: string; location?: 'query' | 'body' | 'headers' | 'path' }

const validName = (name: string) => /^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(name);
const isText = (type: unknown) => typeof type === 'string' && type.toLowerCase() === 'string'
  || Array.isArray(type) && type.some((item) => typeof item === 'string' && item.toLowerCase() === 'string');

export function mcpQuestionInputOptions(tool: ExternalToolItem | undefined, method: string): InputOption[] {
  const schema = tool?.discoveredTools.find((item) => item.name === method)?.inputSchema;
  const properties = schema?.properties;
  if (!properties || typeof properties !== 'object' || Array.isArray(properties)) return [];
  return Object.entries(properties)
    .filter(([name, definition]) => {
      if (!validName(name) || !definition || typeof definition !== 'object') return false;
      const type = (definition as Record<string, unknown>).type;
      return isText(type);
    })
    .map(([name, definition]) => {
      const description = String((definition as Record<string, unknown>).description || '').trim();
      return { label: description ? `${name} · ${description}` : name, value: name };
    });
}

export function httpQuestionInputOptions(tool: ExternalToolItem | undefined): InputOption[] {
  const nodes = tool?.config?.inputSchema;
  if (!Array.isArray(nodes)) return [];
  const found: InputOption[] = [];
  const visit = (items: unknown[]) => {
    for (const item of items) {
      if (!item || typeof item !== 'object') continue;
      const node = item as Record<string, unknown>;
      const name = String(node.name || '').trim();
      if (validName(name) && isText(node.type)) {
        const rawLocation = String(node.location || 'Query').toLowerCase();
        const location = rawLocation === 'header' ? 'headers' : rawLocation === 'path' ? 'path'
          : rawLocation === 'body' ? 'body' : 'query';
        const description = String(node.description || '').trim();
        found.push({ label: `${name} · ${rawLocation}${description ? ` · ${description}` : ''}`, value: name, location });
      }
      if (Array.isArray(node.children)) visit(node.children);
    }
  };
  visit(nodes);
  const counts = new Map<string, number>();
  for (const item of found) counts.set(item.value, (counts.get(item.value) || 0) + 1);
  return found.filter((item) => counts.get(item.value) === 1);
}

export function questionInputOptions(tool: ExternalToolItem | undefined, method: string): InputOption[] {
  return tool?.type === 'mcp' ? mcpQuestionInputOptions(tool, method) : httpQuestionInputOptions(tool);
}

export function selectedQuestionInput(current: string, options: InputOption[]): string {
  if (options.some((option) => option.value === current)) return current;
  return options.length === 1 ? options[0].value : '';
}
