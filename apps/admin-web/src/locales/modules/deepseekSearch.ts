import type { LabelMap } from '../messages';

export const deepseekSearchMessages: Record<string, LabelMap> = {
  'search.deepseek.signIn': { 'zh-CN': '登录 DeepSeek 开放平台', 'en-US': 'Sign in to DeepSeek Platform' },
  'search.deepseek.createKey': { 'zh-CN': '创建自己的 API Key', 'en-US': 'Create your own API Key' },
  'search.deepseek.test': { 'zh-CN': '将 Key 填入 MOVO 并测试搜索', 'en-US': 'Enter the key in MOVO and test search' },
  'search.deepseek.billing': {
    'zh-CN': 'Search 按符合计费条件的成功请求次数收费；MOVO 只使用你配置的 DeepSeek Key，不会自动抓取每条结果。',
    'en-US': 'Search is billed per qualifying successful request. MOVO uses your configured DeepSeek key and does not automatically fetch every result.',
  },
};
