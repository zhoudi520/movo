import { notifyAuthExpiredFromResponse } from './authExpiry'

export interface KnowledgeSourceDocument {
  id: string
  scope: string
  name: string
  originalFilename: string
  fileExt: string
  mimeType: string
  previewMimeType: string
  previewStatus: string
  chunkCount: number
  canDownload?: boolean
  learningMode?: string
}

export interface KnowledgeSourceChunk {
  id: string
  documentId: string
  chunkId: string
  chunkStage: string
  ordinal: number
  text: string
  contextualText: string
  titlePath: string[]
  pageNo: number | string | null
  contentType: string
  sourceChunkIds: string[]
  metadata: Record<string, any>
}

export function knowledgeSourceAuthHeaders(token?: string | null): Record<string, string> {
  const resolved = token ?? (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : '')
  return resolved ? { Authorization: `Bearer ${resolved}` } : {}
}

async function readJson<T>(url: string, token?: string | null): Promise<T> {
  const resp = await fetch(url, { headers: knowledgeSourceAuthHeaders(token) })
  notifyAuthExpiredFromResponse(resp, Boolean(token))
  if (!resp.ok) throw new Error(`Request failed: ${resp.status}`)
  return resp.json() as Promise<T>
}

export function knowledgeSourcePreviewUrl(documentId: string): string {
  return `/askai-api/api/knowledge/sources/documents/${encodeURIComponent(documentId)}/preview`
}

export async function fetchKnowledgeSourceDocument(documentId: string, token?: string | null) {
  return readJson<KnowledgeSourceDocument>(
    `/askai-api/api/knowledge/sources/documents/${encodeURIComponent(documentId)}`,
    token,
  )
}

export async function fetchKnowledgeSourceChunk(documentId: string, chunkId: string, token?: string | null) {
  return readJson<KnowledgeSourceChunk>(
    `/askai-api/api/knowledge/sources/documents/${encodeURIComponent(documentId)}/chunks/${encodeURIComponent(chunkId)}`,
    token,
  )
}

export async function fetchKnowledgeSourcePreview(documentId: string, token?: string | null) {
  const resp = await fetch(knowledgeSourcePreviewUrl(documentId), { headers: knowledgeSourceAuthHeaders(token) })
  notifyAuthExpiredFromResponse(resp, Boolean(token))
  if (!resp.ok) throw new Error(`Request failed: ${resp.status}`)
  return resp.blob()
}

/** Append access_token query for img tags that cannot send Authorization headers. */
export function withKnowledgeArtifactAccess(url: string, token?: string | null): string {
  const raw = String(url || '').trim()
  if (!raw.includes('/knowledge/sources/documents/') || !raw.includes('/artifacts/')) return raw
  if (/[?&]access_token=/.test(raw)) return raw
  const resolved = token ?? (typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : '')
  if (!resolved) return raw
  const sep = raw.includes('?') ? '&' : '?'
  return `${raw}${sep}access_token=${encodeURIComponent(resolved)}`
}

/** Rewrite MinerU artifact API URLs in markdown so browser img tags can authenticate. */
export function attachKnowledgeArtifactAccessToMarkdown(markdown: string, token?: string | null): string {
  if (!markdown) return markdown
  return markdown.replace(
    /(\/askai-api\/api\/knowledge\/sources\/documents\/[^\s)"']+\/artifacts\/[^\s)"']+)/g,
    (match) => withKnowledgeArtifactAccess(match, token),
  )
}

const MD_IMAGE_RE = /!\[([^\]]*)\]\(([^)]+)\)/g
const HTML_IMAGE_RE = /<img\b[^>]*\bsrc=["']([^"']+)["'][^>]*(?:alt=["']([^"']*)["'])?/gi
const HEADING_RE = /^#{1,6}\s+(.+)$/gm
const IMAGE_SUFFIX = /\.(png|jpe?g|gif|webp|bmp|jp2|svg)$/i

type EvidenceTextSource = {
  content?: string
  snippet?: string
  document_id?: string
}

function normalizeImageUrl(url: string): string {
  return String(url || '').trim().split('?', 1)[0].replace(/\\/g, '/')
}

function normalizeMatchText(value: string): string {
  return String(value || '')
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[^\w\u3400-\u9fff]/g, '')
}

function contextTokens(text: string, size = 4): Set<string> {
  const normalized = normalizeMatchText(text)
  const tokens = new Set<string>()
  if (!normalized) return tokens
  if (normalized.length < size) {
    tokens.add(normalized)
    return tokens
  }
  for (let index = 0; index <= normalized.length - size; index += 1) {
    tokens.add(normalized.slice(index, index + size))
  }
  return tokens
}

function overlapScore(answer: string, context: string): number {
  const tokens = contextTokens(context)
  if (!tokens.size) return 0
  const answerNorm = normalizeMatchText(answer)
  if (!answerNorm) return 0
  let hits = 0
  tokens.forEach((token) => {
    if (answerNorm.includes(token)) hits += 1
  })
  return hits / tokens.size
}

function isRelativeImageRef(src: string): boolean {
  const value = String(src || '').trim().replace(/\\/g, '/')
  if (!value || /^https?:\/\//i.test(value) || value.startsWith('data:') || value.startsWith('/askai-api/')) {
    return false
  }
  return IMAGE_SUFFIX.test(value.split('?')[0].split('/').pop() || '')
}

