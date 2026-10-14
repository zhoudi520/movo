export interface InvitationDetail {
  orgName: string
  expiresAt: string
}

async function readResponse(response: Response) {
  const body = await response.json().catch(() => ({})) as { detail?: unknown }
  if (!response.ok) {
    const detail = Array.isArray(body.detail)
      ? body.detail.map(item => typeof item?.msg === 'string' ? item.msg : '').filter(Boolean).join('; ')
      : typeof body.detail === 'string' ? body.detail : ''
    throw new Error(detail || `HTTP ${response.status}`)
  }
  return body
}

export async function fetchInvitation(code: string): Promise<InvitationDetail> {
  const response = await fetch(`/admin-api/api/directory/invite-links/${encodeURIComponent(code)}`)
  return readResponse(response) as Promise<InvitationDetail>
}

export async function registerWithInvitation(code: string, payload: { loginName: string; name: string; email: string; password: string }) {
  const response = await fetch(`/admin-api/api/directory/invite-links/${encodeURIComponent(code)}/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...payload, mobile: '' }),
  })
  await readResponse(response)
}
