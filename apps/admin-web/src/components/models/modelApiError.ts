import axios from 'axios';

interface FieldError {
  loc?: Array<string | number>;
  msg?: string;
}

export function modelApiErrorText(error: unknown): string {
  if (!axios.isAxiosError(error)) return String(error);
  const detail: unknown = error.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item: FieldError) => {
      const field = Array.isArray(item?.loc) ? item.loc.filter((part) => part !== 'body').join('.') : '';
      return [field, item?.msg].filter(Boolean).join(': ');
    }).filter(Boolean);
    if (messages.length) return messages.join('; ');
  }
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === 'string' && message) return message;
  }
  return error.message || 'Request failed';
}
