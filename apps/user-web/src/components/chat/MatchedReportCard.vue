<script setup lang="ts">
import { computed } from 'vue'
import type { ReportMatchItem } from '../../features/chat/reportMatch'
import { pickReportMatchTitle } from '../../features/chat/reportMatch'
import { t, useLocale } from '../../composables/i18n'

const props = defineProps<{
  item: ReportMatchItem
  favorited?: boolean
  openEnabled?: boolean
}>()

const emit = defineEmits<{
  (event: 'open', item: ReportMatchItem): void
  (event: 'favorite', item: ReportMatchItem): void
}>()

const { locale } = useLocale()
const title = computed(() => pickReportMatchTitle(props.item.name, locale.value) || props.item.functionId)
</script>

<template>
  <article class="matched-report-row">
    <div class="matched-report-card-body">
      <h4 class="matched-report-card-title">{{ title }}</h4>
      <p class="matched-report-card-path">({{ item.menuPath }})</p>
    </div>
    <div class="matched-report-card-actions">
      <button type="button" class="matched-report-btn matched-report-btn-ghost" @click="emit('favorite', item)">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 17.3 6.2 21l1.6-6.7L2 9.3l6.9-.6L12 2l3.1 6.7 6.9.6-5.8 4.9L17.8 21z" :fill="favorited ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.6" /></svg>
        <span>{{ t('shortcuts.favorite') }}</span>
      </button>
      <button
        type="button"
        class="matched-report-btn matched-report-btn-primary"
        :disabled="openEnabled === false"
        @click="emit('open', item)"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3h7v7M10 14 21 3M5 5h6v14H5z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" /></svg>
        <span>{{ t('report.match.open') }}</span>
      </button>
    </div>
  </article>
</template>

<style scoped>
.matched-report-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: #f3f4f6;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.matched-report-row:hover {
  background: #eff6ff;
  border-color: #dbeafe;
}

.matched-report-card-body {
  min-width: 0;
  flex: 1;
}

.matched-report-card-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #111827;
  line-height: 1.45;
}

.matched-report-card-path {
  margin: 4px 0 0;
  font-size: 12px;
  color: #6b7280;
  line-height: 1.4;
  word-break: break-all;
}

.matched-report-card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.matched-report-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 0 12px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}

.matched-report-btn svg {
  width: 16px;
  height: 16px;
}

.matched-report-btn-ghost {
  border: 1px solid #d1d5db;
  background: #fff;
  color: #374151;
}

.matched-report-btn-ghost:hover {
  background: #f9fafb;
}

.matched-report-btn-primary {
  border: 1px solid #2563eb;
  background: #2563eb;
  color: #fff;
}

.matched-report-btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
  border-color: #1d4ed8;
}

.matched-report-btn-primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
</style>
