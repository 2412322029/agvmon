<template>
  <div class="ssh-connection-management">
    <n-card title="SSH 连接管理" :bordered="false">
      <template #header-extra>
        <n-space vertical :size="16">
          <n-button @click="loadConnections" size="small" type="primary">刷新连接列表</n-button>
        </n-space>
      </template>
      <!-- 连接列表 -->
      <n-data-table :columns="columns" :data="connections" :loading="loading" :pagination="false"
        :row-key="(row) => row.id" />
      <!-- 下载信息 -->
    </n-card>
    <n-card v-if="downloads && Object.keys(downloads).length > 0" title="下载信息" :bordered="false">
      <template #header-extra>
        <n-space vertical :size="16">
          <n-button @click="loadDownloads" size="small" type="primary">刷新下载信息</n-button>
        </n-space>
      </template>
      <n-data-table :columns="downloadColumns" :data="downloadData" :loading="downloadLoading" :pagination="false"
        :row-key="(row) => row.download_id" />
    </n-card>
  </div>

</template>

<script setup>
import axios from 'axios'
import {
  NButton,
  NCard,
  NDataTable,
  NSpace,
  useMessage
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'

// 消息提示
const message = useMessage()

// 连接数据
const connections = ref([])
const loading = ref(false)

// 下载数据
const downloads = ref({})
const downloadLoading = ref(false)

// 格式化连接状态
const formatStatus = (connected) => {
  return connected ? '已连接' : '未连接'
}

// 格式化状态标签类型
const getStatusType = (connected) => {
  return connected ? 'success' : 'error'
}

// 断开连接
const disconnectConnection = async (id) => {
  try {
    const response = await axios.get(`/agv/disconnect?id=${id}`)
    if (response.data.success) {
      message.success('连接已断开')
      // 重新加载连接列表
      await loadConnections()
    } else {
      message.error(response.data.error || '断开连接失败')
    }
  } catch (error) {
    message.error(error.response?.data?.error || error.message || '断开连接失败')
  }
}

// 加载连接列表
const loadConnections = async () => {
  loading.value = true
  try {
    const response = await axios.get('/agv/list_ssh')
    if (response.data.success) {
      connections.value = response.data.data
    } else {
      message.error(response.data.error || '获取连接列表失败')
    }
  } catch (error) {
    message.error(error.response?.data?.error || error.message || '获取连接列表失败')
  } finally {
    loading.value = false
  }
}

// 加载下载信息
const loadDownloads = async () => {
  downloadLoading.value = true
  try {
    const response = await axios.get('/agv/download_info')
    if (response.data.downloads) {
      downloads.value = response.data.downloads
    }
  } catch (error) {
    message.error(error.response?.data?.error || error.message || '获取下载信息失败')
  } finally {
    downloadLoading.value = false
  }
}

// 列配置
const columns = [
  {
    title: 'ID',
    key: 'id',
    width: 200,
    render(row) {
      return row.id
    }
  },
  {
    title: '名称',
    key: 'name',
    width: 120,
    render(row) {
      return row.name
    }
  },
  {
    title: '创建时间',
    key: 'created_at',
    width: 180,
    render(row) {
      return row.create_time || '-'
    }
  },
  {
    title: '操作',
    key: 'actions',
    width: 150,
    render(row) {
      return h(
        NSpace,
        null,
        {
          default: () => [
            h(
              NButton,
              {
                size: 'small',
                type: 'error',
                onClick: () => disconnectConnection(row.id)
              },
              {
                default: () => '断开连接'
              }
            )
          ]
        }
      )
    }
  }
]

// 下载列配置
const downloadColumns = [
  {
    title: 'ID',
    key: 'download_id',
    width: 150,
    render(row) { 
      return h('div', { style: 'max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;' }, row.download_id)
    }
  },
  {
    title: '文件名',
    key: 'filename',
    width: 300,
    render(row) {
      return row.filename || '-'
    }
  },
  {
    title: '进度',
    key: 'progress',
    width: 200,
    render(row) {
      const total = row.total || 0
      const progress = row.progress || 0
      if (total > 0) {
        const percentage = ((progress / total) * 100).toFixed(2)
        const formatSize = (bytes) => {
          const units = ['B', 'KB', 'MB', 'GB', 'TB']
          let size = bytes
          let unitIndex = 0
          while (size >= 1024 && unitIndex < units.length - 1) {
            size /= 1024
            unitIndex++
          }
          return `${size.toFixed(2)} ${units[unitIndex]}`
        }
        return `${percentage}% (${formatSize(progress)}/${formatSize(total)})`
      }
      return `${progress}/${total} B`
    }
  },
  {
    title: '创建时间',
    key: 'created_at',
    width: 180,
    render(row) {
      return row.created_at || '-'
    }
  }
]

// 下载数据转换（响应式计算属性）
const downloadData = computed(() => Object.entries(downloads.value).map(([download_id, info]) => ({
  download_id,
  ...info
})))

// 页面加载时获取连接列表和下载信息
onMounted(() => {
  loadConnections()
  loadDownloads()
})

</script>

<style scoped>
.ssh-connection-management {
  padding: 2px;
}
</style>