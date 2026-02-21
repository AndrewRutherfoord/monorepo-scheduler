import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import DashboardView from '@/views/DashboardView.vue'
import JobDetailsView from '@/views/JobDetailsView.vue'
import RunDetailsView from '@/views/RunDetailsView.vue'
import LoginView from '@/views/LoginView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: DashboardView, meta: { requiresAuth: true } },
    { path: '/jobs/:jobId', component: JobDetailsView, meta: { requiresAuth: true } },
    { path: '/jobs/:jobId/runs/:runId', component: RunDetailsView, meta: { requiresAuth: true } },
    { path: '/login', component: LoginView },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return '/login'
  }
})

export default router
