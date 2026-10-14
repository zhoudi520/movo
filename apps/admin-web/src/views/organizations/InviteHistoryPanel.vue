<script setup lang="ts">
import { ref, watch } from 'vue';
import { useMessage } from 'naive-ui';
import { fetchOrgInviteHistory, revokeOrgInvite, type InviteHistoryItem } from '@/api/directory';
import { t } from '@/composables/i18n';
import InviteHistoryRow from './InviteHistoryRow.vue';
import InviteMemberDetail from './InviteMemberDetail.vue';

type DepartmentOption = { label: string; value: string };
const props = defineProps<{ open: boolean; refreshKey: number; roleNames: Record<string, string>; departments: DepartmentOption[] }>();
const emit = defineEmits<{ (event: 'close'): void }>();
const rows = ref<InviteHistoryItem[]>([]);
const selected = ref<InviteHistoryItem | null>(null);
const departmentId = ref<string | null>(null);
const statusFilter = ref<string | null>(null);
const page = ref(1);
const total = ref(0);
const loading = ref(false);
const message = useMessage();
const pageSize = 20;
let requestVersion = 0;

const statusOptions = [
  'active', 'expired', 'revoked', 'used',
].map(value => ({ label: t(`inviteHistory.status.${value}`), value }));

async function load() {
  const version = ++requestVersion;
  loading.value = true;
  try {
    const result = await fetchOrgInviteHistory(page.value, pageSize, departmentId.value || undefined, statusFilter.value || undefined);
    if (version !== requestVersion) return;
    rows.value = result.items;
    total.value = result.total;
  } catch { message.error(t('inviteHistory.loadFailed')); }
  finally { if (version === requestVersion) loading.value = false; }
}
watch(() => [props.open, props.refreshKey], () => { if (props.open) { selected.value = null; void load(); } }, { immediate: true });
watch([departmentId, statusFilter], () => {
  if (page.value !== 1) page.value = 1;
  else if (props.open) void load();
});
watch(page, () => { if (props.open) void load(); });

function departmentName(id: string | null) {
  return props.departments.find(option => option.value === id)?.label || t('inviteHistory.rootDepartment');
}
function roleName(id: string) {
  return props.roleNames[id] || id || t('inviteHistory.role');
}
function handleVisibility(value: boolean) {
  if (!value) emit('close');
}
function changePage(value: number) { page.value = value; }
async function copy(value: string) {
  try {
    await navigator.clipboard.writeText(value);
    message.success(t('inviteHistory.copied'));
  } catch { message.error(t('inviteHistory.copyFailed')); }
}
async function revoke(row: InviteHistoryItem) {
  try {
    await revokeOrgInvite(row.id);
    message.success(t('inviteHistory.revoked'));
    await load();
  } catch { message.error(t('inviteHistory.revokeFailed')); }
}
</script>

<template>
  <n-drawer :show="open" placement="right" width="min(920px, 100vw)" @update:show="handleVisibility">
    <n-drawer-content :title="t('inviteHistory.title')" closable>
      <div class="drawer-layout">
        <InviteMemberDetail v-if="selected" :invite="selected" :department-name="departmentName(selected.defaultDepartmentId)" :role-name="roleName(selected.primaryRoleId)" @back="selected = null" />
        <template v-else>
          <div class="history-filters">
            <n-select v-model:value="departmentId" :options="departments" clearable :placeholder="t('inviteHistory.allDepartments')" />
            <n-select v-model:value="statusFilter" :options="statusOptions" clearable :placeholder="t('inviteHistory.allStatuses')" />
            <n-button :loading="loading" @click="load">{{ t('inviteHistory.refresh') }}</n-button>
          </div>
          <div class="history-scroll">
            <n-spin :show="loading">
              <n-empty v-if="!rows.length && !loading" :description="t('inviteHistory.empty')" />
              <InviteHistoryRow v-for="row in rows" :key="row.id" :invite="row" :department-name="departmentName(row.defaultDepartmentId)" :role-name="roleName(row.primaryRoleId)" @select="selected = row" @copy="copy" @revoke="revoke(row)" />
            </n-spin>
          </div>
          <div class="history-footer">
            <span>{{ t('inviteHistory.total', { count: total }) }}</span>
            <n-pagination v-if="total > pageSize" :page="page" :page-size="pageSize" :item-count="total" @update:page="changePage" />
          </div>
        </template>
      </div>
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
.drawer-layout { display:flex; flex-direction:column; height:calc(100vh - 112px); min-height:0; }
.history-filters { display:flex; gap:10px; margin-bottom:12px; }
.history-filters :deep(.n-select) { min-width:0; flex:1; }
.history-scroll { flex:1; min-height:0; overflow-y:auto; }
.history-footer { flex:none; display:flex; justify-content:space-between; align-items:center; gap:12px; padding-top:12px; color:#64748b; font-size:13px; }
@media (max-width:650px) { .history-filters { flex-wrap:wrap; } .history-filters :deep(.n-select) { flex-basis:40%; } }
</style>
