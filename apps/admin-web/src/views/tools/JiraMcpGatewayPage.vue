<template>
  <div class="page-stack jira-gateway-page">
    <n-card :bordered="false" class="shell-card">
      <template #header>
        <div class="page-header">
          <div>
            <div class="page-title">{{ t('Jira MCP 网关') }}</div>
            <div class="page-subtitle">{{ t('配置 Jira 凭证与网关密钥，保存后约 15 秒内自动生效（无需重启容器）。') }}</div>
          </div>
          <n-space>
            <n-button @click="router.push({ name: 'Tools' })">{{ t('返回工具列表') }}</n-button>
            <n-button v-if="form.linkedToolId" @click="openLinkedTool">{{ t('打开关联 MCP 工具') }}</n-button>
          </n-space>
        </div>
      </template>

      <n-spin :show="loading">
        <n-form label-placement="top" :model="form">
          <n-grid :cols="2" :x-gap="18">
            <n-form-item-gi :span="2" :label="t('启用网关配置')">
              <n-switch v-model:value="form.enabled" />
            </n-form-item-gi>
            <n-form-item-gi :span="2" :label="t('Jira 站点 URL')">
              <n-input v-model:value="form.jiraBaseUrl" placeholder="https://your-domain.atlassian.net" />
            </n-form-item-gi>
            <n-form-item-gi :span="2" :label="t('Jira 凭证（邮箱:API Token）')">
              <n-input
                v-model:value="form.personalAccessToken"
                type="password"
                show-password-on="click"
                :placeholder="settings.personalAccessTokenMasked ? t('留空表示不修改') : t('user@company.com:ATATT...')"
              />
            </n-form-item-gi>
            <n-form-item-gi :span="2" :label="t('网关密钥（Bearer）')">
              <n-input-group>
                <n-input
                  v-model:value="form.gatewayKey"
                  type="password"
                  show-password-on="click"
                  :placeholder="settings.gatewayKeyMasked ? t('留空表示不修改或自动生成') : t('保存时可自动生成')"
                />
                <n-button @click="generateGatewayKey">{{ t('生成') }}</n-button>
              </n-input-group>
            </n-form-item-gi>
            <n-form-item-gi :span="2" :label="t('MOVO 访问网关方式')">
              <n-radio-group v-model:value="form.mcpToolEndpointPreset">
                <n-space vertical>
                  <n-radio value="docker_internal">{{ t('chat-api 在 Docker Compose 内（推荐）') }}</n-radio>
                  <n-radio value="host_loopback">{{ t('chat-api 在本机运行（127.0.0.1:8766）') }}</n-radio>
                </n-space>
              </n-radio-group>
              <div class="hint">{{ t('将写入外部 MCP 工具地址') }}: {{ resolvedEndpoint }}</div>
            </n-form-item-gi>
          </n-grid>

          <n-space :size="12" style="margin-top: 12px">
            <n-button type="primary" :loading="saving" @click="save">{{ t('保存') }}</n-button>
            <n-button :loading="testingJira" @click="testJira">{{ t('测试 Jira') }}</n-button>
            <n-button :loading="testingMcp" @click="testMcp">{{ t('测试 MCP 网关') }}</n-button>
          </n-space>

          <n-alert v-if="settings.configVersion" type="info" style="margin-top: 16px" :bordered="false">
            {{ t('当前配置版本') }}: {{ settings.configVersion }}
            <span v-if="settings.updatedAt"> · {{ settings.updatedAt }}</span>
          </n-alert>
        </n-form>
      </n-spin>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import {
  NAlert,
  NButton,
  NCard,
  NForm,
  NFormItemGi,
  NGrid,
  NInput,
  NInputGroup,
  NRadio,
  NRadioGroup,
  NSpace,
  NSpin,
  NSwitch,
  useMessage,
} from 'naive-ui';
import {
  fetchJiraMcpGatewaySettings,
  saveJiraMcpGatewaySettings,
  testJiraMcpGatewayJira,
  testJiraMcpGatewayMcp,
  type JiraMcpGatewaySettings,
  type McpEndpointPreset,
} from '@/api/jira-mcp-gateway';
import { t } from '@/composables/i18n';

