import { ref, watch, type Ref } from 'vue'
import {
  previewToolGovernance,
  type ExternalToolItem,
  type ToolGovernancePreviewItem,
  type ToolPayload,
} from '../api/tools'

/**
 * Loads MCP tool risk / approval preview from chat-api (same rules as runtime compile).
 */
export function useMcpGovernancePreview(options: {
  userId: () => string
  mainId: () => string
  form: Ref<ToolPayload>
  discoveredTools: Ref<ExternalToolItem['discoveredTools']>
}) {
  const governanceByName = ref<Record<string, ToolGovernancePreviewItem>>({})
  let timer: ReturnType<typeof setTimeout> | null = null

  function governanceFor(name: string): ToolGovernancePreviewItem | null {
    const key = String(name || '').trim()
    return key ? governanceByName.value[key] || null : null
  }

  async function refreshGovernancePreview() {
    if (options.form.value.type !== 'mcp' || options.discoveredTools.value.length === 0) {
      governanceByName.value = {}
      return
    }
    const userId = options.userId()
    if (!userId) {
      governanceByName.value = {}
      return
    }
    try {
      const result = await previewToolGovernance(userId, options.mainId(), {
        type: 'mcp',
        config: { ...options.form.value.config },
        discoveredTools: options.discoveredTools.value,
      })
      const next: Record<string, ToolGovernancePreviewItem> = {}
      for (const item of result.items || []) {
        const name = String(item.name || '').trim()
        if (name) next[name] = item
      }
      governanceByName.value = next
    } catch {
      governanceByName.value = {}
    }
  }

  function scheduleGovernancePreview() {
    if (timer !== null) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      void refreshGovernancePreview()
    }, 300)
  }

  watch(
    () => [options.form.value.type, options.form.value.config, options.discoveredTools.value] as const,
    () => scheduleGovernancePreview(),
    { deep: true },
  )

  return { governanceByName, governanceFor, refreshGovernancePreview }
}
