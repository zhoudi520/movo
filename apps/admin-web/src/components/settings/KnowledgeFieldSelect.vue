<script setup lang="ts">
import { NAutoComplete } from 'naive-ui';
import type { FieldOption } from './knowledgeFieldOptions';
import { t } from '@/composables/i18n';

defineProps<{ value: string; label: string; options: FieldOption[]; required?: boolean }>();
const emit = defineEmits<{ (e: 'update:value', value: string): void }>();
</script>

<template>
  <n-form-item :label="label" :required="required">
    <n-auto-complete
      :value="value"
      :options="options.map((option) => ({ label: option.label, value: option.value }))"
      clearable
      :get-show="() => options.length > 0"
      :placeholder="t('knowledgeSource.chooseField')"
      @update:value="(next: string | null) => emit('update:value', next || '')"
    />
  </n-form-item>
</template>
