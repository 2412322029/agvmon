<script setup>
import { NCard } from 'naive-ui'
import { computed } from 'vue'

const props = defineProps({
  deviceType: {
    type: String,
    default: 'BUFFER'
  },
  cmsIndex: {
    type: String,
    default: ''
  },
  statusData: {
    type: Array,
    default: () => []
  }
})

const getStatusColor = (status) => {
  if (!status) return '#999'
  const service = status.service || ''
  const present = status.present || ''

  if (service === 'IN') {
    if (present === 'ON') return '#52c41a'
    if (present === 'OFF') return '#faad14'
  } else if (service === 'OUT') {
    if (present === 'ON') return '#ff4d4f'
    if (present === 'OFF') return '#1890ff'
  }
  return '#999'
}

const getStatusText = (status) => {
  if (!status) return '未知'
  const service = status.service || ''
  const present = status.present || ''

  if (service === 'IN') {
    return present === 'ON' ? '在库' : '离库'
  } else if (service === 'OUT') {
    return present === 'ON' ? '出库' : '空闲'
  }
  return '未知'
}

const getArrowDirection = (portPos, trayId) => {
  return trayId ? '📦' : ''
}

const getPortLayerText = (portPos) => {
  return portPos === 'UP' ? '上层' : portPos === 'DOWN' ? '下层' : '未知'
}

const groupedData = computed(() => {
  const groups = {}
  props.statusData.forEach(item => {
    const key = item.portPos || 'UNKNOWN'
    if (!groups[key]) {
      groups[key] = []
    }
    groups[key].push(item)
  })
  return groups
})

</script>

