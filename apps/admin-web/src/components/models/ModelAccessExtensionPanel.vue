<script setup lang="ts">
import adminProductUiExtension from '@movo-admin-product-extension'

defineProps<{ modelValue: unknown; loading: boolean; grouped?: boolean }>()
const emit = defineEmits<{ (event: 'update:modelValue', value: unknown): void }>()

const extension = adminProductUiExtension.modelAccess
</script>

<template>
  <n-spin v-if="extension" :show="loading">
    <component
      :is="extension.component"
      :model-value="modelValue"
      :grouped="grouped"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </n-spin>
</template>
