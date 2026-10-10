import { ref } from 'vue'
import { api } from '../utils/api'
import { clearToken, getToken, setToken } from '../utils/authStorage'

// 模块级单例，全局共享登录状态
const token = ref<string | null>(getToken())

export function useAuth() {
  const isAuthenticated = () => !!token.value

  const login = async (username: string, password: string) => {
    const { data } = await api.post<{ access_token: string }>('/auth/login', {
      username,
      password,
    })
    setToken(data.access_token)
    token.value = data.access_token
  }

  const logout = () => {
    clearToken()
    token.value = null
  }

  return { token, isAuthenticated, login, logout }
}
