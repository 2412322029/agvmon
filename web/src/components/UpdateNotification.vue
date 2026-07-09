<template>
  <div v-if="status !== 'idle'" class="update-notification">
    <!-- Checking -->
    <n-alert v-if="status === 'checking'" type="info" :bordered="false" class="update-alert">
      <template #header>
        <n-space align="center" :size="8">
          <n-spin :size="14" />
          <span>正在检查更新...</span>
        </n-space>
      </template>
    </n-alert>

    <!-- Update available -->
    <n-alert
      v-else-if="status === 'update_available'"
      type="warning"
      :bordered="false"
      class="update-alert"
    >
      <template #header>
        <n-space align="center" justify="space-between">
          <span>发现新版本 <strong>v{{ updateInfo?.version }}</strong>
            <span v-if="updateInfo?.size" class="size-hint"> ({{ formatSize(updateInfo.size) }})</span>
          </span>
          <n-button size="tiny" type="warning" @click="handleDownload">
            下载更新
          </n-button>
        </n-space>
      </template>
    </n-alert>

    <!-- Downloading -->
    <n-alert
      v-else-if="status === 'downloading'"
      type="info"
      :bordered="false"
      class="update-alert"
    >
      <template #header>
        <div>
          <n-space align="center" justify="space-between" style="margin-bottom: 4px">
            <span>正在下载更新... {{ downloadProgress.toFixed(0) }}%</span>
            <n-button size="tiny" @click="cancelDownload">取消</n-button>
          </n-space>
          <n-progress
            type="line"
            :percentage="downloadProgress"
            :height="6"
            :border-radius="3"
            :show-indicator="false"
          />
        </div>
      </template>
    </n-alert>

    <!-- Ready -->
    <n-alert
      v-else-if="status === 'ready'"
      type="success"
      :bordered="false"
      class="update-alert"
    >
      <template #header>
        <n-space align="center" justify="space-between">
          <span>更新已下载，重启以应用新版本</span>
          <n-button size="tiny" type="success" @click="handleApply">
            重启更新
          </n-button>
        </n-space>
      </template>
    </n-alert>

    <!-- Applying -->
    <n-alert
      v-else-if="status === 'applying'"
      type="warning"
      :bordered="false"
      class="update-alert"
    >
      <template #header>
        <n-space align="center" :size="8">
          <n-spin :size="14" />
          <span>正在应用更新，系统即将重启...</span>
        </n-space>
      </template>
    </n-alert>

    <!-- Error -->
    <n-alert
      v-else-if="status === 'error'"
      type="error"
      :bordered="false"
      class="update-alert"
    >
      <template #header>
        <n-space align="center" justify="space-between">
          <span>{{ errorMessage }}</span>
          <n-button size="tiny" @click="handleRetry">重试</n-button>
        </n-space>
      </template>
    </n-alert>
  </div>
</template>

<script setup>
import {
  NAlert,
  NButton,
  NProgress,
  NSpace,
  NSpin,
} from 'naive-ui'
import { useUpdate } from '../composables/useUpdate'

const {
  status,
  updateInfo,
  downloadProgress,
  errorMessage,
  formatSize,
  downloadUpdate,
  applyUpdate,
  checkForUpdates,
} = useUpdate()

let eventSource = null

async function handleDownload() {
  try {
    await downloadUpdate()
  } catch {
    // error already set in composable
  }
}

async function handleApply() {
  await applyUpdate()
}

async function handleRetry() {
  // Go back to checking
  await checkForUpdates()
}

function cancelDownload() {
  // SSE is handled inside the composable; just reset
  status.value = 'idle'
}
</script>

<style scoped>
.update-notification {
  max-width: 1400px;
  margin: 0 auto 8px;
  padding: 0 4px;
}
.update-alert {
  border-radius: 0;
}
.size-hint {
  font-weight: normal;
  font-size: 12px;
  color: var(--n-text-color-3);
}
</style>
