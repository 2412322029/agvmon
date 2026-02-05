<script setup>
import { dateZhCN, NButton, NConfigProvider, NDropdown, NMenu, NMessageProvider, NSplit, zhCN } from 'naive-ui';
import { onMounted, onUnmounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

const router = useRouter();
const route = useRoute();

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
  },
  {
    label: 'RCS Web 登录',
    key: '/rcs-web-login',
    onClick: () => router.push('/rcs-web-login')
  },
  {
    label: '异常记录',
    key: '/exception-records',
    onClick: () => router.push('/exception-records')
  },
    {
    label: 'agveq协议解析',
    key: '/agv',
    onClick: () => router.push('/agv')
  },
  {
    label: 'SSH 文件管理',
    key: '/ssh',
    onClick: () => router.push('/ssh')
  }
];

// 移动端下拉菜单选项
const mobileMenuOptions = menuOptions.map(item => ({
  label: item.label,
  key: item.key,
  // 在移动端菜单中，我们只存储key值，实际跳转由handleMobileMenuSelect处理
}));

// 处理移动端菜单选择
const handleMobileMenuSelect = (key) => {
  router.push(key);
};

// 检测是否为移动端
const isMobile = ref(false);

// 更新窗口大小检测函数
const updateIsMobile = () => {
  isMobile.value = window.innerWidth < 768;
};

// 组件挂载时初始化
onMounted(() => {
  updateIsMobile();
  window.addEventListener('resize', updateIsMobile);
});

// 组件卸载时移除事件监听器
onUnmounted(() => {
  window.removeEventListener('resize', updateIsMobile);
});
</script>

<template>
  <n-message-provider>
    <n-config-provider :locale="zhCN" :date-locale="dateZhCN">
      <div>
        <!-- 顶部导航 -->
        <n-split :default-size="1">
          <template #1>
            <!-- 桌面端显示完整菜单 -->
            <div v-if="!isMobile" class="desktop-menu">
              <NMenu mode="horizontal" :options="menuOptions" style="height: 60px; line-height: 60px;align-items: center;" responsive />
            </div>
            <!-- 移动端显示汉堡菜单 -->
            <div v-else class="mobile-menu">
              <NDropdown trigger="click" :options="mobileMenuOptions" placement="bottom-start" @select="handleMobileMenuSelect">
                <NButton quaternary circle>
                  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-menu">
                    <line x1="4" x2="20" y1="12" y2="12"></line>
                    <line x1="4" x2="20" y1="6" y2="6"></line>
                    <line x1="4" x2="20" y1="18" y2="18"></line>
                  </svg>
                </NButton>
              </NDropdown>
            </div>
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

/* 移动端适配 */
@media (max-width: 768px) {
  :deep(.n-menu) {
    font-size: 14px;
  }
  
  :deep(.n-menu-item) {
    font-size: 12px; /* 减小字体大小 */
    padding: 0 6px !important; /* 减小内边距 */
  }
  
  :deep(.n-menu-item-content) {
    min-height: 40px;
    display: flex;
    align-items: center;
  }
  
  /* 针对特别小的屏幕 */
  @media (max-width: 480px) {
    :deep(.n-menu-item) {
      font-size: 11px;
      padding: 0 4px !important;
    }
    
    :deep(.n-menu) {
      height: 50px !important;
      line-height: 50px !important;
    }
  }
}

/* 移动端菜单样式 */
.mobile-menu {
  display: flex;
  align-items: center;
  justify-content: flex-end; /* 将按钮靠右对齐 */
  height: 60px;
  padding-right: 10px; /* 添加右边距 */
}

.desktop-menu {
  width: 100%;
}
</style>