function artifactPublicUrl(documentId: string, relativePath: string): string {
  const rel = String(relativePath || '').trim().replace(/\\/g, '/').replace(/^\.\//, '')
  const encoded = rel.split('/').map((part) => encodeURIComponent(part)).join('/')
  return `/askai-api/api/knowledge/sources/documents/${encodeURIComponent(documentId)}/artifacts/${encoded}`
}

function rewriteMineruImageUrls(markdown: string, documentId: string): string {
  if (!documentId) return markdown
  const replaceSrc = (src: string): string => {
    const raw = String(src || '').trim()
    if (!raw || !isRelativeImageRef(raw)) return raw
    const normalized = raw.replace(/\\/g, '/').replace(/^\.\//, '')
    const assetRel = normalized.startsWith('assets/')
      ? normalized
      : `assets/${normalized.split('/').pop() || normalized}`
    return artifactPublicUrl(documentId, assetRel)
  }
  return markdown.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_match, alt, src) => `![${alt}](${replaceSrc(src)})`)
}

function nearestHeading(text: string, position: number): string {
  let heading = ''
  HEADING_RE.lastIndex = 0
  let match = HEADING_RE.exec(text)
  while (match) {
    if (match.index <= position) heading = String(match[1] || '').trim()
    else break
    match = HEADING_RE.exec(text)
  }
  return heading
}

function imageContext(text: string, start: number, end: number, alt: string): string {
  const before = text.slice(Math.max(0, start - 420), start)
  const after = text.slice(end, Math.min(text.length, end + 220))
  const heading = nearestHeading(text, start)
  return [heading, alt, before, after].filter((part) => String(part || '').trim()).join('\n')
}

interface ImageCandidate {
  markdownLine: string
  url: string
  context: string
}

function extractImageCandidates(text: string): ImageCandidate[] {
  const body = String(text || '')
  const output: ImageCandidate[] = []
  const seen = new Set<string>()
  for (const match of body.matchAll(MD_IMAGE_RE)) {
    const alt = String(match[1] || '').trim()
    const url = String(match[2] || '').trim()
    if (!url) continue
    const key = normalizeImageUrl(url)
    if (seen.has(key)) continue
    seen.add(key)
    const index = match.index ?? 0
    output.push({
      markdownLine: `![${alt}](${url})`,
      url,
      context: imageContext(body, index, index + match[0].length, alt),
    })
  }
  return output
}

function splitAnswerBlocks(answer: string): string[] {
  const blocks = String(answer || '')
    .split(/\n\n+/)
    .map((block) => block.trim())
    .filter(Boolean)
  return blocks.length ? blocks : [String(answer || '').trim()]
}

/**
 * Embed citation images inline when evidence snippet context matches the assistant answer.
 */
export function mergeKnowledgeEvidenceImagesIntoAnswer(
  answer: string,
  sources: EvidenceTextSource[],
  options: { maxImages?: number; minScore?: number; minHits?: number } = {},
): string {
  const base = String(answer || '').trim()
  if (!base || base === '内部知识库中未找到足够依据。') return base

  const maxImages = options.maxImages ?? 3
  const minScore = options.minScore ?? 0.08
  const minHits = options.minHits ?? 3

  const presentUrls = new Set<string>()
  for (const match of base.matchAll(MD_IMAGE_RE)) {
    presentUrls.add(normalizeImageUrl(match[2]))
  }

  const citationTexts = sources
    .map((source) => {
      const documentId = String(source.document_id || '').trim()
      const raw = String(source.content || source.snippet || '').trim()
      if (!raw) return ''
      return rewriteMineruImageUrls(raw, documentId)
    })
    .filter(Boolean)

  const candidates: Array<{ item: ImageCandidate; score: number; hits: number }> = []
  for (const text of citationTexts) {
    for (const item of extractImageCandidates(text)) {
      const urlKey = normalizeImageUrl(item.url)
      if (presentUrls.has(urlKey)) continue
      const score = overlapScore(base, item.context)
      const hits = [...contextTokens(item.context)].filter((token) => contextTokens(base).has(token)).length
      if (score < minScore && hits < minHits) continue
      candidates.push({ item, score, hits })
    }
  }

  if (!candidates.length) {
    return attachKnowledgeArtifactAccessToMarkdown(base)
  }

  candidates.sort((a, b) => b.score - a.score || b.hits - a.hits)
  const blocks = splitAnswerBlocks(base)
  let embedded = 0

  for (const { item, score } of candidates) {
    if (embedded >= maxImages) break
    const urlKey = normalizeImageUrl(item.url)
    if (presentUrls.has(urlKey)) continue

    let bestIndex = 0
    let bestBlockScore = -1
    blocks.forEach((block, index) => {
      const blockScore = overlapScore(block, item.context)
      if (blockScore > bestBlockScore) {
        bestBlockScore = blockScore
        bestIndex = index
      }
    })
    if (bestBlockScore < minScore && score < minScore) continue

    blocks[bestIndex] = `${blocks[bestIndex]}\n\n${item.markdownLine}`
    presentUrls.add(urlKey)
    embedded += 1
  }

  return attachKnowledgeArtifactAccessToMarkdown(blocks.join('\n\n'))
}
