<script setup lang="ts">
import type { SessionSnapshot } from '../../api/sessionSnapshots'
import { t } from '../../composables/i18n'

defineProps<{ messages: SessionSnapshot['messages'] }>()
</script>

<template>
  <div class="snapshot-conversation">
    <div v-for="(item, index) in messages" :key="index" class="snapshot-turn" :class="{ 'snapshot-turn--user': item.role === 'user' }">
      <div v-if="item.role === 'user'" class="snapshot-user-message">
        <div class="snapshot-speaker">{{ item.author_name || t('session.snapshot.user') }}</div>
        <div class="snapshot-copy">{{ item.content }}</div>
      </div>
      <div v-else class="snapshot-assistant-message">
        <div class="snapshot-speaker">{{ t('session.snapshot.assistant') }}</div>
        <div class="snapshot-copy">{{ item.content }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.snapshot-conversation { display: flex; flex-direction: column; gap: 28px; padding: 40px 0 88px; }
.snapshot-turn { display: flex; min-width: 0; }
.snapshot-turn--user { justify-content: flex-end; }
.snapshot-user-message { max-width: min(78%, 740px); border-radius: 22px; background: #f3f4f6; padding: 15px 20px; }
.snapshot-assistant-message { width: 100%; padding: 0 2px; }
.snapshot-speaker { margin-bottom: 8px; color: #64748b; font-size: 12px; font-weight: 600; }
.snapshot-copy { color: #1f2937; font-size: 15px; line-height: 1.85; white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 640px) {
  .snapshot-conversation { gap: 22px; padding: 24px 0 56px; }
  .snapshot-user-message { max-width: 92%; }
}
</style>
