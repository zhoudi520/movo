import assert from 'node:assert/strict'
import test from 'node:test'

import { CodeApprovalReviewer, parseDecision } from '../src/code-approval-reviewer.mjs'
import { codePermissionPolicy } from '../src/code-permission-policy.mjs'

test('reviewer accepts only explicit structured decisions', () => {
  assert.deepEqual(parseDecision('{"decision":"allow","reason":"bounded test"}'), { allowed: true, reason: 'bounded test' })
  assert.throws(() => parseDecision('yes'), SyntaxError)
  assert.throws(() => parseDecision('{"decision":"allow"}'))
})

test('separate reviewer model call receives no tools and fails closed', async () => {
  let options
  const adapter = { async *stream(value) { options = value; yield { type: 'text-delta', text: '{"decision":"deny","reason":"credential access"}' } } }
  const reviewer = new CodeApprovalReviewer(adapter, { modelName: 'test-model' })
  const result = await reviewer.review({ sessionId: 's', toolName: 'bash', reason: 'read secret', argumentsJson: '{"command":"cat .env"}' })
  assert.equal(result.allowed, false)
  assert.deepEqual(options.tools, [])
  assert.match(options.messages[0].content, /cat \.env/)
  const failed = new CodeApprovalReviewer({ async *stream() { throw new Error('provider failed') } }, { modelName: 'test-model' })
  assert.equal((await failed.review({ sessionId: 's', toolName: 'bash', reason: '', argumentsJson: '' })).allowed, false)
})

test('code permission policy validates effective sandbox and reviewer pair', () => {
  assert.deepEqual(codePermissionPolicy(), { permissionPreset: 'workspace-write', approvalReviewer: 'user', approvalPolicy: 'ask' })
  assert.deepEqual(codePermissionPolicy({ approvalReviewer: 'auto_review' }), { permissionPreset: 'workspace-write', approvalReviewer: 'auto_review', approvalPolicy: 'ask' })
  assert.deepEqual(codePermissionPolicy({ permissionPreset: 'danger-full-access' }), { permissionPreset: 'danger-full-access', approvalReviewer: 'user', approvalPolicy: 'never' })
  assert.throws(() => codePermissionPolicy({ permissionPreset: 'danger-full-access', approvalReviewer: 'auto_review' }))
})
