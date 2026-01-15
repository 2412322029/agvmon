<script setup>
import { NButton, NCard, NSpin, NText, useMessage } from 'naive-ui'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import MapComponent from '../components/MapComponent.vue'

const message = useMessage()

// 地图数据
const mapData = ref({ map_ret_list: [], ret_name_list: [] })
const mapLoading = ref(false)

// 机器人数据
const robotData = ref([])
const isConnected = ref(false)
const ws = ref(null)

// 获取地图数据
const fetchMapData = async () => {
  mapLoading.value = true
  try {
    const response = await fetch('/api/rcms/sharemapdata')
    const data = await response.json()
    mapData.value = data
    message.success('地图数据加载成功')
  } catch (error) {
    message.error('地图数据加载失败')
    console.error('Error fetching map data:', error)
  } finally {
    mapLoading.value = false
  }
}

// 连接WebSocket获取机器人实时数据
const connectWebSocket = () => {
  try {
    // 创建WebSocket连接
    const wsUrl = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsPath = `${wsUrl}//${window.location.host}/ws/robot-status`
    ws.value = new WebSocket(wsPath)

    // 连接打开
    ws.value.onopen = () => {
      console.log('WebSocket连接已打开')
      isConnected.value = true
    }

    // 接收消息
    ws.value.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        // 转换数据格式，添加友好的文本显示
        const formattedData = Object.values(data.data || {}).map(item => {
          // 确定显示状态和颜色
          let displayStatus = '正常'
          let statusColor = 'success'

          // 异常状态判断
          if (item.abnormal || [67, 61].includes(Number(item.status_code)) || (item.status && item.status.includes('异常'))) {
            displayStatus = '异常'
            statusColor = 'error'
          }
          // 暂停状态判断
          else if (item.stop) {
            displayStatus = '暂停'
            statusColor = 'warning'
          }
          // 排除状态判断
          else if (item.remove) {
            displayStatus = '排除'
            statusColor = 'info'
          }

          return {
            ...item,
            display_status: displayStatus,
            status_color: statusColor
          }
        })
        robotData.value = formattedData
      } catch (error) {
        console.error('解析WebSocket消息错误:', error)
      }
    }

    // 连接关闭
    ws.value.onclose = () => {
      console.log('WebSocket连接已关闭')
      isConnected.value = false
    }

    // 连接错误
    ws.value.onerror = (error) => {
      console.error('WebSocket连接错误:', error)
      isConnected.value = false
    }

  } catch (error) {
    console.error('创建WebSocket连接失败:', error)
    isConnected.value = false
  }
}

// 断开WebSocket连接
const disconnectWebSocket = () => {
  if (ws.value) {
    ws.value.close()
    ws.value = null
  }
}
//获取屏幕宽度
const screenWidth = ref(window.innerWidth)
// 生命周期钩子
onMounted(() => {
  fetchMapData()
  connectWebSocket()
})

onBeforeUnmount(() => {
  disconnectWebSocket()
})
</script>

<template>
  <div class="main-container">
    <NCard title="AGV地图" :bordered="false" style="max-width: 1200px; margin: 0 auto;">
      <template #header-extra>
        <NSpin :show="isConnected" size="small" />
        <NButton type="primary" @click="fetchMapData" :loading="mapLoading" style="margin-left: 10px;">
          刷新地图
        </NButton>
      </template>
      
      <NSpin :show="mapLoading" :size="'large'">
        <div v-if="mapData.MapRetCfg" class="map-container">
          <MapComponent 
            :map-data="mapData" 
            :robots="robotData" 
            :width=screenWidth-20
            :height="700" 
          />
        </div>
        <div v-else class="map-placeholder">
          <NText type="secondary">暂无地图数据</NText>
        </div>
      </NSpin>
    </NCard>
  </div>
</template>

<style scoped>
.main-container {
  min-height: 100vh;
  background-color: #f5f5f7;
  padding: 20px;
}

.map-container {
  display: flex;
  justify-content: center;
  align-items: center;
}

.map-placeholder {
  text-align: center;
  padding: 100px 0;
}
</style>