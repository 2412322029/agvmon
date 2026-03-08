<script setup>
import { NButton, NCard, useMessage } from 'naive-ui'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const message = useMessage()

const props = defineProps({
  deviceType: {
    type: String,
    default: 'BUFFER'
  },
  dName: {
    type: String,
    default: ''
  },
  cmsIndex: {
    type: String,
    default: ''
  },
  statusData: {
    type: Array,
    default: () => []
  },
  isPinned: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['refresh', 'unpin', 'pin'])

const lastUpdateTime = ref(null)
const currentTime = ref(new Date())
let interval = null

onMounted(() => {
  lastUpdateTime.value = new Date()
  if (props.isPinned) {
    interval = setInterval(() => {
      currentTime.value = new Date()
    }, 1000)
  }

})

onBeforeUnmount(() => {
  if (interval) {
    clearInterval(interval)
    interval = null
  }
})

const timeDifference = computed(() => {
  if (!lastUpdateTime.value) return ''
  const diff = currentTime.value - lastUpdateTime.value
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return `（${seconds}秒前）`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `（${minutes}分${remainingSeconds}秒前）`
})

const onRefresh = () => {
  lastUpdateTime.value = new Date()
  emit('refresh')
}

const getStatusColor = (status) => {
  if (!status) return '#999'
  const service = status.service || ''

  if (service === 'IN') {
    return '#52c41a'
  } else if (service === 'OUT') {
    return '#ff4d4f'
  }
  return '#999'
}
const getpresentColor = (status) => {
  if (!status) return '#999'
  const present = status.present || ''
  const trayId = status.trayId || ''

  if ((present === 'ON' && trayId) || (present === 'OFF' && !trayId)) {
    return '#52c41a'
  } else if ((present === 'ON' && !trayId) || (present === 'OFF' && trayId)) {
    return '#ff4d4f'
  }
  return '#999'
}
const getArrowDirection = (portPos, trayId) => {
  return trayId ? '📦' : ''
}

const onUnpin = () => {
  emit('unpin')
}

const onPin = () => {
  emit('pin')
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
    <NCard :bordered="false" size="small">
      <template #header>
        <div class="header-content">
          <span class="title-text">{{ dName || "设备状态" }} </span>
          <span class="time-diff" v-if="isPinned && statusData.length > 0">{{ timeDifference }}</span>
        </div>
      </template>
      <template #header-extra>
        <span class="header-extra">{{ deviceType }} - {{ cmsIndex }} </span>
        <NButton v-if="isPinned" type="default" size="small" @click="onRefresh" :loading="false" circle
          style="margin: 0 5px;">
          <template #icon>
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
              <path d="M16 21h5v-5" />
            </svg>
          </template>
        </NButton>
        <NButton v-if="isPinned" type="default" size="small" @click="onUnpin" circle>
          <template #icon>
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </template>
        </NButton>
        <NButton v-if="!isPinned" type="default" size="small" @click="onPin" circle style="margin: 0 5px;">
          <template #icon>
            <svg t="1772969854733" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg"
              p-id="2076" width="200" height="200">
              <path
                d="M648.728381 130.779429a73.142857 73.142857 0 0 1 22.674286 15.433142l191.561143 191.756191a73.142857 73.142857 0 0 1-22.137905 118.564571l-67.876572 30.061715-127.341714 127.488-10.093714 140.239238a73.142857 73.142857 0 0 1-124.684191 46.445714l-123.66019-123.782095-210.724572 211.699809-51.833904-51.614476 210.846476-211.821714-127.926857-128.024381a73.142857 73.142857 0 0 1 46.299428-124.635429l144.237715-10.776381 125.074285-125.220571 29.379048-67.779048a73.142857 73.142857 0 0 1 96.207238-38.034285z m-29.086476 67.120761l-34.913524 80.530286-154.087619 154.331429-171.398095 12.751238 303.323428 303.542857 12.044191-167.399619 156.233143-156.428191 80.384-35.59619-191.585524-191.73181z"
                p-id="2077" fill="#7EE8C5"></path>
            </svg>
          </template>
        </NButton>
      </template>
      <div v-if="statusData.length > 0" class="grid-wrapper">

        <div v-if="groupedData.UP && groupedData.UP.length > 0" class="grid-section">
          <div class="grid-content">

            <div v-for="item in groupedData.UP" :key="item.cmsIndex + item.portPos" class="device-cell">
              <div class="device-icon"
                :style="{ backgroundColor: getStatusColor(item), border: '4px solid ' + getpresentColor(item) + '' }">
                <span class="arrow">{{ item.present === 'ON' && item.trayId ? '📦' : '' }}</span>
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
                  <span class="hover-value">{{ item.manualOp }}</span>
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
              <div class="device-icon"
                :style="{ backgroundColor: getStatusColor(item), border: '4px solid ' + getpresentColor(item) + '' }">
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
  padding: 5px;
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
  /* border-radius: 6px; */
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
  top: -8px;
  left: 50%;
  transform: translateX(-50%);
  border-width: 6px 6px 0;
  border-style: solid;
  border-color: var(--n-text-color);

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

.present-icon {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 12px;
  height: 12px;
}

.present-icon svg {
  width: 100%;
  height: 100%;
}

@media (max-width: 768px) {
  .device-grid-wrapper {
    margin-bottom: 10px;
  }

  .grid-wrapper {
    gap: 12px;
  }

  .grid-section {
    padding: 8px;
  }

  .section-title {
    font-size: 13px;
    margin-bottom: 8px;
  }

  .grid-content {
    gap: 5px;
  }

  .device-cell {
    flex: 0 0 36px;
    max-width: 36px;
  }

  .device-icon {
    width: 28px;
    height: 28px;
    border-width: 3px;
  }

  .device-icon .arrow {
    font-size: 14px;
  }

  .present-icon {
    width: 10px;
    height: 10px;
    bottom: 1px;
    right: 1px;
  }

  .device-number {
    font-size: 9px;
    margin-top: 2px;
  }

  .device-hover-info {
    width: 150px;
    padding: 5px;
    margin-top: 3px;
    font-size: 11px;
  }

  .hover-info-item {
    margin-bottom: 2px;
  }

  .hover-label {
    width: 45px;
    font-size: 10px;
  }

  .hover-value {
    font-size: 10px;
  }

  .device-hover-info::before {
    border-width: 4px 4px 0;
  }
}

@media (max-width: 480px) {
  .device-grid-wrapper {
    margin-bottom: 8px;
  }

  .grid-wrapper {
    gap: 10px;
  }

  .grid-section {
    padding: 6px;
  }

  .section-title {
    font-size: 12px;
    margin-bottom: 6px;
  }

  .grid-content {
    gap: 4px;
  }

  .device-cell {
    flex: 0 0 32px;
    max-width: 32px;
  }

  .device-icon {
    width: 24px;
    height: 24px;
    border-width: 2px;
  }

  .device-icon .arrow {
    font-size: 12px;
  }

  .present-icon {
    width: 8px;
    height: 8px;
    bottom: 0;
    right: 0;
  }

  .device-number {
    font-size: 8px;
    margin-top: 1px;
  }

  .device-hover-info {
    width: 130px;
    padding: 4px;
    margin-top: 2px;
    font-size: 10px;
  }

  .hover-info-item {
    margin-bottom: 1px;
  }

  .hover-label {
    width: 40px;
    font-size: 9px;
  }

  .hover-value {
    font-size: 9px;
  }

  .device-hover-info::before {
    border-width: 3px 3px 0;
  }
}
</style>
