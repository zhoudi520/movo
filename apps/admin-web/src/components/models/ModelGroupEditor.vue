<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useMessage } from 'naive-ui';
import { t } from '@/composables/i18n';
import { createModelGroup, deleteModelGroup, updateModelGroup, type ModelGroupItem, type ModelGroupPayload, type ModelInstanceItem, type ModelProviderItem } from '@/api/models';
import adminProductUiExtension from '@movo-admin-product-extension';
import { providerLabel } from './providerLabels';
import { modelApiErrorText } from './modelApiError';
import ModelGroupMemberRow from './ModelGroupMemberRow.vue';
import ModelGroupTestPane from './ModelGroupTestPane.vue';
import LinkOutline from '@vicons/ionicons5/es/LinkOutline';
import AlbumsOutline from '@vicons/ionicons5/es/AlbumsOutline';
import AddOutline from '@vicons/ionicons5/es/AddOutline';
import SaveOutline from '@vicons/ionicons5/es/SaveOutline';
import TrashOutline from '@vicons/ionicons5/es/TrashOutline';

const props = defineProps<{ show: boolean; group: ModelGroupItem | null; providers: ModelProviderItem[]; models: ModelInstanceItem[]; selectedModelId?: string }>();
const emit = defineEmits<{ (event: 'update:show', value: boolean): void; (event: 'saved', group: ModelGroupItem): void; (event: 'deleted'): void; (event: 'member-changed'): void }>();
const message = useMessage();
const extension = adminProductUiExtension.modelGroupAccess;
const saving = ref(false);
const accessLoading = ref(false);
const access = ref<unknown>(extension?.createValue());
const form = ref<ModelGroupPayload>({ name: '', providerId: '', baseUrl: '', apiVersion: '', apiKey: '', status: 'active' });
const providerOptions = computed(() => props.providers.filter((item) => item.status === 'active').map((item) => ({ label: providerLabel(item), value: item.id })));
const provider = computed(() => props.providers.find((item) => item.id === form.value.providerId));
const savedProvider = computed(() => props.providers.find((item) => item.id === props.group?.providerId));
const memberModels = computed(() => props.models.filter((item) => item.groupId === props.group?.id));
const draftId = ref(0);
const showDraft = ref(false);
const testModelId = ref('');

watch(() => props.show, async (show) => {
  if (!show) return;
  showDraft.value = false;
  testModelId.value = props.selectedModelId || '';
  form.value = props.group
    ? { name: props.group.name, providerId: props.group.providerId, baseUrl: props.group.baseUrl, apiVersion: props.group.apiVersion, apiKey: '', status: props.group.status }
    : { name: '', providerId: props.providers[0]?.id || '', baseUrl: props.providers[0]?.defaultBaseUrl || '', apiVersion: '', apiKey: '', status: 'active' };
  access.value = extension?.createValue();
  if (props.group && extension) {
    accessLoading.value = true;
    try { access.value = await extension.load(props.group.id); }
    catch (error) { message.error(modelApiErrorText(error)); }
    finally { accessLoading.value = false; }
  }
});

function selectProvider(id: string) {
  form.value.providerId = id;
  form.value.baseUrl = props.providers.find((item) => item.id === id)?.defaultBaseUrl || '';
}

async function save() {
  const warning = extension?.validate?.(access.value);
  if (warning) { message.warning(t(warning)); return; }
  if (!form.value.name.trim() || !form.value.providerId || !form.value.baseUrl.trim() || (!props.group && !form.value.apiKey.trim())) {
    message.warning(t('modelGroup.required')); return;
  }
  if (provider.value?.providerType === 'azure_openai' && !form.value.apiVersion.trim()) {
    message.warning(t('modelGroup.azureVersionRequired')); return;
  }
  saving.value = true;
  let newlyCreated: ModelGroupItem | null = null;
  try {
    const payload = { ...form.value, name: form.value.name.trim(), baseUrl: form.value.baseUrl.trim(), apiKey: form.value.apiKey.trim() };
    const saved = props.group ? await updateModelGroup(props.group.id, payload) : await createModelGroup(payload);
    if (!props.group) newlyCreated = saved;
    if (extension) await extension.save(saved.id, access.value);
    emit('saved', saved);
    message.success(t('modelGroup.saved'));
  } catch (error) {
    if (newlyCreated) await deleteModelGroup(newlyCreated.id).catch(() => undefined);
    message.error(modelApiErrorText(error));
  }
  finally { saving.value = false; }
}

async function remove() {
  if (!props.group || memberModels.value.length || !window.confirm(t('modelGroup.deleteConfirm'))) return;
  saving.value = true;
  try { await deleteModelGroup(props.group.id); emit('deleted'); emit('update:show', false); }
  catch (error) { message.error(modelApiErrorText(error)); }
  finally { saving.value = false; }
}

function memberSaved(model: ModelInstanceItem) {
  showDraft.value = false;
  testModelId.value = model.id;
  emit('member-changed');
}

function memberDeleted() {
  testModelId.value = '';
  emit('member-changed');
}
</script>

