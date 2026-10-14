import { ref } from 'vue'
import adminProductUiExtension from '@movo-admin-product-extension'

export function useModelAccessExtension() {
  const extension = adminProductUiExtension.modelAccess
  const value = ref<unknown>(extension?.createValue())
  const loading = ref(false)

  function reset(grouped = false) {
    value.value = extension?.createValue(grouped)
  }

  async function load(modelId: string) {
    if (!extension) return
    loading.value = true
    try {
      value.value = await extension.load(modelId)
    } finally {
      loading.value = false
    }
  }

  function validate(): string | null {
    return extension?.validate?.(value.value) || null
  }

  async function save(modelId: string) {
    if (extension) await extension.save(modelId, value.value)
  }

  return { enabled: Boolean(extension), value, loading, reset, load, validate, save }
}
