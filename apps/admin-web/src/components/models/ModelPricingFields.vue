<script setup lang="ts">
import { computed } from 'vue';
import { t } from '@/composables/i18n';
import type { ModelPricing } from '@/api/models';

const props = defineProps<{ modelValue: ModelPricing | null }>();
const emit = defineEmits<{ (event: 'update:modelValue', value: ModelPricing | null): void }>();
const enabled = computed(() => props.modelValue !== null);
const currencyOptions = [
  { label: 'CNY (¥)', value: 'CNY' },
  { label: 'USD ($)', value: 'USD' },
];

function update(value: Partial<ModelPricing>) {
  emit('update:modelValue', { currency: 'CNY', inputPerMillion: 0, outputPerMillion: 0, ...props.modelValue, ...value });
}

function toggle(value: boolean) {
  emit('update:modelValue', value ? { currency: 'CNY', inputPerMillion: 0, outputPerMillion: 0 } : null);
}
</script>

<template>
  <section class="pricing-card">
    <div class="pricing-heading">
      <n-checkbox :checked="enabled" @update:checked="toggle">{{ t('modelPricing.enable') }}</n-checkbox>
      <div v-if="modelValue" class="currency-control">
        <span>{{ t('modelPricing.currency') }}</span>
        <n-select
          :value="modelValue.currency"
          :options="currencyOptions"
          @update:value="(value: 'CNY' | 'USD') => update({ currency: value })"
        />
      </div>
    </div>
    <p class="pricing-help">{{ t('modelPricing.help') }}</p>
    <div v-if="modelValue" class="rate-grid">
      <label class="rate-field">
        <span>{{ t('modelPricing.input') }}</span>
        <n-input-number
          :value="modelValue.inputPerMillion"
          :min="0"
          :max="1000000"
          :precision="6"
          :show-button="false"
          @update:value="(value: number | null) => update({ inputPerMillion: value ?? 0 })"
        />
      </label>
      <label class="rate-field">
        <span>{{ t('modelPricing.output') }}</span>
        <n-input-number
          :value="modelValue.outputPerMillion"
          :min="0"
          :max="1000000"
          :precision="6"
          :show-button="false"
          @update:value="(value: number | null) => update({ outputPerMillion: value ?? 0 })"
        />
      </label>
    </div>
  </section>
</template>

<style scoped>
.pricing-card {
  width: 100%;
  padding: 18px 20px;
  border: 1px solid #dfe7f3;
  border-radius: 12px;
  background: #f8faff;
  box-sizing: border-box;
}
.pricing-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.currency-control { display: flex; align-items: center; gap: 10px; color: #64748b; white-space: nowrap; }
.currency-control :deep(.n-select) { width: 145px; }
.pricing-help { margin: 8px 0 0; color: #728098; font-size: 13px; line-height: 1.5; }
.rate-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 18px; }
.rate-field { display: flex; flex-direction: column; gap: 8px; min-width: 0; color: #334155; font-size: 13px; font-weight: 500; }
.rate-field :deep(.n-input-number) { width: 100%; }
@media (max-width: 720px) {
  .pricing-heading { align-items: flex-start; flex-direction: column; }
  .rate-grid { grid-template-columns: 1fr; }
}
</style>
