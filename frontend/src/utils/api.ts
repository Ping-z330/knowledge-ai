import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: import.meta.env.VITE_API_TOKEN
    ? { Authorization: `Bearer ${import.meta.env.VITE_API_TOKEN}` }
    : {},
})

export function extractApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
    if (error.response?.status) {
      return `请求失败：HTTP ${error.response.status}`
    }
    if (error.message) {
      return error.message
    }
  }
  return '请求失败，请检查后端日志或模型服务配置。'
}
