import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('../views/Home.vue'),
    },
    // Service Interface Pages
    {
      path: '/service',
      name: 'service',
      component: () => import('../views/ServiceDashboard.vue'),
    },
    {
      path: '/service/build_from_cache',
      name: 'build_from_cache',
      component: () => import('../views/BuildFromCache.vue'),
    },
    {
      path: '/service/build_from_raw',
      name: 'build_from_raw',
      component: () => import('../views/BuildFromRaw.vue'),
    },
    // Map Interface Pages
    {
      path: '/map',
      name: 'map',
      component: () => import('../views/MapView.vue'),
    },
    // Task Query Page
    {
      path: '/task-query',
      name: 'task-query',
      component: () => import('../views/TaskQueryView.vue'),
    },
  ],
})

export default router
