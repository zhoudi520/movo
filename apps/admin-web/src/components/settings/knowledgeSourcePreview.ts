import type { KnowledgeSourceSettings } from '@/api/knowledge-source';

export function valueAt(value: unknown, path: string): unknown {
  if (!path.trim()) return undefined;
  return path.split('.').reduce<unknown>((current, segment) => {
    if (Array.isArray(current) && /^\d+$/.test(segment)) return current[Number(segment)];
    if (current && typeof current === 'object') return (current as Record<string, unknown>)[segment];
    return undefined;
  }, value);
}

export function responseBody(outcome: Record<string, any>): unknown {
  const raw = outcome.raw;
  if (raw?.structuredContent && typeof raw.structuredContent === 'object') return { ...raw, response: raw.structuredContent };
  if (Array.isArray(raw?.content)) {
    for (const block of raw.content) {
      if (block?.type !== 'text') continue;
      try { return { ...raw, response: JSON.parse(String(block.text || '')) }; } catch { /* inspect next block */ }
    }
  }
  return raw;
}

export function previewKnowledgeResult(outcome: Record<string, any>, settings: KnowledgeSourceSettings) {
  const body = responseBody(outcome);
  const fields = settings.mapping;
  const answer = valueAt(body, fields.answerPath);
  const sourceRows = valueAt(body, fields.sourcesPath);
  const sources = Array.isArray(sourceRows) ? sourceRows.slice(0, 20).filter((row) => row && typeof row === 'object').map((row) => ({
    title: String(valueAt(row, fields.titlePath) || ''),
    documentUrl: String(valueAt(row, fields.documentUrlPath) || ''),
    snippet: String(valueAt(row, fields.snippetPath) || ''),
  })) : [];
  return { answer: typeof answer === 'string' ? answer.trim() : '', sources, body };
}