<template>
  <n-modal :show="show" preset="card" :title="group ? t('modelGroup.edit') : t('modelGroup.create')" class="group-editor-modal" style="width: min(1320px, 96vw)" @update:show="emit('update:show', $event)">
    <div class="group-editor-layout">
      <div class="group-editor-main">
        <section class="settings-section">
          <h3 class="section-title"><n-icon size="20"><LinkOutline /></n-icon>{{ t('modelGroup.connection') }}</h3>
          <n-form label-placement="top">
            <div class="settings-grid">
              <n-form-item :label="t('modelGroup.name')"><n-input v-model:value="form.name" /></n-form-item>
              <n-form-item :label="t('modelGroup.provider')"><n-select :value="form.providerId" :options="providerOptions" :disabled="Boolean(group && memberModels.length)" @update:value="selectProvider" /></n-form-item>
              <n-form-item label="Base URL"><n-input v-model:value="form.baseUrl" /></n-form-item>
              <n-form-item v-if="provider?.providerType === 'azure_openai'" label="API Version"><n-input v-model:value="form.apiVersion" /></n-form-item>
              <n-form-item label="API Key"><n-input v-model:value="form.apiKey" type="password" show-password-on="click" :placeholder="group?.apiKeyMasked || t('modelGroup.keyPlaceholder')" /></n-form-item>
              <n-form-item :label="t('modelGroup.status')"><n-select v-model:value="form.status" :options="[{ label: t('modelGroup.active'), value: 'active' }, { label: t('modelGroup.disabled'), value: 'disabled' }]" /></n-form-item>
            </div>
            <n-spin v-if="extension" :show="accessLoading"><component :is="extension.component" v-model="access" /></n-spin>
          </n-form>
          <div class="settings-actions">
            <n-button v-if="group" type="error" tertiary :disabled="memberModels.length > 0" @click="remove"><template #icon><n-icon><TrashOutline /></n-icon></template>{{ t('modelGroup.delete') }}</n-button>
            <n-button type="primary" :loading="saving" @click="save"><template #icon><n-icon><SaveOutline /></n-icon></template>{{ t('modelGroup.saveConnection') }}</n-button>
          </div>
        </section>
        <section class="members-section">
          <div class="section-head"><div><h3 class="section-title"><n-icon size="20"><AlbumsOutline /></n-icon>{{ t('modelGroup.members') }}</h3><p>{{ t('modelGroup.membersHelp') }}</p></div><n-button type="primary" secondary :disabled="!group || showDraft" @click="draftId++; showDraft = true"><template #icon><n-icon><AddOutline /></n-icon></template>{{ t('modelGroup.addModel') }}</n-button></div>
          <n-alert v-if="!group" type="info" :bordered="false">{{ t('modelGroup.saveFirst') }}</n-alert>
          <div v-else class="member-list">
            <ModelGroupMemberRow v-for="model in memberModels" :key="model.id" :group="group" :provider="savedProvider" :model="model" :expanded="selectedModelId === model.id" @saved="memberSaved" @deleted="memberDeleted" @select="testModelId = $event" />
            <ModelGroupMemberRow v-if="showDraft" :key="`draft-${draftId}`" :group="group" :provider="savedProvider" @saved="memberSaved" @cancel="showDraft = false" />
            <n-empty v-if="!memberModels.length && !showDraft" :description="t('modelGroup.empty')" />
          </div>
        </section>
      </div>
      <ModelGroupTestPane :models="memberModels" :selected-id="testModelId" @select="testModelId = $event" @tested="emit('member-changed')" />
    </div>
    <template #footer>
      <div class="editor-footer">
        <span>{{ t('modelGroup.testHelp') }}</span>
        <n-button @click="emit('update:show', false)">{{ t('modelGroup.close') }}</n-button>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.group-editor-layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; height: min(72dvh, 760px); max-height: calc(100dvh - 170px); min-height: 0; margin: -8px -24px; overflow: hidden; }
.group-editor-main { min-height: 0; overflow-y: auto; overscroll-behavior: contain; scrollbar-gutter: stable; padding: 20px 24px 28px; }
.group-editor-main::-webkit-scrollbar { width: 9px; }
.group-editor-main::-webkit-scrollbar-thumb { border: 2px solid transparent; border-radius: 8px; background: #b9c5d8; background-clip: padding-box; }
.group-editor-main::-webkit-scrollbar-track { background: #f5f7fb; }
.settings-section, .members-section { padding: 0 0 22px; }
.members-section { border-top: 1px solid #e4eaf3; padding-top: 22px; }
h3 { margin: 0 0 14px; font-size: 16px; }
.section-title { display: flex; align-items: center; gap: 8px; color: #253a61; }
.section-title .n-icon { color: #4774cb; }
.settings-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 14px; }
.settings-actions, .section-head, .editor-footer { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.settings-actions { justify-content: flex-end; }
.settings-actions > :first-child:not(:last-child) { margin-right: auto; }
.section-head h3 { margin-bottom: 4px; }.section-head p, .editor-footer span { margin: 0; color: #718097; font-size: 12px; }
.member-list { display: grid; gap: 10px; margin-top: 16px; }
@media (max-width: 900px) { .group-editor-layout { display: block; overflow-y: auto; }.group-editor-main { overflow: visible; }.settings-grid { grid-template-columns: 1fr; } }
</style>
