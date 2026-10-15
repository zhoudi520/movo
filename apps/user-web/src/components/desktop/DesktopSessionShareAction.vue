<script setup lang="ts">
import { ref, watch } from 'vue'
import { NButton, NModal, NSelect, useMessage } from 'naive-ui'
import SessionShareDialog from '../session/SessionShareDialog.vue'
import { getSession } from '../../api/sessions'
import { createSessionSnapshot, revokeSessionSnapshot } from '../../api/sessionSnapshots'
import { copyTextToClipboard } from '../../utils/copyTextToClipboard'
import { t } from '../../composables/i18n'

const props = defineProps<{ sessionId: string | null; userId: string; mainId: string; authToken: string | null; membersRevision?: number }>()
const emit = defineEmits<{ left: [sessionId: string] }>()
const message = useMessage()
const location = ref('')
const mode = ref<'owner' | 'participant'>('owner')
const available = ref(false)
const normalOpen = ref(false)
const snapshotOpen = ref(false)
const snapshotLink = ref('')
const snapshotId = ref('')
const expiry = ref(30)
const busy = ref(false)
let sequence = 0

watch(() => [props.sessionId, props.authToken, props.membersRevision], async () => {
  const current = ++sequence
  available.value = false
  normalOpen.value = false
  snapshotOpen.value = false
  snapshotLink.value = ''
  snapshotId.value = ''
  if (!props.sessionId || !props.userId || !props.authToken) return
  try {
    const detail = await getSession(props.sessionId, props.userId, props.mainId, props.authToken)
    if (current !== sequence) return
    location.value = detail.execution_location || 'server'
    mode.value = detail.access === 'shared' ? 'participant' : 'owner'
    available.value = location.value === 'server' || (location.value === 'desktop' && detail.runtime_preset_id === 'code' && mode.value === 'owner')
  } catch { if (current === sequence) available.value = false }
}, { immediate: true })

function open() {
  if (location.value === 'desktop') snapshotOpen.value = true
  else normalOpen.value = true
}

async function create() {
  if (!props.sessionId) return
  busy.value = true
  try {
    const result = await createSessionSnapshot(props.sessionId, expiry.value)
    snapshotLink.value = result.url
    snapshotId.value = result.id
  } catch { message.error(t('session.snapshot.createFailed')) }
  finally { busy.value = false }
}

async function copy() {
  try { await copyTextToClipboard(snapshotLink.value); message.success(t('session.share.copied')) }
  catch { message.error(t('session.share.copy_failed')) }
}

async function revoke() {
  if (!snapshotId.value) return
  busy.value = true
  try {
    await revokeSessionSnapshot(snapshotId.value)
    snapshotLink.value = ''
    snapshotId.value = ''
    message.success(t('session.share.revoked'))
  } catch { message.error(t('session.snapshot.revokeFailed')) }
  finally { busy.value = false }
}
</script>

<template>
  <div v-if="available">
    <button type="button" class="desktop-window-chrome__icon-button" :aria-label="t('session.share.action')" :title="t('session.share.action')" @click="open">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><path d="m8 6 4-4 4 4M12 2v13"/></svg>
    </button>
    <SessionShareDialog v-if="location === 'server'" v-model:show="normalOpen" :mode="mode" :session-id="sessionId" :members-revision="membersRevision" @left="sessionId && emit('left', sessionId)" />
    <n-modal v-if="location === 'desktop'" v-model:show="snapshotOpen" preset="card" :title="t('session.snapshot.title')" style="width: min(560px, calc(100vw - 32px))">
      <p class="mb-4 text-sm text-slate-600">{{ t('session.snapshot.hint') }}</p>
      <div v-if="!snapshotLink" class="flex gap-2">
        <n-select v-model:value="expiry" class="w-36" :options="[{ label: t('session.share.expiry_7'), value: 7 }, { label: t('session.share.expiry_30'), value: 30 }, { label: t('session.share.expiry_90'), value: 90 }]" />
        <n-button type="primary" :loading="busy" @click="create">{{ t('session.snapshot.create') }}</n-button>
      </div>
      <div v-else class="space-y-3">
        <input :value="snapshotLink" readonly class="w-full rounded border border-slate-300 p-2 text-sm" />
        <div class="flex gap-3"><n-button @click="copy">{{ t('session.share.copy') }}</n-button><n-button type="error" ghost :loading="busy" @click="revoke">{{ t('session.share.revoke') }}</n-button></div>
      </div>
    </n-modal>
  </div>
</template>

<style scoped>
.desktop-window-chrome__icon-button {
  display: inline-flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #475569;
  cursor: pointer;
  -webkit-app-region: no-drag;
}
.desktop-window-chrome__icon-button:hover { background: #eaf0f8; color: #2563eb; }
</style>
