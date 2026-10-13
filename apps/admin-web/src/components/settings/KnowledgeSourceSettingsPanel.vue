<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { NAlert, NCollapse, NCollapseItem, useMessage } from 'naive-ui';
import { discoverMcpTools, fetchTools, testTool, type ExternalToolItem } from '@/api/tools';
import { fetchKnowledgeSource, saveKnowledgeSource, type KnowledgeSourceSettings } from '@/api/knowledge-source';
import { t } from '@/composables/i18n';
import { previewKnowledgeResult } from './knowledgeSourcePreview';
import { mappingFieldOptions, type MappingKey } from './knowledgeFieldOptions';
import KnowledgeFieldSelect from './KnowledgeFieldSelect.vue';
import { questionInputOptions as toolQuestionInputOptions, selectedQuestionInput } from './knowledgeInputOptions';
import { retrievalOptions as buildRetrievalOptions } from './knowledgeRetrievalOptions';

const emit = defineEmits<{ (e: 'mode-change', value: 'movo' | 'external'): void }>();
const message = useMessage();
const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const refreshingFields = ref(false);
const testQuery = ref('');
const testOutcome = ref<Record<string, any> | null>(null);
const testError = ref('');
const tools = ref<ExternalToolItem[]>([]);
const savedSnapshot = ref('');
const loadError = ref('');
const hasUnsavedChanges = computed(() => Boolean(savedSnapshot.value) && JSON.stringify(form) !== savedSnapshot.value);
const form = reactive<KnowledgeSourceSettings>({
  mode: 'movo', displayName: '', toolId: '', mcpToolName: '', queryArgument: '',
  mapping: { answerPath: '', sourcesPath: '', titlePath: '', documentUrlPath: '', snippetPath: '' },
});
const testResult = computed(() => testOutcome.value ? previewKnowledgeResult(testOutcome.value, form) : null);
const emptyMapping: KnowledgeSourceSettings['mapping'] = {
  answerPath: '', sourcesPath: '', titlePath: '', documentUrlPath: '', snippetPath: '',
};
const selectedTool = computed(() => tools.value.find((item) => item.id === form.toolId));
const retrievalOptions = computed(() => buildRetrievalOptions(tools.value));
const selectedRetrieval = computed(() => retrievalOptions.value.find((item) => item.toolId === form.toolId && item.mcpToolName === form.mcpToolName));
const questionInputOptions = computed(() => toolQuestionInputOptions(selectedTool.value, form.mcpToolName));
const fieldChoices = (key: MappingKey) => mappingFieldOptions(selectedTool.value, form.mcpToolName, testResult.value?.body, form.mapping.sourcesPath, key);

async function refreshFields() {
  if (selectedTool.value?.type !== 'mcp') return;
  refreshingFields.value = true;
  try {
    const result = await discoverMcpTools(form.toolId);
    if (!result.success) throw new Error(result.message || t('knowledgeSource.refreshFieldsFailed'));
    tools.value = await fetchTools();
    form.queryArgument = selectedQuestionInput(form.queryArgument, questionInputOptions.value);
    testOutcome.value = null;
    testError.value = '';
    message.success(t('knowledgeSource.fieldsRefreshed'));
  } catch (error) {
    message.error(error instanceof Error ? error.message : String(error));
  } finally {
    refreshingFields.value = false;
  }
}

async function load() {
  loading.value = true;
  loadError.value = '';
  try {
    const [saved, available] = await Promise.all([fetchKnowledgeSource(), fetchTools()]);
    Object.assign(form, saved);
    Object.assign(form.mapping, saved.mapping);
    tools.value = available;
    savedSnapshot.value = JSON.stringify(form);
    if (form.mode === 'external') form.queryArgument = selectedQuestionInput(form.queryArgument, questionInputOptions.value);
    emit('mode-change', form.mode);
  } catch (error) {
    loadError.value = t('knowledgeSource.loadFailed');
    message.error(String(error));
  } finally {
    loading.value = false;
  }
}

function changeMode(value: 'movo' | 'external') {
  form.mode = value;
  testOutcome.value = null;
  emit('mode-change', value);
}

