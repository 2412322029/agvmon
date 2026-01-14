<script setup>
import { NConfigProvider, NMenu, NSplit } from 'naive-ui';
import { useRouter } from 'vue-router';



const router = useRouter()

// 导航菜单配置
const menuOptions = [
  {
    label: 'home',
    key: '/',
    onClick: () => router.push('/')
  }
]
</script>

<template>
  <n-config-provider>
    <div style="height: 40px;">
      <!-- 顶部导航 -->
      <n-split :default-size="1">
        <template #1>
        <NMenu 
          mode="horizontal" 
          :options="menuOptions" 
          style="height: 60px; line-height: 60px;"
        /></template>
      </n-split>
      
      <!-- 主要内容区域 -->
      <main style="padding: 3px; max-width: 1200px; margin: 0 auto;">
        <router-view />
      </main>
    </div>
  </n-config-provider>
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
