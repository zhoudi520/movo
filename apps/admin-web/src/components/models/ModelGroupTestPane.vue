<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import axios from 'axios';
import { t } from '@/composables/i18n';
import { streamModelInstanceTest, testImageModelInstance, testKnowledgeModelInstance, type ModelInstanceItem } from '@/api/models';
import { resolveModelTestKind } from './modelTestKind';
import FlaskOutline from '@vicons/ionicons5/es/FlaskOutline';
import PlayOutline from '@vicons/ionicons5/es/PlayOutline';

const props = defineProps<{ models: ModelInstanceItem[]; selectedId?: string }>();
const emit = defineEmits<{ (event: 'tested'): void; (event: 'select', id: string): void }>();
const modelId = ref('');
const prompt = ref(t('测试模型默认提示'));
const testing = ref(false);
const result = ref('');
const resultType = ref<'idle' | 'success' | 'failed'>('idle');
const imageUrl = ref('');
const model = computed(() => props.models.find((item) => item.id === modelId.value));
const kind = computed(() => resolveModelTestKind(model.value?.capabilities || []));
const options = computed(() => props.models.map((item) => ({ label: `${item.displayName} · ${item.modelName}`, value: item.id })));

watch(() => [props.models, props.selectedId] as const, () => {
  if (props.selectedId && props.models.some((item) => item.id === props.selectedId)) modelId.value = props.selectedId;
  else if (!props.models.some((item) => item.id === modelId.value)) modelId.value = props.models[0]?.id || '';
}, { immediate: true });
watch(modelId, () => { result.value = ''; resultType.value = 'idle'; imageUrl.value = ''; });

function errorText(error: unknown) {
  return axios.isAxiosError(error) ? String(error.response?.data?.detail || error.message) : String(error);
}

async function run() {
  if (!model.value || testing.value) return;
  const selectedId = model.value.id;
  testing.value = true;
  result.value = '';
  resultType.value = 'idle';
  imageUrl.value = '';
  try {
    if (kind.value === 'image') {
      const response = await testImageModelInstance(selectedId, prompt.value);
      result.value = response.message || (response.success ? t('图片生成测试成功。') : t('图片生成测试失败。'));
      resultType.value = response.success ? 'success' : 'failed';
      imageUrl.value = response.imageUrl || '';
    } else if (kind.value === 'embedding' || kind.value === 'rerank') {
      const response = await testKnowledgeModelInstance(selectedId, kind.value);
      result.value = response.message || (response.success ? t('模型连接测试成功。') : t('测试失败'));
      resultType.value = response.success ? 'success' : 'failed';
    } else {
      let receivedDelta = false;
      await streamModelInstanceTest(selectedId, prompt.value, (event) => {
        if (event.type === 'start') result.value = event.message || t('正在连接模型...');
        if (event.type === 'delta') {
          if (!receivedDelta) { result.value = ''; receivedDelta = true; }
          result.value += event.content || '';
        }
        if (event.type === 'error') { result.value = event.message || t('测试失败'); resultType.value = 'failed'; }
        if (event.type === 'done' && resultType.value !== 'failed') {
          result.value ||= event.message || t('模型连接测试成功。');
          resultType.value = 'success';
        }
      });
      if (resultType.value === 'idle') resultType.value = 'success';
    }
    emit('tested');
  } catch (error) {
    result.value = errorText(error);
    resultType.value = 'failed';
  } finally { testing.value = false; }
}
</script>

<template>
  <aside class="group-test-pane">
    <h3 class="test-title"><n-icon size="20"><FlaskOutline /></n-icon>{{ t('modelGroup.testTitle') }}</h3>
    <p class="helper">{{ t('modelGroup.testHelp') }}</p>
    <n-select :value="modelId" :options="options" :placeholder="t('modelGroup.selectTestModel')" :disabled="!models.length || testing" @update:value="modelId = $event; emit('select', $event)" />
    <template v-if="model">
      <div class="model-summary"><span>{{ t('模型 ID') }}</span><strong>{{ model.modelName }}</strong></div>
      <div class="model-summary"><span>{{ t('能力') }}</span><strong>{{ model.capabilities.join(' · ') }}</strong></div>
      <n-input v-if="kind === 'chat' || kind === 'image'" v-model:value="prompt" type="textarea" :rows="4" :placeholder="t('modelGroup.testPrompt')" />
      <n-alert v-else type="info" :bordered="false">{{ kind === 'embedding' ? t('将调用 Embedding 接口并校验返回向量。') : t('将调用 Rerank 接口并校验排序结果。') }}</n-alert>
      <n-button type="primary" block :loading="testing" @click="run"><template #icon><n-icon><PlayOutline /></n-icon></template>{{ t('modelGroup.runTest') }}</n-button>
      <div v-if="result" class="test-result" :class="resultType">{{ result }}</div>
      <img v-if="imageUrl" class="test-image" :src="imageUrl" :alt="t('图片模型测试结果')" />
    </template>
    <n-empty v-else :description="t('modelGroup.noTestModel')" />
  </aside>
</template>

<style scoped>
.group-test-pane { display: flex; flex-direction: column; gap: 14px; min-width: 0; min-height: 0; overflow-y: auto; padding: 20px; border-left: 1px solid #e4eaf3; background: #f8faff; }
h3 { margin: 0; font-size: 16px; }
.test-title { display: flex; align-items: center; gap: 8px; color: #253a61; }.test-title .n-icon { color: #4774cb; }
.helper { margin: 0; color: #697789; font-size: 12px; }
.model-summary { display: flex; justify-content: space-between; gap: 12px; color: #65758b; font-size: 12px; }
.model-summary strong { color: #263954; text-align: right; overflow-wrap: anywhere; }
.test-result { white-space: pre-wrap; overflow-wrap: anywhere; padding: 12px; border-radius: 8px; background: #eef2fa; }
.test-result.success { background: #eaf7ee; }.test-result.failed { color: #af3131; background: #fff0f0; }
.test-image { display: block; max-width: 100%; border-radius: 8px; }
@media (max-width: 900px) { .group-test-pane { overflow: visible; border-left: 0; border-top: 1px solid #e4eaf3; } }
</style>
