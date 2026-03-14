<template>
  <div class="image-decode-view">
    <n-page-header>
      <n-space>
        <n-button @click="goBack" size="small">
          <n-icon style="margin-right: 4px;">
            <arrow-left-outlined />
          </n-icon>
          返回
        </n-button>
        <n-breadcrumb>
          <n-breadcrumb-item>
            <a @click="goHome">
              首页
            </a>
          </n-breadcrumb-item>
          <n-breadcrumb-item>
            图片识别
          </n-breadcrumb-item>
        </n-breadcrumb>
      </n-space>
    </n-page-header>

    <div style="margin-top: 20px;">
      <ImageDecodeComponent />
    </div>
  </div>
</template>

<script setup>
import ImageDecodeComponent from '@/components/ImageDecodeComponent.vue'
import { ArrowLeftOutlined } from '@vicons/antd'
import { useRouter } from 'vue-router'
import { NPageHeader, NSpace, NButton, NIcon, NBreadcrumb, NBreadcrumbItem } from 'naive-ui'

const router = useRouter()

const goBack = () => {
  router.back()
}

const goHome = () => {
  router.push('/')
}
</script>

<style scoped>
.image-decode-view {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

/* Mobile responsiveness */
@media (max-width: 768px) {
  .image-decode-view {
    padding: 10px;
  }
}

@media (max-width: 480px) {
  .n-page-header {
    padding: 10px 0;
  }
  
  .n-breadcrumb {
    font-size: 12px;
  }
}
</style>
