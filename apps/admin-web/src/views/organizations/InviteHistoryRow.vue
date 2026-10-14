<script setup lang="ts">
import type { InviteHistoryItem } from '@/api/directory';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import { t } from '@/composables/i18n';

defineProps<{ invite: InviteHistoryItem; departmentName: string; roleName: string }>();
const emit = defineEmits<{
  (event: 'select'): void;
  (event: 'copy', value: string): void;
  (event: 'revoke'): void;
}>();
</script>

<template>
  <article class="invite-row">
    <div class="row-header">
      <div><strong>{{ departmentName }} · {{ roleName }}</strong><div class="muted">{{ t('inviteHistory.createdAt') }}: {{ formatAdminDateTime(invite.createdAt) }}</div></div>
      <n-tag :type="invite.status === 'active' ? 'success' : 'default'" size="small">{{ t(`inviteHistory.status.${invite.status}`) }}</n-tag>
    </div>
    <div class="muted">{{ t('inviteHistory.members') }}: {{ invite.acceptedCount }} · {{ t('inviteHistory.expires') }}: {{ formatAdminDateTime(invite.expiresAt) }}</div>
    <div class="row-actions">
      <n-button text type="primary" @click="emit('select')">{{ t('inviteHistory.viewMembers') }}</n-button>
      <n-button size="small" :disabled="invite.status !== 'active'" @click="emit('copy', invite.inviteUrl)">{{ t('inviteHistory.copy') }}</n-button>
      <n-button size="small" :disabled="invite.status !== 'active'" @click="emit('copy', invite.token)">{{ t('inviteHistory.copyCode') }}</n-button>
      <n-button size="small" :disabled="invite.status !== 'active'" @click="emit('revoke')">{{ t('inviteHistory.revoke') }}</n-button>
    </div>
  </article>
</template>

<style scoped>
.invite-row { padding:14px 2px; border-bottom:1px solid #e5e7eb; }
.row-header,.row-actions { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.row-actions { justify-content:flex-start; flex-wrap:wrap; margin-top:10px; }
.muted { color:#64748b; font-size:12px; margin-top:4px; }
</style>
