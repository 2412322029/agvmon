<template>
  <div class="ssh-connection-management">
    <n-card title="SSH 连接管理" :bordered="false">
      <n-space vertical :size="16">
        <!-- 连接列表 -->
        <n-data-table
          :columns="columns"
          :data="connections"
          :loading="loading"
          :pagination="false"
          :row-key="(row) => row.id"
        />
      </n-space>
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
    NTag,
    useMessage
} from 'naive-ui'
import { h, onMounted, ref } from 'vue'

// 消息提示
const message = useMessage()

// 连接数据
const connections = ref([])
const loading = ref(false)

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

// 页面加载时获取连接列表
onMounted(() => {
  loadConnections()
})
</script>

<style scoped>
.ssh-connection-management {
  padding: 2px;
}
</style>