function onRetrievalChange(value: string | null) {
  const next = retrievalOptions.value.find((item) => item.value === value);
  if (form.toolId === (next?.toolId || '') && form.mcpToolName === (next?.mcpToolName || '')) return;
  form.toolId = next?.toolId || '';
  form.mcpToolName = next?.mcpToolName || '';
  form.queryArgument = selectedQuestionInput('', questionInputOptions.value);
  Object.assign(form.mapping, emptyMapping);
  testOutcome.value = null;
}

function onSourcesPathChange(path: string) {
  if (form.mapping.sourcesPath === path) return;
  form.mapping.sourcesPath = path;
  for (const key of ['titlePath', 'snippetPath', 'documentUrlPath'] as const) form.mapping[key] = '';
}

async function save(): Promise<boolean> {
  if (loadError.value || !savedSnapshot.value) {
    message.error(t('knowledgeSource.loadFailed'));
    return false;
  }
  if (!hasUnsavedChanges.value) return true;
  if (form.mode === 'external' && (!selectedRetrieval.value || !questionInputOptions.value.some((option) => option.value === form.queryArgument))) {
    message.error(t('knowledgeSource.chooseQueryField'));
    return false;
  }
  saving.value = true;
  try {
    const saved = await saveKnowledgeSource(JSON.parse(JSON.stringify(form)));
    Object.assign(form, saved);
    Object.assign(form.mapping, saved.mapping);
    savedSnapshot.value = JSON.stringify(form);
    emit('mode-change', saved.mode);
    message.success(t('knowledgeSource.saved'));
    return true;
  } catch (error) {
    message.error(String(error));
    return false;
  } finally {
    saving.value = false;
  }
}

defineExpose({ save, load, hasUnsavedChanges, saving });

async function runTest() {
  if (!selectedTool.value || !testQuery.value.trim()) return;
  if (!selectedRetrieval.value || !questionInputOptions.value.some((option) => option.value === form.queryArgument)) {
    message.error(t('knowledgeSource.chooseQueryField'));
    return;
  }
  testing.value = true;
  testOutcome.value = null;
  testError.value = '';
  try {
    const argument = form.queryArgument;
    const location = questionInputOptions.value.find((option) => option.value === argument)?.location || 'query';
    const input = selectedTool.value.type === 'mcp'
      ? { toolName: form.mcpToolName, arguments: { [argument]: testQuery.value.trim() } }
      : { [location]: { [argument]: testQuery.value.trim() } };
    const outcome = await testTool(form.toolId, input, Number(selectedTool.value.config?.timeoutSeconds || 15));
    if (!outcome.success) throw new Error(String(outcome.message || t('knowledgeSource.testFailed')));
    testOutcome.value = outcome;
  } catch (error) {
    testError.value = error instanceof Error ? error.message : String(error);
  } finally {
    testing.value = false;
  }
}

onMounted(load);
</script>

