import {
  expandReportMatchPayload,
  type ReportMatchItem,
  reportMatchKey,
} from '../features/chat/reportMatch'

export interface SplitAssistantReportMatchesResult {
  displayContent: string
  items: ReportMatchItem[]
}

export type AssistantContentSegment =
  | { kind: 'text'; content: string }
  | { kind: 'reports'; items: ReportMatchItem[] }

interface ReportMatchRegion {
  start: number
  end: number
  items: ReportMatchItem[]
}

const FENCE_PATTERN = /```(?:movo-report-match|json)\s*\n([\s\S]*?)```/gi

function mergeItems(existing: ReportMatchItem[], incoming: ReportMatchItem[]): ReportMatchItem[] {
  const map = new Map<string, ReportMatchItem>()
  for (const item of [...existing, ...incoming]) {
    map.set(item.key || reportMatchKey(item.functionId, item.menuPath), item)
  }
  return [...map.values()]
}

function tryParseJson(text: string): unknown | null {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function looksLikeReportMatchObject(parsed: unknown): boolean {
  if (!parsed || typeof parsed !== 'object') return false
  if (Array.isArray(parsed)) {
    return parsed.some((entry) => looksLikeReportMatchObject(entry))
  }
  const obj = parsed as Record<string, unknown>
  if (Array.isArray(obj.items)) return looksLikeReportMatchObject(obj.items)
  const menuPath = String(obj.menuPath || '').trim()
  if (!menuPath) return false
  const param = obj.param && typeof obj.param === 'object' ? (obj.param as Record<string, unknown>) : null
  const functionId = String(param?.functionId || obj.functionId || '').trim()
  return Boolean(functionId || menuPath.includes('\\') || menuPath.includes('/'))
}

function collapseBlankLines(text: string): string {
  return text
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]+\n/g, '\n')
    .trim()
}

function indexInsideRegion(index: number, regions: ReportMatchRegion[]): boolean {
  return regions.some((region) => index >= region.start && index < region.end)
}

function findFencedRegions(content: string): ReportMatchRegion[] {
  const regions: ReportMatchRegion[] = []
  const pattern = new RegExp(FENCE_PATTERN.source, FENCE_PATTERN.flags)
  let match = pattern.exec(content)
  while (match) {
    const parsed = tryParseJson(String(match[1] || '').trim())
    if (parsed && looksLikeReportMatchObject(parsed)) {
      const found = expandReportMatchPayload(parsed)
      if (found.length) {
        regions.push({
          start: match.index,
          end: match.index + match[0].length,
          items: found,
        })
      }
    }
    match = pattern.exec(content)
  }
  return regions
}

function findWholeDocumentRegion(content: string): ReportMatchRegion | null {
  const trimmed = content.trim()
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return null
  const parsed = tryParseJson(trimmed)
  if (!parsed || !looksLikeReportMatchObject(parsed)) return null
  const found = expandReportMatchPayload(parsed)
  if (!found.length) return null
  const start = content.indexOf(trimmed)
  if (start < 0) return null
  return { start, end: start + trimmed.length, items: found }
}

function findInlineJsonRegions(content: string, skipRegions: ReportMatchRegion[]): ReportMatchRegion[] {
  const regions: ReportMatchRegion[] = []

  for (let index = 0; index < content.length; index += 1) {
    if (content[index] !== '{' || indexInsideRegion(index, skipRegions)) continue
    let depth = 0
    let inString = false
    let escaped = false
    for (let cursor = index; cursor < content.length; cursor += 1) {
      const ch = content[cursor]
      if (inString) {
        if (escaped) escaped = false
        else if (ch === '\\') escaped = true
        else if (ch === '"') inString = false
        continue
      }
      if (ch === '"') {
        inString = true
        continue
      }
      if (ch === '{') depth += 1
      if (ch === '}') {
        depth -= 1
        if (depth === 0) {
          const end = cursor + 1
          if (!indexInsideRegion(index, skipRegions)) {
            const slice = content.slice(index, end)
            const parsed = tryParseJson(slice)
            if (parsed && looksLikeReportMatchObject(parsed)) {
              const found = expandReportMatchPayload(parsed)
              if (found.length) {
                regions.push({ start: index, end, items: found })
              }
            }
          }
          index = cursor
          break
        }
      }
    }
  }

  return regions
}

function mergeNonOverlappingRegions(regions: ReportMatchRegion[]): ReportMatchRegion[] {
  const sorted = [...regions].sort((a, b) => a.start - b.start || a.end - b.end)
  const merged: ReportMatchRegion[] = []
  for (const region of sorted) {
    const last = merged[merged.length - 1]
    if (last && region.start < last.end) continue
    merged.push(region)
  }
  return merged
}

function collectReportRegions(content: string): ReportMatchRegion[] {
  const fenced = findFencedRegions(content)
  let regions: ReportMatchRegion[] = [...fenced]
  if (!regions.length) {
    const whole = findWholeDocumentRegion(content)
    if (whole) regions = [whole]
    else regions = findInlineJsonRegions(content, [])
  } else {
    regions = [...regions, ...findInlineJsonRegions(content, fenced)]
  }
  return mergeNonOverlappingRegions(regions)
}

/**
 * One assistant message renders at most one report card; all matches become rows inside it.
 */
function buildSingleReportCardSegments(content: string, regions: ReportMatchRegion[]): AssistantContentSegment[] {
  let allItems: ReportMatchItem[] = []
  for (const region of regions) {
    allItems = mergeItems(allItems, region.items)
  }
  if (!allItems.length) {
    return [{ kind: 'text', content }]
  }

  const first = regions[0]
  const last = regions[regions.length - 1]
  const before = collapseBlankLines(content.slice(0, first.start))
  const after = collapseBlankLines(content.slice(last.end))

  const segments: AssistantContentSegment[] = []
  if (before) segments.push({ kind: 'text', content: before })
  segments.push({ kind: 'reports', items: allItems })
  if (after) segments.push({ kind: 'text', content: after })
  return segments
}

/**
 * Split assistant content into ordered text and report-card segments.
 */
export function splitAssistantReportSegments(content: string): AssistantContentSegment[] {
  if (!content || !content.trim()) {
    return content ? [{ kind: 'text', content }] : []
  }

  const regions = collectReportRegions(content)
  if (!regions.length) {
    return [{ kind: 'text', content }]
  }

  return buildSingleReportCardSegments(content, regions)
}

/**
 * Split assistant content into user-visible prose and normalized report match cards.
 */
export function splitAssistantReportMatches(content: string): SplitAssistantReportMatchesResult {
  const segments = splitAssistantReportSegments(content)
  const textParts = segments.filter((segment): segment is { kind: 'text'; content: string } => segment.kind === 'text')
  const items = segments
    .filter((segment): segment is { kind: 'reports'; items: ReportMatchItem[] } => segment.kind === 'reports')
    .flatMap((segment) => segment.items)
  return {
    displayContent: collapseBlankLines(textParts.map((segment) => segment.content).join('\n\n')),
    items: mergeItems([], items),
  }
}

/**
 * Return true when content contains a complete, parseable report-match payload.
 */
export function hasCompleteReportMatches(content: string): boolean {
  return splitAssistantReportSegments(content).some(
    (segment) => segment.kind === 'reports' && segment.items.length > 0,
  )
}
