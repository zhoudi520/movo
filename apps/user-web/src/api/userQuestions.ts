import type { DshPendingQuestion, DshQuestionAnswer } from '../platform/types'

function endpoint(conversationId: string, suffix = ''): string {
  return `/askai-api/api/dsh/conversations/${encodeURIComponent(conversationId)}/questions${suffix}`
}

export async function listUserQuestions(conversationId: string, token: string): Promise<DshPendingQuestion[]> {
  const response = await fetch(endpoint(conversationId), {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Question recovery failed: ${response.status}`)
  const payload = await response.json()
  return Array.isArray(payload?.questions) ? payload.questions : []
}

export async function answerUserQuestion(conversationId: string, questionId: string, answers: DshQuestionAnswer[], token: string): Promise<void> {
  const response = await fetch(endpoint(conversationId, `/${encodeURIComponent(questionId)}/answer`), {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers }),
  })
  if (response.ok) return
  const payload = await response.json().catch(() => ({}))
  throw new Error(typeof payload?.detail === 'string' ? payload.detail : `Question answer failed: ${response.status}`)
}
