import axios from 'axios'
import router from '../router'
import { clearToken, getToken } from './authStorage'

export const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

// 动态注入 JWT（每次请求从 localStorage 读取最新 token）
api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 401 → 清除 token 并重定向到登录页；其它错误走全局 ErrorToast
api.interceptors.response.use(
  (res) => res,
  (error) => {
    const status = error.response?.status
    if (status === 401) {
      clearToken()
      const redirect = router.currentRoute.value.fullPath
      if (router.currentRoute.value.path !== '/login') {
        router.replace({ path: '/login', query: redirect ? { redirect } : {} })
      }
      return Promise.reject(error)
    }
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
