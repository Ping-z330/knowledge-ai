import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: import.meta.env.VITE_API_TOKEN
    ? { Authorization: `Bearer ${import.meta.env.VITE_API_TOKEN}` }
    : {},
})

// Global error interceptor — dispatches custom event for ErrorToast
api.interceptors.response.use(
  (res) => res,
  (error) => {
    const detail = extractApiError(error)
    window.dispatchEvent(new CustomEvent('app-error', { detail }))
    return Promise.reject(error)
  },
)

export function extractApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return '无法连接到服务器，请检查网络或后端是否启动。'
    }
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
    if (error.response?.status) {
      if (error.response.status >= 500) {
        return `服务器错误 (${error.response.status})，请稍后重试。`
      }
      return `请求失败：HTTP ${error.response.status}`
    }
    if (error.message) {
      return error.message
    }
  }
  return '请求失败，请检查后端日志或模型服务配置。'
}
