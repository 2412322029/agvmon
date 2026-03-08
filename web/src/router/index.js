import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      meta: {
        disc: '首页',
      },
      component: () => import('../views/Home.vue'),
    },
    // Service Interface Pages
    {
      path: '/service',
      name: 'service',
      meta: {
        disc: '服务管理',
      },
      component: () => import('../views/ServiceDashboard.vue'),
    },
    {
      path: '/service/build_from_cache',
      name: 'build_from_cache',
      meta: {
        disc: '从缓存构建',
      },
      component: () => import('../views/BuildFromCache.vue'),
    },
    {
      path: '/service/build_from_raw',
      name: 'build_from_raw',
      meta: {
        disc: '从原始数据构建',
      },
      component: () => import('../views/BuildFromRaw.vue'),
    },
    // Map Interface Pages
    {
      path: '/map',
      name: 'map',
      meta: {
        disc: '地图',
      },
      component: () => import('../views/MapView.vue'),
    },
    // Task Query Page
    {
      path: '/task-query',
      name: 'task-query',
      meta: {
        disc: '任务查询',
      },
      component: () => import('../views/TaskQueryView.vue'),
    },
    // RCS Web Login Page
    {
      path: '/rcs-web-login',
      name: 'rcs-web-login',
      meta: {
        disc: 'RCS Web 登录',
      },
      component: () => import('../views/RCSWebLogin.vue'),
    },
    // Exception Records Page
    {
      path: '/exception-records',
      name: 'exception-records',
      meta: {
        disc: '异常记录',
      },
      component: () => import('../views/ExceptionRecordsView.vue'),
    },
    // AGV Protocol Parser Page
    {
      path: '/agv',
      name: 'agv-protocol-parser',
      meta: {
        disc: 'AGV-EQ协议解析',
      },
      component: () => import('../views/AGVProtocolParser.vue'),
    },
    // SSH View Page
    {
      path: '/ssh',
      name: 'ssh',
      meta: {
        disc: 'SSH 文件管理',
      },
      component: () => import('../views/SSHView.vue'),
    },
    // SSH Connections View Page
    {
      path: '/ssh-mgr',
      name: 'ssh-mgr',
      meta: {
        disc: 'SSH 管理',
      },
      component: () => import('../views/SSHConnectionManagementView.vue'),
    },
    // File Upload View Page
    {
      path: '/file-upload',
      name: 'file-upload',
      meta: {
        disc: '文件上传管理',
      },
      component: () => import('../views/FileUploadView.vue'),
    },
    // Chat View Page
    {
      path: '/chat',
      name: 'chat',
      meta: {
        disc: '聊天室',
      },
      component: () => import('../views/ChatView.vue'),
    },
    // Setting View Page
    {
      path: '/setting',
      name: 'setting',
      meta: {
        disc: '设置',
      },
      component: () => import('../views/setting.vue'),
    },
    // WCS Device Status Page
    {
      path: '/wcs-status',
      name: 'wcs-status',
      meta: {
        disc: 'WCS设备状态',
      },
      component: () => import('../views/WCSDeviceStatus.vue'),
    },
    // 404 Not Found Page
    {
      path: '/:pathMatch(.*)*',
      name: '404',
      meta: {
        disc: '404 未找到',
      },
      component: () => import('../views/404.vue'),
    }
  ],
})

export default router
