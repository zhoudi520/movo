import { apiClient } from '@/api/client';

export interface TokenStatsSummary {
  totalCalls: number;
  totalTokens: number;
  promptTokens: number;
  completionTokens: number;
  avgTokens: number;
  lastCalledAt: string | null;
  last24hCalls: number;
  last24hTokens: number;
  activeUsers: number;
  activeDepartments: number;
  costsByCurrency: Record<'CNY' | 'USD', number>;
  pricedCallsByCurrency: Record<'CNY' | 'USD', number>;
  avgCostsByCurrency: Record<'CNY' | 'USD', number>;
  last24hCostsByCurrency: Record<'CNY' | 'USD', number>;
  unpricedCalls: number;
}

export interface TokenStatsItem {
  requestId: string;
  userRequestId?: string;
  mainId: string;
  mainName: string;
  userName: string;
  departmentName: string;
  modelName: string;
  stage: string;
  status: string;
  requestTitle: string;
  promptPreview: string;
  totalTokens: number;
  promptTokens: number;
  completionTokens: number;
  createdAt: string | null;
  durationMs: number;
  calls?: number;
  sessionId?: string;
}

export interface TokenStatsOption {
  label: string;
  value: string;
}

export interface TokenStatsFilterOptions {
  enterprises: TokenStatsOption[];
  departments: TokenStatsOption[];
  users: TokenStatsOption[];
  models: TokenStatsOption[];
  stages: TokenStatsOption[];
  statuses: TokenStatsOption[];
}

export interface TokenStatsPage {
  summary: TokenStatsSummary;
  items: TokenStatsItem[];
  offset: number;
  limit: number;
  total: number;
  hasMore: boolean;
  filterOptions: TokenStatsFilterOptions;
}

export interface TokenStatsQuery {
  q?: string;
  departmentId?: string;
  userId?: string;
  modelName?: string;
  stage?: string;
  status?: string;
  offset?: number;
  limit?: number;
  groupBy?: string;
  sessionId?: string;
  userRequestId?: string;
}

const defaultSummary: TokenStatsSummary = {
  totalCalls: 0,
  totalTokens: 0,
  promptTokens: 0,
  completionTokens: 0,
  avgTokens: 0,
  lastCalledAt: null,
  last24hCalls: 0,
  last24hTokens: 0,
  activeUsers: 0,
  activeDepartments: 0,
  costsByCurrency: { CNY: 0, USD: 0 },
  pricedCallsByCurrency: { CNY: 0, USD: 0 },
  avgCostsByCurrency: { CNY: 0, USD: 0 },
  last24hCostsByCurrency: { CNY: 0, USD: 0 },
  unpricedCalls: 0,
};

const defaultOptions: TokenStatsFilterOptions = {
  enterprises: [],
  departments: [],
  users: [],
  models: [],
  stages: [],
  statuses: [],
};

export async function fetchTokenStats(query: TokenStatsQuery = {}): Promise<TokenStatsPage> {
  const params = {
    q: query.q || '',
    departmentId: query.departmentId || '',
    userId: query.userId || '',
    modelName: query.modelName || '',
    stage: query.stage || '',
    status: query.status || '',
    offset: query.offset || 0,
    limit: query.limit || 20,
    groupBy: query.groupBy || 'user_request',
    sessionId: query.sessionId || '',
    userRequestId: query.userRequestId || '',
  };

  const { data } = await apiClient.get('/api/analytics/token-usage', { params });
  return {
    summary: {
      ...defaultSummary,
      ...(data?.summary || {}),
    },
    items: Array.isArray(data?.items) ? data.items : [],
    offset: Number(data?.offset || params.offset || 0),
    limit: Number(data?.limit || params.limit || 20),
    total: Number(data?.total || 0),
    hasMore: Boolean(data?.hasMore),
    filterOptions: {
      ...defaultOptions,
      ...(data?.filterOptions || {}),
    },
  };
}

export interface TokenStatsDetail {
  requestId: string;
  prompt: string;
  requestPayload: any;
  responsePayload: any;
}

export async function fetchTokenStatsDetail(requestId: string): Promise<TokenStatsDetail> {
  const { data } = await apiClient.get(`/api/analytics/token-usage/${requestId}`);
  return data;
}

export interface ChatMessageItem {
  id: string;
  role: string;
  content: string;
  plan?: any;
  progress?: any[];
  documents?: any[];
  images?: any[];
  createdAt: string | null;
}

export interface SessionChatHistory {
  sessionId: string;
  title: string;
  messages: ChatMessageItem[];
}

export async function fetchSessionChatHistory(requestId: string): Promise<SessionChatHistory> {
  const { data } = await apiClient.get(`/api/analytics/token-usage/${requestId}/chat-history`);
  return data;
}
