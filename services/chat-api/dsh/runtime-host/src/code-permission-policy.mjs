const PRESETS = new Set(['read-only', 'workspace-write', 'danger-full-access'])
const REVIEWERS = new Set(['user', 'auto_review'])
const APPROVAL_POLICIES = new Set(['ask', 'never'])

/** Validate Code-only permission inputs before they reach the native DSH session. */
export function codePermissionPolicy(input = {}) {
  const permissionPreset = input.permissionPreset ?? 'workspace-write'
  const approvalReviewer = input.approvalReviewer ?? 'user'
  const approvalPolicy = input.approvalPolicy ?? (permissionPreset === 'danger-full-access' ? 'never' : 'ask')
  if (!PRESETS.has(permissionPreset)) throw new Error('unsupported Code Session permissionPreset')
  if (!REVIEWERS.has(approvalReviewer)) throw new Error('unsupported Code Session approvalReviewer')
  if (!APPROVAL_POLICIES.has(approvalPolicy)) throw new Error('unsupported Code Session approvalPolicy')
  if (permissionPreset === 'danger-full-access' && approvalReviewer === 'auto_review') {
    throw new Error('automatic review requires a sandbox boundary')
  }
  if (approvalPolicy === 'never' && approvalReviewer === 'auto_review') {
    throw new Error('automatic review requires approval_policy ask')
  }
  return { permissionPreset, approvalReviewer, approvalPolicy }
}