<template>
  <n-spin :show="loading">
    <n-alert v-if="loadError" type="error" class="load-error">{{ loadError }}</n-alert>
    <section class="source-layout" :class="{ 'source-layout--movo': form.mode === 'movo' }">
      <div class="source-card">
        <div class="section-heading"><span class="step-number">1</span><div><h3>{{ t('knowledgeSource.title') }}</h3><p class="help">{{ t('knowledgeSource.description') }}</p></div></div>
        <n-radio-group :value="form.mode" @update:value="changeMode">
          <n-space><n-radio-button value="movo">{{ t('knowledgeSource.movo') }}</n-radio-button><n-radio-button value="external">{{ t('knowledgeSource.external') }}</n-radio-button></n-space>
        </n-radio-group>
        <template v-if="form.mode === 'external'">
          <div class="section-divider" />
          <div class="section-heading"><span class="step-number">2</span><div><h3>{{ t('knowledgeSource.connectionTitle') }}</h3><p class="help">{{ t('knowledgeSource.connectionHelp') }}</p></div></div>
          <n-form label-placement="top" class="source-form">
            <n-form-item :label="t('knowledgeSource.tool')" required>
              <div class="retrieval-tool-row">
                <n-select :value="selectedRetrieval?.value || null" :options="retrievalOptions" :placeholder="t('knowledgeSource.chooseRetrievalTool')" filterable @update:value="onRetrievalChange" />
                <n-button v-if="selectedTool?.type === 'mcp'" :loading="refreshingFields" @click="refreshFields">{{ t('knowledgeSource.refreshFields') }}</n-button>
              </div>
            </n-form-item>
            <div class="field-grid"><n-form-item :label="t('knowledgeSource.name')" required><n-input v-model:value="form.displayName" /></n-form-item>
            <n-form-item :label="t('knowledgeSource.queryField')" required>
              <n-select v-model:value="form.queryArgument" :options="questionInputOptions" :placeholder="t('knowledgeSource.chooseQueryField')" :disabled="!selectedRetrieval || !questionInputOptions.length" />
            </n-form-item></div>
            <p v-if="selectedRetrieval && !questionInputOptions.length" class="help">{{ t('knowledgeSource.noQueryFields') }}</p>
          </n-form>
          <n-alert type="info" :show-icon="false" class="access-note">{{ t('knowledgeSource.accessHelp') }}</n-alert>
          <div class="section-divider" />
          <div class="section-heading"><span class="step-number">3</span><div><h3>{{ t('knowledgeSource.mapping') }}</h3><p class="help">{{ t('knowledgeSource.chooseFieldHelp') }}</p></div></div>
          <n-form label-placement="top" class="source-form">
            <KnowledgeFieldSelect v-model:value="form.mapping.answerPath" :label="t('knowledgeSource.answerPath')" :options="fieldChoices('answerPath')" required />
            <div class="source-mapping-group">
              <KnowledgeFieldSelect :value="form.mapping.sourcesPath" :label="t('knowledgeSource.sourcesPath')" :options="fieldChoices('sourcesPath')" @update:value="onSourcesPathChange" />
              <div v-if="form.mapping.sourcesPath" class="source-item-fields">
                <h4>{{ t('knowledgeSource.sourceItemFields') }}</h4>
                <p class="help">{{ t('knowledgeSource.sourceItemHelp') }}</p>
                <div class="field-grid">
                  <KnowledgeFieldSelect v-model:value="form.mapping.titlePath" :label="t('knowledgeSource.titlePath')" :options="fieldChoices('titlePath')" />
                  <KnowledgeFieldSelect v-model:value="form.mapping.snippetPath" :label="t('knowledgeSource.snippetPath')" :options="fieldChoices('snippetPath')" />
                  <div class="document-link-field"><KnowledgeFieldSelect v-model:value="form.mapping.documentUrlPath" :label="t('knowledgeSource.documentUrlPath')" :options="fieldChoices('documentUrlPath')" /></div>
                </div>
              </div>
            </div>
            <p class="help">{{ t('knowledgeSource.documentLinkHelp') }}</p>
          </n-form>
        </template>
        <n-alert v-else type="info" :show-icon="false" class="access-note">{{ t('knowledgeSource.movoHelp') }}</n-alert>
      </div>

      <div v-if="form.mode === 'external'" class="source-card test-card">
        <div class="section-heading"><span class="step-number">4</span><div><h3>{{ t('knowledgeSource.testTitle') }}</h3><p class="help">{{ t('knowledgeSource.testHelp') }}</p></div></div>
        <div class="test-row"><n-input v-model:value="testQuery" :placeholder="t('knowledgeSource.testQuery')" @keyup.enter="runTest" />
          <n-button type="primary" :disabled="!selectedRetrieval || !testQuery.trim() || !form.queryArgument" :loading="testing" @click="runTest">{{ t('knowledgeSource.test') }}</n-button></div>
        <n-alert v-if="testError" type="error" :show-icon="false">{{ testError }}</n-alert>
        <n-alert v-if="testResult && form.mapping.answerPath && !testResult.answer" type="warning" :show-icon="false">{{ t('knowledgeSource.answerMissing') }}</n-alert>
        <template v-if="testResult">
          <div class="result-label">{{ t('knowledgeSource.parsedAnswer') }}</div>
          <p class="answer">{{ testResult.answer || t('knowledgeSource.chooseAnswerAfterTest') }}</p>
          <div class="result-label">{{ t('knowledgeSource.sourcesCount', { count: testResult.sources.length }) }}</div>
          <div v-for="(source, index) in testResult.sources" :key="index" class="source-result">
            <strong>{{ source.title || form.displayName }}</strong>
            <small v-if="source.snippet">{{ source.snippet }}</small>
            <small v-if="source.documentUrl">{{ t('knowledgeSource.documentAvailable') }}</small>
          </div>
          <n-collapse><n-collapse-item :title="t('knowledgeSource.rawResponse')"><pre>{{ JSON.stringify(testResult.body, null, 2) }}</pre></n-collapse-item></n-collapse>
        </template>
        <div v-else class="test-empty">{{ t('knowledgeSource.testEmpty') }}</div>
      </div>
    </section>
  </n-spin>
