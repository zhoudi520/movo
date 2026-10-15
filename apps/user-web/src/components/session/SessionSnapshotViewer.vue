<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NButton, NSpin } from 'naive-ui'
import { readSessionSnapshot, type SessionSnapshot } from '../../api/sessionSnapshots'
import { t } from '../../composables/i18n'
import SessionSnapshotConversation from './SessionSnapshotConversation.vue'

const props = defineProps<{ token: string }>()
const emit = defineEmits<{ close: [] }>()
const snapshot = ref<SessionSnapshot | null>(null)
const loading = ref(true)
const error = ref(false)

onMounted(async () => {
  try { snapshot.value = await readSessionSnapshot(props.token) }
  catch { error.value = true }
  finally { loading.value = false }
})
</script>

<template>
  <div class="fixed inset-0 z-[100] overflow-y-auto bg-white text-slate-900">
    <header class="sticky top-0 z-10 border-b border-slate-200 bg-white/95 px-5 py-3 backdrop-blur">
      <div class="mx-auto flex max-w-5xl items-center justify-between gap-4">
        <span class="shrink-0 text-lg font-semibold tracking-wide text-slate-600">MOVO</span>
        <div class="min-w-0 text-center"><strong class="block truncate text-sm">{{ snapshot?.title || t('session.snapshot.title') }}</strong><p class="text-xs text-slate-500">{{ t('session.snapshot.readOnly') }}</p></div>
        <n-button class="shrink-0" round @click="emit('close')">{{ t('ui.close') }}</n-button>
      </div>
    </header>
    <main class="mx-auto max-w-4xl px-5">
      <n-spin v-if="loading" />
      <p v-else-if="error">{{ t('session.snapshot.unavailable') }}</p>
      <SessionSnapshotConversation v-else :messages="snapshot?.messages || []" />
    </main>
  </div>
</template>
