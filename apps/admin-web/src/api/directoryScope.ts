import { apiClient } from '@/api/client';

export interface DirectoryScope {
  level: 'organization' | 'department' | 'user';
  id: string;
  name: string;
}

export interface ScopeDepartment {
  id: string;
  name: string;
  children: ScopeDepartment[];
}

export interface ScopeUser {
  id: string;
  name: string;
  loginName: string;
  email: string;
}

export interface ScopeUserPage {
  items: ScopeUser[];
  total: number;
  page: number;
  pageSize: number;
}

export async function fetchScopeDepartments(): Promise<ScopeDepartment[]> {
  const { data } = await apiClient.get<ScopeDepartment[]>('/api/directory/scope-departments');
  return data;
}

export async function fetchScopeUsers(params: { departmentId: string; keyword: string; page: number; pageSize: number }): Promise<ScopeUserPage> {
  const { data } = await apiClient.get<ScopeUserPage>('/api/directory/scope-users', { params });
  return data;
}
