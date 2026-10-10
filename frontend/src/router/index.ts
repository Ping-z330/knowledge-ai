import { createRouter, createWebHistory } from 'vue-router'
import { isAuthenticated } from '../utils/authStorage'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      name: 'home',
      component: () => import('../views/WelcomeView.vue'),
    },
    {
      path: '/:kbId',
      name: 'workspace',
      component: () => import('../views/KbWorkspaceView.vue'),
    },
    {
      path: '/:kbId/documents',
      name: 'documents',
      component: () => import('../views/KbDocumentsView.vue'),
    },
  ],
})

router.beforeEach((to) => {
  // public 路由放行；已登录访问 /login 时跳回首页
  if (to.meta.public) {
    if (to.name === 'login' && isAuthenticated()) return { name: 'home' }
    return true
  }
  // 受保护路由未登录 → 重定向到登录页
  if (!isAuthenticated()) {
    return {
      name: 'login',
      query: to.fullPath !== '/' ? { redirect: to.fullPath } : {},
    }
  }
  return true
})

export default router
