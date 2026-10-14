<script setup lang="ts">
import { computed } from 'vue';
import { t } from '@/composables/i18n';
import type { ModelGroupItem, ModelInstanceItem, ModelProviderItem } from '@/api/models';
import { capabilityLabel } from './capabilityLabels';
import { providerLabel } from './providerLabels';

const props = defineProps<{ group: ModelGroupItem; models: ModelInstanceItem[]; providers: ModelProviderItem[] }>();
const emit = defineEmits<{ (event: 'edit'): void; (event: 'add'): void; (event: 'edit-model', model: ModelInstanceItem): void }>();
const provider = computed(() => props.providers.find((item) => item.id === props.group.providerId));
</script>

<template>
  <section class="model-group-card" :class="{ 'is-disabled': group.status === 'disabled' }">
    <div class="group-head">
      <span class="group-badge">{{ t('modelGroup.badge') }}</span>
      <span class="group-count">{{ group.status === 'disabled' ? `${t('modelGroup.disabled')} · ` : '' }}{{ t('modelGroup.count', { count: models.length }) }}</span>
    </div>
    <h3>{{ group.name }}</h3>
    <p class="group-provider">{{ providerLabel(provider) }} · {{ group.baseUrl }}</p>
    <div class="group-models">
      <button v-for="model in models" :key="model.id" type="button" class="group-model" @click="emit('edit-model', model)">
        <span><strong>{{ model.displayName }}</strong><small>{{ model.modelName }}</small></span>
        <span class="model-capabilities">{{ model.capabilities.map(capabilityLabel).join(' · ') }}</span>
      </button>
      <p v-if="!models.length" class="group-empty">{{ t('modelGroup.empty') }}</p>
    </div>
    <div class="group-actions">
      <n-button size="small" secondary @click="emit('edit')">{{ t('modelGroup.settings') }}</n-button>
      <n-button size="small" type="primary" secondary @click="emit('add')">{{ t('modelGroup.addModel') }}</n-button>
    </div>
  </section>
</template>

<style scoped>
.model-group-card { position: relative; isolation: isolate; display: flex; flex-direction: column; gap: 10px; min-height: 220px; padding: 16px; margin: 0 6px 8px 0; border: 1px solid #b9c9ef; border-radius: 10px; background: #fdfefe; box-shadow: 0 4px 12px rgba(35, 75, 150, .06); }
.model-group-card::before, .model-group-card::after { content: ''; position: absolute; inset: 5px -5px -5px 5px; z-index: -1; border: 1px solid #ccdaf4; border-radius: 10px; background: #f4f8ff; }
.model-group-card::after { inset: 10px -10px -10px 10px; z-index: -2; background: #e9f1ff; }
.model-group-card.is-disabled { border-color: #d0d5de; }
.model-group-card.is-disabled::before, .model-group-card.is-disabled::after { border-color: #dce0e7; background: #f2f3f6; }
.group-head, .group-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.group-badge { padding: 3px 8px; border-radius: 5px; color: #2455bb; background: #e9f0ff; font-size: 11px; font-weight: 700; }
.group-count, .group-provider, .group-empty { color: #687789; font-size: 12px; }
h3 { margin: 0; color: #17233d; font-size: 16px; }
.group-provider { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin: 0; }
.group-models { display: grid; gap: 5px; max-height: 165px; overflow: auto; }
.group-model { width: 100%; display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 8px; border: 1px solid #e5eaf4; border-radius: 7px; background: #fff; color: #263859; text-align: left; cursor: pointer; }
.group-model:hover { border-color: #6690e8; }
.group-model strong, .group-model small { display: block; }
.group-model small { color: #7b8799; font-size: 11px; }
.model-capabilities { color: #697b96; font-size: 11px; white-space: nowrap; }
.group-actions { margin-top: auto; }
</style>