const defaultEndpointPresets: Record<McpEndpointPreset, string> = {
  docker_internal: 'http://jira-mcp-gateway:8766/mcp',
  host_loopback: 'http://127.0.0.1:8766/mcp',
};

const router = useRouter();
const message = useMessage();

const loading = ref(false);
const saving = ref(false);
const testingJira = ref(false);
const testingMcp = ref(false);

const settings = reactive<JiraMcpGatewaySettings>({
  mainId: 'default',
  enabled: true,
  jiraBaseUrl: '',
  personalAccessTokenMasked: '',
  gatewayKeyMasked: '',
  configVersion: 0,
  mcpToolEndpointPreset: 'docker_internal',
  linkedToolId: '',
  resolvedMcpEndpoint: '',
  updatedAt: '',
  endpointPresets: {
    docker_internal: 'http://jira-mcp-gateway:8766/mcp',
    host_loopback: 'http://127.0.0.1:8766/mcp',
  },
});

const form = reactive({
  enabled: true,
  jiraBaseUrl: '',
  personalAccessToken: '',
  gatewayKey: '',
  mcpToolEndpointPreset: 'docker_internal' as McpEndpointPreset,
  linkedToolId: '',
});

const resolvedEndpoint = computed(() => {
  const presets = settings.endpointPresets ?? defaultEndpointPresets;
  return presets[form.mcpToolEndpointPreset] || settings.resolvedMcpEndpoint;
});

function applySettings(data: JiraMcpGatewaySettings) {
  Object.assign(settings, data);
  form.enabled = data.enabled;
  form.jiraBaseUrl = data.jiraBaseUrl;
  form.mcpToolEndpointPreset = data.mcpToolEndpointPreset || 'docker_internal';
  form.linkedToolId = data.linkedToolId || '';
  form.personalAccessToken = '';
  form.gatewayKey = '';
}

async function load() {
  loading.value = true;
  try {
    applySettings(await fetchJiraMcpGatewaySettings());
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('加载失败'));
  } finally {
    loading.value = false;
  }
}

function generateGatewayKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  form.gatewayKey = btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function save() {
  saving.value = true;
  try {
    const saved = await saveJiraMcpGatewaySettings({
      enabled: form.enabled,
      jiraBaseUrl: form.jiraBaseUrl.trim(),
      personalAccessToken: form.personalAccessToken.trim(),
      gatewayKey: form.gatewayKey.trim(),
      mcpToolEndpointPreset: form.mcpToolEndpointPreset,
    });
    applySettings(saved);
    message.success(t('已保存，网关将在轮询周期内热重载'));
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('保存失败'));
  } finally {
    saving.value = false;
  }
}

async function testJira() {
  testingJira.value = true;
  try {
    await testJiraMcpGatewayJira({
      jiraBaseUrl: form.jiraBaseUrl.trim(),
      personalAccessToken: form.personalAccessToken.trim(),
    });
    message.success(t('Jira 连接成功'));
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('Jira 测试失败'));
  } finally {
    testingJira.value = false;
  }
}

async function testMcp() {
  testingMcp.value = true;
  try {
    await testJiraMcpGatewayMcp({ gatewayKey: form.gatewayKey.trim() });
    message.success(t('MCP 网关连接成功'));
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('MCP 测试失败'));
  } finally {
    testingMcp.value = false;
  }
}

function openLinkedTool() {
  if (!form.linkedToolId) return;
  router.push({ name: 'ToolEdit', params: { id: form.linkedToolId } });
}

onMounted(load);
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
}
.page-subtitle {
  margin-top: 4px;
  color: var(--n-text-color-3);
  font-size: 13px;
}
.hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--n-text-color-3);
}
</style>
