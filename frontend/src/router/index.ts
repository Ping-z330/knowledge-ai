import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
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

export default router
