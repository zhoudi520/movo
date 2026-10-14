<script setup lang="ts">
import { ref, watch } from 'vue'
import { fetchInvitation, registerWithInvitation } from '../../api/invitations'
import { t } from '../../composables/i18n'

const props = defineProps<{ initialCode?: string }>()
const emit = defineEmits<{ (event: 'success', username: string): void }>()
const code = ref(props.initialCode || '')
const orgName = ref('')
const loginName = ref('')
const name = ref('')
const email = ref('')
const password = ref('')
const confirmation = ref('')
const error = ref('')
const loading = ref(false)

watch(() => props.initialCode, value => { if (value) code.value = value }, { immediate: true })

async function inspectCode() {
  orgName.value = ''
  error.value = ''
  if (!code.value.trim()) return
  try {
    const detail = await fetchInvitation(code.value.trim())
    orgName.value = detail.orgName
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : t('invite.invalid')
  }
}

watch(code, () => { orgName.value = '' })
if (code.value) void inspectCode()

async function submit() {
  error.value = ''
  if (!code.value.trim() || !loginName.value.trim() || !name.value.trim()) {
    error.value = t('invite.required')
    return
  }
  if (password.value.length < 10 || password.value !== confirmation.value) {
    error.value = t('invite.password_rule')
    return
  }
  loading.value = true
  try {
    await registerWithInvitation(code.value.trim(), { loginName: loginName.value.trim(), name: name.value.trim(), email: email.value.trim(), password: password.value })
    emit('success', loginName.value.trim())
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : t('invite.invalid')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <form class="mt-6 space-y-4" @submit.prevent="submit">
    <div v-if="orgName" class="rounded-xl bg-blue-50 px-4 py-3 text-sm text-blue-800">{{ t('invite.join_org', { org: orgName }) }}</div>
    <label class="block text-sm text-slate-700">{{ t('invite.code') }}
      <div class="mt-1 flex gap-2"><input v-model="code" required class="min-w-0 flex-1 rounded-xl border border-slate-300 px-3 py-2" /><button type="button" class="rounded-xl border px-3" @click="inspectCode">{{ t('invite.verify') }}</button></div>
    </label>
    <label class="block text-sm text-slate-700">{{ t('invite.username') }}<input v-model="loginName" required autocomplete="username" class="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2" /></label>
    <label class="block text-sm text-slate-700">{{ t('invite.name') }}<input v-model="name" required autocomplete="name" class="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2" /></label>
    <label class="block text-sm text-slate-700">{{ t('invite.email') }}<input v-model="email" type="email" autocomplete="email" class="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2" /></label>
    <label class="block text-sm text-slate-700">{{ t('invite.password') }}<input v-model="password" type="password" required autocomplete="new-password" class="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2" /></label>
    <label class="block text-sm text-slate-700">{{ t('invite.confirm_password') }}<input v-model="confirmation" type="password" required autocomplete="new-password" class="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2" /></label>
    <p v-if="error" role="alert" class="text-sm text-red-600">{{ error }}</p>
    <button type="submit" :disabled="loading" class="w-full rounded-xl bg-blue-600 px-4 py-3 font-semibold text-white disabled:opacity-50">{{ loading ? t('invite.submitting') : t('invite.register') }}</button>
  </form>
</template>
