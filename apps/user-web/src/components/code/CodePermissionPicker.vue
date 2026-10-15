<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import ChevronDownOutline from '@vicons/ionicons5/es/ChevronDownOutline'
import type { CodePermissionMode } from '../../platform/types'
import { openDshCodePermissionConfig, validateDshCodePermissionConfig } from '../../platform'
import { t } from '../../composables/i18n'

const props = defineProps<{ modelValue: CodePermissionMode; disabled?: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: CodePermissionMode): void }>()
const open = ref(false)
const error = ref('')
const configPath = ref('')
const checking = ref(false)
const options: { mode: CodePermissionMode; title: string; description: string }[] = [
  { mode: 'ask', title: 'code.permission.ask', description: 'code.permission.askHint' },
  { mode: 'auto', title: 'code.permission.auto', description: 'code.permission.autoHint' },
  { mode: 'full', title: 'code.permission.full', description: 'code.permission.fullHint' },
  { mode: 'custom', title: 'code.permission.custom', description: 'code.permission.customHint' },
]
const selected = computed(() => options.find(item => item.mode === props.modelValue) || options[0])
async function choose(mode: CodePermissionMode) {
  if (mode === 'custom') {
    checking.value = true
    try { configPath.value = await validateDshCodePermissionConfig() }
    catch { error.value = t('code.permission.invalidConfig'); checking.value = false; return }
    checking.value = false
  }
  emit('update:modelValue', mode)
  open.value = false
  error.value = ''
}
async function editCustom() {
  try { configPath.value = await openDshCodePermissionConfig(); error.value = '' }
  catch (cause) { error.value = String(cause) }
}
function closeOnOutside(event: PointerEvent) {
  if (!(event.target as Element)?.closest?.('[data-code-permission-picker]')) open.value = false
}
if (typeof document !== 'undefined') document.addEventListener('pointerdown', closeOnOutside)
onBeforeUnmount(() => document.removeEventListener('pointerdown', closeOnOutside))
</script>

<template>
  <div data-code-permission-picker class="relative shrink-0">
    <button type="button" class="flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-200"
      :class="modelValue === 'full' ? 'text-orange-600' : 'text-slate-600'" :disabled="disabled" :aria-expanded="open"
      :title="t(selected.description)" @click="open = !open">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2 4 5v6c0 5.5 3.4 9.4 8 11 4.6-1.6 8-5.5 8-11V5l-8-3Z"/><path d="M12 8v5m0 4h.01"/></svg>
      <span>{{ t(selected.title) }}</span><ChevronDownOutline class="h-3 w-3 shrink-0" aria-hidden="true" />
    </button>
    <div v-if="open" class="absolute bottom-full left-0 z-50 mb-2 w-[340px] max-w-[90vw] rounded-2xl border border-slate-200 bg-white p-2 shadow-xl" role="menu">
      <div class="px-3 py-2 text-xs font-medium text-slate-500">{{ t('code.permission.heading') }}</div>
      <button v-for="item in options" :key="item.mode" type="button" role="menuitemradio" :aria-checked="modelValue === item.mode" :disabled="checking"
        class="flex w-full items-start justify-between gap-3 rounded-xl px-3 py-2 text-left hover:bg-slate-50" @click="choose(item.mode)">
        <span><strong class="block text-sm text-slate-800" :class="item.mode === 'full' ? 'text-orange-600' : ''">{{ t(item.title) }}</strong>
          <span class="mt-0.5 block text-xs leading-5 text-slate-500">{{ t(item.description) }}</span></span>
        <span v-if="modelValue === item.mode" class="text-blue-600" aria-hidden="true">✓</span>
      </button>
      <div class="mt-1 border-t border-slate-100 px-3 pt-2">
        <button type="button" class="text-xs text-blue-600 hover:underline" @click="editCustom">{{ t('code.permission.editConfig') }}</button>
        <p v-if="configPath" class="mt-1 break-all text-[11px] leading-4 text-slate-500">{{ configPath }}</p>
        <p class="mt-1 text-[11px] leading-4 text-slate-500">{{ t('code.permission.applyNextTurn') }}</p>
        <p class="mt-1 text-[11px] leading-4 text-slate-500">{{ t('code.permission.networkLimit') }}</p>
        <p v-if="error" class="mt-1 text-xs text-red-600" role="alert">{{ error }}</p>
      </div>
    </div>
  </div>
</template>
