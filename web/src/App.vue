<script setup>
import { NConfigProvider, NMenu, NMessageProvider, NSplit } from 'naive-ui';
import { useRouter } from 'vue-router';



const router = useRouter()

// 导航菜单配置
const menuOptions = [
  {
    label: '首页',
    key: '/',
    onClick: () => router.push('/')
  },
  {
    label: '服务管理',
    key: '/service',
    onClick: () => router.push('/service'),
    // children: [
    //   {
    //     label: '从缓存构建',
    //     key: '/service/build_from_cache',
    //     onClick: () => router.push('/service/build_from_cache')
    //   },
    //   {
    //     label: '从原始数据构建',
    //     key: '/service/build_from_raw',
    //     onClick: () => router.push('/service/build_from_raw')
    //   }
    // ]
  },
  {
    label: '地图管理',
    key: '/map',
    onClick: () => router.push('/map'),
    // children: [
    //   {
    //     label: '共享地图数据',
    //     key: '/map/sharemapdata',
    //     onClick: () => router.push('/map/sharemapdata')
    //   }
    // ]
  },
  {
    label: '任务查询',
    key: '/task-query',
    onClick: () => router.push('/task-query')
  }
]
</script>

<template>
  <n-message-provider>
    <n-config-provider>
      <div style="height: 40px;">
        <!-- 顶部导航 -->
        <n-split :default-size="1">
          <template #1>
            <NMenu mode="horizontal" :options="menuOptions" style="height: 60px; line-height: 60px;" />
          </template>
        </n-split>

        <!-- 主要内容区域 -->
        <main style="padding: 3px; max-width: 1200px; margin: 0 auto;">
          <router-view />
        </main>
      </div>
    </n-config-provider>
  </n-message-provider>
</template>

<style scoped>
/* 全局样式 */
:deep(.n-menu) {
  background-color: transparent;
  border-bottom: none;
}

:deep(.n-menu-item) {
  font-size: 16px;
  font-weight: 500;
}
</style>