<template>
  <div class="device-grid-wrapper">
    <NCard :title="`${deviceType} 设备状态`" :bordered="false" size="small">
      <div v-if="statusData.length > 0" class="grid-wrapper">
        
        <div v-if="groupedData.UP && groupedData.UP.length > 0" class="grid-section">
          <div class="grid-content">
            
            <div v-for="item in groupedData.UP" :key="item.cmsIndex + item.portPos" class="device-cell">
              <div class="device-icon" :style="{ backgroundColor: getStatusColor(item) }">
                <span class="arrow">{{ getArrowDirection(item.portPos, item.trayId) }}</span>
              </div>
              <div class="device-number">{{ item.cmsIndex }}</div>
              <div class="device-hover-info">
                <div class="hover-info-item">
                  <span class="hover-label">service:</span>
                  <span class="hover-value">{{ item.service }}</span>
                </div>
                <div class="hover-info-item">
                  <span class="hover-label">present:</span>
                  <span class="hover-value">{{ item.present }}</span>
                </div>
                <div v-if="item.trayId" class="hover-info-item">
                  <span class="hover-label">trayId:</span>
                  <span class="hover-value">{{ item.trayId }}</span>
                </div>
                <div v-if="item.manualOp" class="hover-info-item">
                  <span class="hover-label">manualOp:</span>
                  <span class="hover-value">{{ item.manualOp }}({{ item.manualOp === '00' ? '自动' : '手动' }})</span>
                </div>
                <div v-if="item.eqRequest" class="hover-info-item">
                  <span class="hover-label">eq请求:</span>
                  <span class="hover-value">{{ item.eqRequest }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <!-- <div class="section-title">下层</div> -->
        <div v-if="groupedData.DOWN && groupedData.DOWN.length > 0" class="grid-section">
          <div class="grid-content">

            <div v-for="item in groupedData.DOWN" :key="item.cmsIndex + item.portPos" class="device-cell">
              <div class="device-icon" :style="{ backgroundColor: getStatusColor(item) }">
                <span class="arrow">{{ getArrowDirection(item.portPos, item.trayId) }}</span>
              </div>
              <div class="device-number">{{ item.cmsIndex }}</div>
              <div class="device-hover-info">
                <div class="hover-info-item">
                  <span class="hover-label">service:</span>
                  <span class="hover-value">{{ item.service }}</span>
                </div>
                <div class="hover-info-item">
                  <span class="hover-label">present:</span>
                  <span class="hover-value">{{ item.present }}</span>
                </div>
                <div v-if="item.trayId" class="hover-info-item">
                  <span class="hover-label">trayId:</span>
                  <span class="hover-value">{{ item.trayId }}</span>
                </div>
                <div v-if="item.manualOp" class="hover-info-item">
                  <span class="hover-label">manualOp:</span>
                  <span class="hover-value">{{ item.manualOp }}({{ item.manualOp === '00' ? '自动' : '手动' }})</span>
                </div>
                <div v-if="item.eqRequest" class="hover-info-item">
                  <span class="hover-label">eq请求:</span>
                  <span class="hover-value">{{ item.eqRequest }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty-grid">
        <div class="empty-grid-text">暂无设备数据</div>
      </div>
    </NCard>
  </div>
</template>

<style scoped>
.device-grid-wrapper {
  margin-bottom: 20px;
}

.grid-wrapper {
  display: flex;
  flex-direction: column;
  gap: 0px;
}

.grid-section {
  background: var(--n-card-color);
  border-radius: 8px;
  padding: 15px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--n-divider-color);
  color: var(--n-text-color);
}

.grid-content {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  width: 100%;
}

.device-cell {
  flex: 1 1 auto;
  max-width: 60px;
  min-width: 40px;
  position: relative;
  cursor: pointer;
  transition: all 0.3s ease;
}

.device-icon {
  width: 40px;
  height: 40px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto;
  transition: all 0.3s ease;
}

.device-icon .arrow {
  font-size: 20px;
  font-weight: bold;
}

.device-cms {
  font-size: 12px;
  text-align: center;
  color: var(--n-text-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.device-cms {
  font-size: 12px;
  text-align: center;
  color: var(--n-text-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.device-number {
  font-size: 11px;
  text-align: center;
  color: var(--n-text-color);
  margin-top: 4px;
  font-weight: 500;
}

.device-hover-info {
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  width: 180px;
  background: rgb(255, 255, 255);
  color: black;
  backdrop-filter: blur(15px);
  border: 1px solid green;
  border-radius: 8px;
  padding: 8px;
  z-index: 10;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  display: none;
  margin-top: 6px;
}

.device-hover-info::before {
  content: '';
  position: absolute;
  top: -6px;
  left: 50%;
  transform: translateX(-50%);
  border-width: 6px 6px 0;
  border-style: solid;
  border-color: var(--n-divider-color);
}

.device-cell:hover .device-hover-info {
  display: block;
}

.hover-info-item {
  display: flex;
  margin-bottom: 4px;
  font-size: 12px;
}

.hover-label {
  width: 70px;
  margin-right: 6px;
}

.hover-value {
  flex: 1;
  word-break: break-all;
}

.empty-grid {
  padding: 40px 20px;
  text-align: center;
  color: var(--n-text-color-2);
}

.empty-grid-text {
  font-size: 14px;
}

@media (max-width: 768px) {
  .device-grid-wrapper {
    margin-bottom: 10px;
  }

  .grid-wrapper {
    gap: 15px;
  }

  .grid-section {
    padding: 10px;
  }

  .section-title {
    font-size: 14px;
    margin-bottom: 10px;
  }

  .grid-content {
    gap: 6px;
  }

  .device-cell {
    flex: 0 0 40px;
    max-width: 40px;
  }

  .device-icon {
    width: 32px;
    height: 32px;
  }

  .device-icon .arrow {
    font-size: 16px;
  }

  .device-number {
    font-size: 10px;
    margin-top: 3px;
  }

  .device-hover-info {
    width: 160px;
    padding: 6px;
    margin-top: 4px;
  }

  .hover-info-item {
    margin-bottom: 3px;
    font-size: 11px;
  }

  .hover-label {
    width: 35px;
    font-size: 11px;
  }

  .hover-value {
    font-size: 11px;
  }

  .device-hover-info::before {
    border-width: 5px 5px 0;
  }
}

@media (max-width: 480px) {
  .device-cell {
    flex: 0 0 35px;
    max-width: 35px;
  }

  .device-icon {
    width: 28px;
    height: 28px;
  }

  .device-icon .arrow {
    font-size: 14px;
  }

  .device-number {
    font-size: 9px;
    margin-top: 2px;
  }

  .device-hover-info {
    width: 140px;
    padding: 5px;
    margin-top: 3px;
  }

  .hover-info-item {
    margin-bottom: 2px;
    font-size: 10px;
  }

  .hover-label {
    width: 30px;
    font-size: 10px;
  }

  .hover-value {
    font-size: 10px;
  }

  .device-hover-info::before {
    border-width: 4px 4px 0;
  }
}
</style>
