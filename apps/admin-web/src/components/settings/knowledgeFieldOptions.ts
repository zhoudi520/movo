import type { ExternalToolItem } from '@/api/tools';
import type { KnowledgeSourceMapping } from '@/api/knowledge-source';
import { valueAt } from './knowledgeSourcePreview';

export type MappingKey = keyof KnowledgeSourceMapping;
export interface FieldOption { label: string; value: string }

type FieldType = 'string' | 'array' | 'object' | 'other' | 'unknown';
interface FieldCandidate { path: string; type: FieldType }

const documentKeys: MappingKey[] = ['titlePath', 'snippetPath', 'documentUrlPath'];

function declaredType(node: Record<string, any>): FieldType {
  const type = String(node.type || '').toLowerCase();
  if (type === 'string' || type === 'array' || type === 'object') return type;
  if (type) return 'other';
  if (node.properties) return 'object';
  if (node.items) return 'array';
  return 'unknown';
}

function schemaFields(schema: unknown, prefix = '', depth = 0): FieldCandidate[] {
  if (!schema || typeof schema !== 'object' || depth > 5) return [];
  const node = schema as Record<string, any>;
  const properties = node.properties && typeof node.properties === 'object' ? node.properties : {};
  const fields: FieldCandidate[] = Object.entries(properties).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return [{ path, type: declaredType((child || {}) as Record<string, any>) }, ...schemaFields(child, path, depth + 1)];
  });
  if (node.items) fields.push(...schemaFields(node.items, prefix, depth + 1));
  for (const variant of [...(node.oneOf || []), ...(node.anyOf || [])]) {
    fields.push(...schemaFields(variant, prefix, depth + 1));
  }
  return fields;
}

function treeFields(nodes: unknown, prefix = ''): FieldCandidate[] {
  if (!Array.isArray(nodes)) return [];
  return nodes.flatMap((node) => {
    const name = String(node?.name || '').trim();
    if (!name) return [];
    const isArrayItem = name === '[Array Item]';
    const path = isArrayItem ? prefix : prefix ? `${prefix}.${name}` : name;
    const children = treeFields(node.children, path);
    return isArrayItem ? children : [{ path, type: declaredType(node) }, ...children];
  });
}

function responseFields(value: unknown, prefix = '', depth = 0): FieldCandidate[] {
  if (depth > 5) return [];
  if (Array.isArray(value)) return value.length ? responseFields(value[0], prefix, depth + 1) : [];
  if (!value || typeof value !== 'object') return [];
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    const type: FieldType = typeof child === 'string' ? 'string' : Array.isArray(child) ? 'array'
      : child && typeof child === 'object' ? 'object' : child == null ? 'unknown' : 'other';
    return [{ path, type }, ...responseFields(child, path, depth + 1)];
  });
}

function reachableFields(fields: FieldCandidate[], allowedArrayPath = ''): FieldCandidate[] {
  const arrays = fields.filter((field) => field.type === 'array').map((field) => field.path);
  return fields.filter((field) => !arrays.some((path) => path !== allowedArrayPath && field.path.startsWith(`${path}.`)));
}

function outputFields(tool: ExternalToolItem | undefined, method: string, body: unknown): FieldCandidate[] {
  const discovered = tool?.discoveredTools.find((item) => item.name === method);
  const declared = tool?.type === 'mcp'
    ? schemaFields(discovered?.outputSchema, 'response')
    : treeFields(tool?.config?.outputSchema);
  const observed = responseFields(body).filter((field) => tool?.type !== 'mcp' || field.path.startsWith('response.'));
  const byPath = new Map<string, FieldCandidate>();
  for (const field of [...declared, ...observed]) {
    if (!/^[A-Za-z_][\w]*(?:\.(?:[A-Za-z_][\w]*|\d+))*$/.test(field.path)) continue;
    const previous = byPath.get(field.path);
    if (!previous || previous.type === 'unknown' && field.type !== 'unknown') byPath.set(field.path, field);
  }
  return [...byPath.values()];
}

export function mappingFieldOptions(tool: ExternalToolItem | undefined, method: string, body: unknown, sourcesPath: string, key: MappingKey): FieldOption[] {
  let fields = reachableFields(outputFields(tool, method, body), documentKeys.includes(key) ? sourcesPath : '');
  if (documentKeys.includes(key)) {
    const prefix = `${sourcesPath}.`;
    fields = fields.filter((field) => field.path.startsWith(prefix)).map((field) => ({ ...field, path: field.path.slice(prefix.length) }));
    const rows = valueAt(body, sourcesPath);
    if (Array.isArray(rows) && rows.length) fields.push(...reachableFields(responseFields(rows[0])));
  }
  const expectedType = key === 'sourcesPath' ? 'array' : 'string';
  return [...new Set(fields
    .filter((field) => field.type === expectedType || field.type === 'unknown' && expectedType === 'string')
    .map((field) => field.path)
    .filter((path) => /^[A-Za-z_][\w]*(?:\.(?:[A-Za-z_][\w]*|\d+))*$/.test(path)))]
    .map((value) => ({ label: value, value }));
}
