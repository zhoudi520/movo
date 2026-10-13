/** Normalized G3-style report match entries extracted from assistant content. */

export interface LocalizedName {
  CHS?: string
  CHT?: string
  EN?: string
}

export interface ReportMatchItem {
  key: string
  functionId: string
  menuPath: string
  name: LocalizedName
}

const FUNCTION_ID_PATTERN = /^[A-Z0-9_]+$/
const MAX_MENU_PATH_LENGTH = 512

/**
 * Pick a display title from localized name fields for the active UI locale.
 */
export function pickReportMatchTitle(name: LocalizedName, locale: string): string {
  const lang = String(locale || '').toLowerCase()
  const candidates = lang.startsWith('en')
    ? [name.EN, name.CHS, name.CHT]
    : lang.includes('tw') || lang.includes('hk') || lang === 'cht'
      ? [name.CHT, name.CHS, name.EN]
      : [name.CHS, name.CHT, name.EN]
  for (const value of candidates) {
    const text = String(value || '').trim()
    if (text) return text
  }
  return ''
}

/**
 * Build a stable dedupe key for favorites and list merging.
 */
export function reportMatchKey(functionId: string, menuPath: string): string {
  return `${functionId}|${menuPath}`
}

/**
 * Parse param.name when it is a JSON string or plain object.
 */
export function parseLocalizedName(raw: unknown): LocalizedName {
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    const obj = raw as Record<string, unknown>
    return {
      CHS: obj.CHS != null ? String(obj.CHS) : undefined,
      CHT: obj.CHT != null ? String(obj.CHT) : undefined,
      EN: obj.EN != null ? String(obj.EN) : undefined,
    }
  }
  if (typeof raw === 'string') {
    const trimmed = raw.trim()
    if (!trimmed) return {}
    try {
      return parseLocalizedName(JSON.parse(trimmed))
    } catch {
      return { EN: trimmed }
    }
  }
  return {}
}

function inferFunctionIdFromMenuPath(menuPath: string): string {
  const normalized = menuPath.replace(/\\/g, '/').replace(/\/+$/, '')
  const segment = normalized.split('/').filter(Boolean).pop() || ''
  return segment.trim()
}

function isUnsafeMenuPath(menuPath: string): boolean {
  const lower = menuPath.toLowerCase()
  return lower.includes('<script') || menuPath.length > MAX_MENU_PATH_LENGTH
}

/**
 * Normalize one raw JSON object into a ReportMatchItem, or null if invalid.
 */
export function normalizeReportMatchRecord(raw: unknown): ReportMatchItem | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const record = raw as Record<string, unknown>
  const menuPath = String(record.menuPath || '').trim()
  if (!menuPath || isUnsafeMenuPath(menuPath)) return null

  const param = record.param && typeof record.param === 'object' && !Array.isArray(record.param)
    ? (record.param as Record<string, unknown>)
    : {}
  let functionId = String(param.functionId || record.functionId || '').trim()
  if (!functionId) functionId = inferFunctionIdFromMenuPath(menuPath)
  if (!functionId || !FUNCTION_ID_PATTERN.test(functionId)) return null

  const name = parseLocalizedName(param.name ?? record.name)
  return {
    key: reportMatchKey(functionId, menuPath),
    functionId,
    menuPath,
    name,
  }
}

/**
 * Expand a parsed JSON value into zero or more report match items.
 */
export function expandReportMatchPayload(parsed: unknown): ReportMatchItem[] {
  if (Array.isArray(parsed)) {
    return parsed.map((entry) => normalizeReportMatchRecord(entry)).filter(Boolean) as ReportMatchItem[]
  }
  if (parsed && typeof parsed === 'object') {
    const obj = parsed as Record<string, unknown>
    if (Array.isArray(obj.items)) {
      return expandReportMatchPayload(obj.items)
    }
    const one = normalizeReportMatchRecord(parsed)
    return one ? [one] : []
  }
  return []
}
