<template>
  <n-button secondary class="scope-trigger" @click="open">
    {{ t('directoryScope.scope') }}: {{ modelValue.level === 'organization' ? t('directoryScope.all') : modelValue.name }}
  </n-button>
  <n-modal v-model:show="visible" preset="card" :title="t('directoryScope.title')" class="scope-modal" :mask-closable="false">
    <div class="scope-modes">
      <n-button v-for="level in levels" :key="level" :type="draft.level === level ? 'primary' : 'default'" :secondary="draft.level !== level" @click="setLevel(level)">
        {{ t(`directoryScope.${level}`) }}
      </n-button>
    </div>
    <p v-if="draft.level === 'organization'" class="scope-hint">{{ t('directoryScope.allHint') }}</p>
    <div v-else class="scope-content">
      <div class="scope-departments">
        <n-input v-model:value="departmentSearch" clearable :placeholder="t('directoryScope.searchDepartment')" />
        <n-spin :show="departmentsLoading">
          <div class="scope-tree">
            <n-tree
              :data="treeOptions"
              :pattern="departmentSearch"
              :show-irrelevant-nodes="false"
              :selected-keys="selectedDepartmentId ? [selectedDepartmentId] : []"
              block-line
              virtual-scroll
              :style="{ height: '100%' }"
              @update:selected-keys="selectDepartment"
            />
          </div>
        </n-spin>
        <n-text v-if="departmentError" type="error">{{ t('directoryScope.loadFailed') }}</n-text>
      </div>
      <div v-if="draft.level === 'user'" class="scope-users">
        <n-input v-model:value="userSearch" clearable :placeholder="t('directoryScope.searchUser')" />
        <n-spin :show="usersLoading">
          <div class="scope-user-list">
            <button v-for="user in users" :key="user.id" type="button" class="scope-user" :class="{ selected: draft.id === user.id }" @click="draft = { level: 'user', id: user.id, name: user.name }">
              <strong>{{ user.name }}</strong><span>{{ user.loginName }}{{ user.email ? ` · ${user.email}` : '' }}</span>
            </button>
            <n-empty v-if="!usersLoading && !users.length" :description="t('directoryScope.noUsers')" />
          </div>
        </n-spin>
        <n-pagination :page="userPage" :page-size="20" :item-count="userTotal" :page-slot="5" @update:page="userPage = $event" />
      </div>
      <div v-else class="scope-selection">
        <strong>{{ t('directoryScope.selected') }}</strong>
        <span>{{ draft.id ? draft.name : t('directoryScope.selectDepartment') }}</span>
      </div>
    </div>
    <template #footer>
      <div class="scope-footer">
        <n-button @click="visible = false">{{ t('directoryScope.cancel') }}</n-button>
        <n-button type="primary" :disabled="draft.level !== 'organization' && !draft.id" @click="apply">{{ t('directoryScope.apply') }}</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { TreeOption } from 'naive-ui';
import { fetchScopeDepartments, fetchScopeUsers, type DirectoryScope, type ScopeDepartment, type ScopeUser } from '@/api/directoryScope';
import { t } from '@/composables/i18n';

const props = defineProps<{ modelValue: DirectoryScope }>();
const emit = defineEmits<{ 'update:modelValue': [value: DirectoryScope] }>();
const levels = ['organization', 'department', 'user'] as const;
const visible = ref(false);
const draft = ref<DirectoryScope>({ ...props.modelValue });
const departments = ref<ScopeDepartment[]>([]);
const departmentsLoading = ref(false);
const departmentError = ref(false);
const departmentSearch = ref('');
const selectedDepartmentId = ref('');
const userSearch = ref('');
const users = ref<ScopeUser[]>([]);
const usersLoading = ref(false);
const userTotal = ref(0);
const userPage = ref(1);
let searchTimer: ReturnType<typeof setTimeout> | undefined;
let requestId = 0;

const treeOptions = computed<TreeOption[]>(() => [{ key: '', label: t('directoryScope.all'), children: departments.value.map(toTree) }]);
function toTree(department: ScopeDepartment): TreeOption {
  return { key: department.id, label: department.name, children: department.children.map(toTree) };
}
function findDepartment(nodes: ScopeDepartment[], id: string): ScopeDepartment | undefined {
  for (const node of nodes) {
    if (node.id === id) return node;
    const child = findDepartment(node.children, id);
    if (child) return child;
  }
}
async function open() {
  draft.value = { ...props.modelValue };
  selectedDepartmentId.value = draft.value.level === 'department' ? draft.value.id : '';
  visible.value = true;
  if (!departments.value.length) {
    departmentsLoading.value = true;
    departmentError.value = false;
    try { departments.value = await fetchScopeDepartments(); }
    catch { departmentError.value = true; }
    finally { departmentsLoading.value = false; }
  }
}
function setLevel(level: DirectoryScope['level']) {
  draft.value = { level, id: '', name: '' };
  selectedDepartmentId.value = '';
  userPage.value = 1;
}
function selectDepartment(keys: Array<string | number>) {
  const id = String(keys[0] ?? '');
  selectedDepartmentId.value = id;
  if (draft.value.level === 'department') {
    draft.value = { level: 'department', id, name: findDepartment(departments.value, id)?.name || '' };
  } else {
    draft.value = { level: 'user', id: '', name: '' };
    userPage.value = 1;
  }
}
async function loadUsers() {
  const current = ++requestId;
  usersLoading.value = true;
  try {
    const result = await fetchScopeUsers({ departmentId: selectedDepartmentId.value, keyword: userSearch.value, page: userPage.value, pageSize: 20 });
    if (current !== requestId) return;
    users.value = result.items;
    userTotal.value = result.total;
  } catch {
    if (current === requestId) { users.value = []; userTotal.value = 0; }
  } finally {
    if (current === requestId) usersLoading.value = false;
  }
}
watch([visible, () => draft.value.level, selectedDepartmentId, userSearch, userPage], () => {
  clearTimeout(searchTimer);
  if (!visible.value || draft.value.level !== 'user') { requestId++; return; }
  searchTimer = setTimeout(() => { void loadUsers(); }, 250);
});
watch(userSearch, () => { userPage.value = 1; });
function apply() {
  emit('update:modelValue', { ...draft.value });
  visible.value = false;
}
</script>

<style scoped>
.scope-trigger { min-width: 160px; justify-content: flex-start; }
.scope-modes { display: flex; gap: 8px; margin-bottom: 16px; }
.scope-hint { color: #64748b; min-height: 280px; }
.scope-content { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(240px, 1fr); gap: 20px; min-height: 330px; }
.scope-departments, .scope-users { min-width: 0; display: flex; flex-direction: column; gap: 10px; }
.scope-tree { height: 310px; overflow: auto; border: 1px solid #e5eaf0; border-radius: 8px; padding: 6px; }
.scope-user-list { height: 268px; overflow: auto; border: 1px solid #e5eaf0; border-radius: 8px; }
.scope-user { width: 100%; display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 10px; border: 0; border-bottom: 1px solid #edf0f5; background: white; cursor: pointer; text-align: left; }
.scope-user:hover, .scope-user.selected { background: #eef4ff; }
.scope-user span { color: #64748b; font-size: 12px; }
.scope-selection { display: flex; flex-direction: column; gap: 10px; padding: 18px; background: #f8fafc; border-radius: 8px; }
.scope-footer { display: flex; justify-content: flex-end; gap: 8px; }
:global(.scope-modal) { width: min(760px, calc(100vw - 32px)); }
@media (max-width: 640px) { .scope-content { grid-template-columns: 1fr; } .scope-tree { height: 180px; } }
</style>
