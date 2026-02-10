<script setup>
import {
  HomeOutlined,
  LinkOutlined,
  SettingOutlined,
  ToolOutlined,
  MenuOutlined
} from '@vicons/antd';
import {
  dateZhCN,
  NButton,
  NConfigProvider,
  NDropdown,
  NIcon,
  NMenu,
  NMessageProvider,
  NSplit,
  zhCN
} from 'naive-ui';
import { computed, h, onMounted, onUnmounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

const router = useRouter();
const route = useRoute();

// Helper function to render icons
const renderIcon = (icon) => {
  return () => h(NIcon, null, { default: () => h(icon) });
};

// Menu structure for desktop with submenus and icons
const menuOptions = [
  {
    label: '首页',
    key: '/',
    icon: renderIcon(HomeOutlined),
    onClick: () => router.push('/')
  },
  {
    label: '系统管理',
    key: 'system',
    icon: renderIcon(SettingOutlined),
    children: [
      {
        label: '服务管理',
        key: '/service',
        onClick: () => router.push('/service')
      }
    ]
  },
  {
    label: '工具',
    key: 'tools',
    icon: renderIcon(ToolOutlined),
    children: [
      {
        label: '异常记录',
        key: '/exception-records',
        onClick: () => router.push('/exception-records')
      },
      {
        label: 'AGV-EQ议解析',
        key: '/agv',
        onClick: () => router.push('/agv')
      },
      {
        label: 'SSH 文件管理',
        key: '/ssh',
        onClick: () => router.push('/ssh')
      },
      {
        label: 'SSH 连接管理',
        key: '/ssh-connections',
        onClick: () => router.push('/ssh-connections')
      },
      {
        label: '文件上传管理',
        key: '/file-upload',
        onClick: () => router.push('/file-upload')
      }
    ]
  },
  {
    label: '外部服务',
    key: 'external',
    icon: renderIcon(LinkOutlined),
    children: [
      {
        label: 'RCS Web 登录',
        key: '/rcs-web-login',
        onClick: () => router.push('/rcs-web-login')
      },
      {
        label: '任务查询',
        key: '/task-query',
        onClick: () => router.push('/task-query')
      },
      {
        label: '地图',
        key: '/map',
        onClick: () => router.push('/map')
      }
    ]
  }
];

// Mobile menu options without icons to simplify mobile view
const mobileMenuOptions = JSON.parse(JSON.stringify(menuOptions)).map(item => {
  const newItem = { ...item };
  // Remove icons from mobile menu for cleaner appearance
  delete newItem.icon;
  if (newItem.children) {
    newItem.children = newItem.children.map(child => {
      const newChild = { ...child };
      delete newChild.icon;
      return newChild;
    });
  }
  return newItem;
});

// 处理移动端菜单选择
const handleMobileMenuSelect = (key) => {
  // 检查是否是路由路径（以/开头），否则不做任何操作
  if (key.startsWith('/')) {
    router.push(key);
  }
};
// 处理菜单选择事件
const handleUpdateValue = (key) => {
  if (key.startsWith('/')) {
    router.push(key);
  }
};
// 检测是否为移动端
const isMobile = ref(false);

// 当前路由路径，用于高亮当前页面
const currentRoute = computed(() => route.path);

// 更新窗口大小检测函数
const updateIsMobile = () => {
  isMobile.value = window.innerWidth < 992; // Changed breakpoint to 992px for better tablet support
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
              <NMenu mode="horizontal" :options="menuOptions" :value="currentRoute" @update:value="handleUpdateValue"
                style="height: 60px; line-height: 60px;align-items: center;" responsive :indent="18" />
            </div>
            <!-- 移动端显示汉堡菜单 -->
            <div v-else class="mobile-menu">
              <NDropdown trigger="click" :options="mobileMenuOptions" placement="bottom-start"
                @select="handleMobileMenuSelect" :keyboard="true" :show-arrow="true">
                <NButton quaternary circle>
                  <NIcon :component="MenuOutlined" />
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
  transition: all 0.3s ease;
}

:deep(.n-menu-item) {
  font-size: 16px;
  font-weight: 500;
  transition: all 0.2s ease;
  border-radius: 6px;
  margin: 0 4px;
}

:deep(.n-menu-item:hover) {
  background-color: rgba(0, 0, 0, 0.05);
}

:deep(.n-submenu .n-submenu-arrow) {
  transition: transform 0.2s ease;
}

/* Active/current route styling */
:deep(.n-menu-item--selected) {
  background-color: rgba(0, 100, 255, 0.1) !important;
  color: #1890ff;
  font-weight: 600;
}

/* 移动端适配 */
@media (max-width: 992px) {
  :deep(.n-menu) {
    font-size: 14px;
  }

  :deep(.n-menu-item) {
    font-size: 13px;
    /* Slightly larger font for better touch targets */
    padding: 0 8px !important;
    /* Better touch target size */
  }

  :deep(.n-menu-item-content) {
    min-height: 44px;
    display: flex;
    align-items: center;
  }

  /* 针对小屏幕设备 */
  @media (max-width: 576px) {
    :deep(.n-menu-item) {
      font-size: 12px;
      padding: 0 6px !important;
    }

    :deep(.n-menu) {
      height: 54px !important;
      line-height: 54px !important;
    }
  }
}

/* 移动端菜单样式 */
.mobile-menu {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  /* 将按钮靠右对齐 */
  height: 60px;
  padding-right: 16px;
  /* Increased padding for better spacing */
  transition: all 0.3s ease;
}

.desktop-menu {
  width: 100%;
  padding: 0 16px;
}

/* 优化移动端下拉菜单样式 */
@media (max-width: 992px) {
  :deep(.n-dropdown-option) {
    padding: 10px 16px;
    border-radius: 4px;
    margin: 2px 8px;
    transition: all 0.2s ease;
  }

  :deep(.n-dropdown-option:hover) {
    background-color: rgba(0, 0, 0, 0.04);
  }

  :deep(.n-dropdown-option-body) {
    font-size: 15px;
    padding: 8px 16px;
  }

  :deep(.n-dropdown) {
    max-height: 70vh;
    overflow-y: auto;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    border-radius: 8px;
  }
}

/* Smooth transitions for menu interactions */
:deep(.n-menu-item-content .n-base-icon),
:deep(.n-menu-item .n-icon) {
  transition: all 0.2s ease;
}

/* Adjust submenu styling */
:deep(.n-submenu .n-submenu-trigger) {
  border-radius: 6px;
}
</style>
