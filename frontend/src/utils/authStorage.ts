/** JWT token 在 localStorage 中的存取。
 *  纯叶子模块（无外部 import），被 api.ts / sse.ts / useAuth / router 共同依赖，
 *  打破循环依赖。
 */

const KEY = 'ka_jwt'

export const getToken = (): string | null => localStorage.getItem(KEY)
export const setToken = (t: string): void => localStorage.setItem(KEY, t)
export const clearToken = (): void => localStorage.removeItem(KEY)
export const isAuthenticated = (): boolean => !!getToken()
