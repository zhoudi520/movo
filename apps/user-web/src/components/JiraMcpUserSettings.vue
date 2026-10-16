<template>
  <n-card class="jira-card shell-card" :bordered="false" size="small">
    <template #header>
      <div class="jira-card-head">
        <span class="jira-title">{{ t('Jira 账号') }}</span>
        <n-tag v-if="settings?.configured" type="success" size="small" :bordered="false">{{ t('已绑定') }}</n-tag>
        <n-tag v-else size="small" :bordered="false">{{ t('未绑定（将使用企业默认）') }}</n-tag>
      </div>
    </template>
    <n-spin :show="loading">
      <n-form label-placement="top" :show-require-mark="false">
        <n-form-item :label="t('Jira 站点 URL')">
          <n-input v-model:value="form.jiraBaseUrl" :placeholder="t('例如 https://your-domain.atlassian.net')" />
        </n-form-item>
        <n-form-item :label="t('邮箱:API Token')">
          <n-input
            v-model:value="form.personalAccessToken"
            type="password"
            show-password-on="click"
            :placeholder="t('user@example.com:xxxx')"
          />
        </n-form-item>
        <n-space :size="10">
          <n-button type="primary" :loading="saving" @click="save">{{ t('保存') }}</n-button>
          <n-button :loading="saving" secondary @click="saveAndValidate">{{ t('保存并验证') }}</n-button>
          <n-button v-if="settings?.configured" tertiary type="warning" :loading="clearing" @click="clearBinding">
            {{ t('清除绑定') }}
          </n-button>
        </n-space>
        <p v-if="mcpOneLine" class="mcp-oneline" :title="mcpOneLine">{{ mcpOneLine }}</p>
        <p v-else-if="settings && !settings.mcpTool?.enabled" class="hint warn">
          {{ t('管理员尚未启用 Jira MCP 网关。') }}
        </p>
        <p class="hint">{{ t('未绑定时，调用组织 Jira 工具将使用管理员配置的企业默认账号。') }}</p>
      </n-form>
    </n-spin>
  </n-card>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  NButton,
  NCard,
  NForm,
  NFormItem,
  NInput,
  NSpace,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import {
  deleteMyJiraMcpSettings,
  fetchMyJiraMcpSettings,
  saveMyJiraMcpSettings,
  type JiraMcpUserSettings,
} from '../api/jiraMcp'
import { t } from '../composables/i18n'

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const clearing = ref(false)
const settings = ref<JiraMcpUserSettings | null>(null)
const form = reactive({
  jiraBaseUrl: '',
  personalAccessToken: '',
})

function applyFormFromSettings(data: JiraMcpUserSettings) {
  form.jiraBaseUrl = data.jiraBaseUrl || ''
  form.personalAccessToken = data.personalAccessToken || ''
}

const mcpOneLine = computed(() => {
  const mcp = settings.value?.mcpTool
  if (!mcp?.enabled) {
    return ''
  }
  const endpoint = String(mcp.endpoint || '').trim()
  if (!endpoint) {
    return ''
  }
  return `${t('MCP URL')}: ${endpoint} · ${t('鉴权')}: ${t('无')}`
})

async function load() {
  loading.value = true
  try {
    settings.value = await fetchMyJiraMcpSettings()
    applyFormFromSettings(settings.value)
  } catch {
    message.error(t('加载 Jira 设置失败'))
  } finally {
    loading.value = false
  }
}

async function saveInternal(validateJira: boolean) {
  saving.value = true
  try {
    settings.value = await saveMyJiraMcpSettings({
      jiraBaseUrl: form.jiraBaseUrl.trim(),
      personalAccessToken: form.personalAccessToken.trim(),
      validateJira,
    })
    applyFormFromSettings(settings.value)
    message.success(validateJira ? t('已保存并通过 Jira 验证') : t('已保存'))
  } catch (err: unknown) {
    const detail = err instanceof Error ? err.message : String(err)
    message.error(detail || t('保存失败'))
  } finally {
    saving.value = false
  }
}

function save() {
  return saveInternal(false)
}

function saveAndValidate() {
  return saveInternal(true)
}

async function clearBinding() {
  clearing.value = true
  try {
    settings.value = await deleteMyJiraMcpSettings()
    form.jiraBaseUrl = ''
    form.personalAccessToken = ''
    message.success(t('已清除个人绑定'))
  } catch {
    message.error(t('清除失败'))
  } finally {
    clearing.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<style scoped>
.jira-card {
  margin-bottom: 16px;
}
.jira-card-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.jira-title {
  font-weight: 600;
}
.mcp-oneline {
  margin: 10px 0 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--n-text-color-2);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--n-text-color-3);
}
.hint.warn {
  color: var(--n-warning-color);
}
</style>
