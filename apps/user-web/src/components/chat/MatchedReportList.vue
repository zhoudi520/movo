<script setup lang="ts">
import type { ReportMatchItem } from '../../features/chat/reportMatch'
import { t } from '../../composables/i18n'
import MatchedReportCard from './MatchedReportCard.vue'

defineProps<{
  items: ReportMatchItem[]
  isFavorite?: (item: ReportMatchItem) => boolean
  openEnabled?: boolean
}>()

const emit = defineEmits<{
  (event: 'open', item: ReportMatchItem): void
  (event: 'favorite', item: ReportMatchItem): void
}>()
</script>

<template>
  <section v-if="items.length" class="matched-report-list" aria-label="report matches">
    <header class="matched-report-list-header">
      <span class="matched-report-list-icon" aria-hidden="true">🎯</span>
      <h3 class="matched-report-list-title">{{ t('report.match.title') }}</h3>
    </header>
    <div class="matched-report-list-items">
      <MatchedReportCard
        v-for="item in items"
        :key="item.key"
        :item="item"
        :favorited="isFavorite?.(item)"
        :open-enabled="openEnabled"
        @open="emit('open', $event)"
        @favorite="emit('favorite', $event)"
      />
    </div>
  </section>
</template>

<style scoped>
.matched-report-list {
  margin: 12px 0;
  padding: 14px 14px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.matched-report-list-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.matched-report-list-icon {
  font-size: 15px;
  line-height: 1;
}

.matched-report-list-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #111827;
}

.matched-report-list-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>