</template>

<style scoped>
.source-layout{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(360px,.9fr);gap:20px;margin-bottom:24px;align-items:start}
.source-layout--movo{grid-template-columns:minmax(0,1fr)}
.source-card{min-width:0;border:1px solid #dbe3ef;border-radius:16px;padding:26px;background:#fff;color:#172033;box-shadow:0 4px 18px rgba(31,45,78,.04)}
.section-heading{display:flex;align-items:flex-start;gap:12px;margin-bottom:18px}.section-heading h3{font-size:17px;font-weight:650;margin:0 0 4px}.help{color:#68768c;font-size:13px;line-height:1.6;margin:0}.step-number{display:grid;place-items:center;flex:none;width:28px;height:28px;border-radius:8px;background:#e9f0ff;color:#2757bc;font-weight:700;font-size:13px}
.section-divider{height:1px;background:#e8edf4;margin:28px 0}.source-form :deep(.n-form-item){margin-bottom:12px}.field-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}.access-note{margin-top:16px}.source-form .help{margin-top:10px}
.source-mapping-group{margin-top:18px;border:1px solid #dbe3ef;border-radius:12px;padding:16px;background:#f8faff}.source-mapping-group :deep(.n-form-item:last-child){margin-bottom:0}.source-item-fields{margin-top:16px;padding:16px 0 0 16px;border-top:1px solid #dbe3ef;border-left:3px solid #8fb1fb}.source-item-fields h4{margin:0;font-size:14px;font-weight:650}.source-item-fields>.help{margin:4px 0 14px}.source-item-fields .field-grid{margin-left:0}
.document-link-field{grid-column:1/-1}
.retrieval-tool-row{display:flex;gap:8px;width:100%}.retrieval-tool-row .n-select{min-width:0;flex:1}.retrieval-tool-row .n-button{flex:none}
.test-card{position:sticky;top:20px;display:flex;flex-direction:column;gap:12px}.test-row{display:flex;gap:10px}.test-row .n-button{flex:none}.test-empty{display:grid;place-items:center;min-height:190px;border:1px dashed #d5deed;border-radius:12px;color:#8090a6;font-size:13px;text-align:center;padding:20px}.result-label{font-weight:600;font-size:13px;margin-top:10px}.answer{white-space:pre-wrap;line-height:1.6;border-radius:10px;background:#f5f8fd;padding:14px}.source-result{border:1px solid #e5e7eb;border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:4px;word-break:break-word}.source-result small{color:#748094}pre{white-space:pre-wrap;word-break:break-word;max-height:320px;overflow:auto}
:global(html.dark) .source-card{background:#171e2b;color:#e8edf5;border-color:#344054}
:global(html.dark) .source-mapping-group{background:#202b3b;border-color:#344054}:global(html.dark) .source-item-fields{border-top-color:#344054;border-left-color:#5b80c7}
:global(html.dark) .source-result,:global(html.dark) .test-empty{border-color:#344054}:global(html.dark) .answer{background:#202b3b}:global(html.dark) .section-divider{background:#344054}
@media(max-width:1100px){.source-layout{grid-template-columns:1fr}.test-card{position:static}}@media(max-width:640px){.field-grid{grid-template-columns:1fr}.source-card{padding:18px}.test-row,.retrieval-tool-row{flex-direction:column}}
</style>
