<script setup>
import { NButton, NCard, useMessage } from 'naive-ui'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const message = useMessage()

const props = defineProps({
  deviceType: { type: String, default: 'BUFFER' },
  dName: { type: String, default: '' },
  cmsIndex: { type: String, default: '' },
  statusData: { type: Array, default: () => [] },
  isPinned: { type: Boolean, default: false }
})

const emit = defineEmits(['refresh', 'unpin', 'pin'])

const lastUpdateTime = ref(null)
const currentTime = ref(new Date())
let interval = null

onMounted(() => {
  lastUpdateTime.value = new Date()
  interval = setInterval(() => { currentTime.value = new Date() }, 1000)
})

onBeforeUnmount(() => {
  if (interval) { clearInterval(interval); interval = null }
})

const timeDifference = computed(() => {
  if (!lastUpdateTime.value) return ''
  const diff = currentTime.value - lastUpdateTime.value
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return `（${seconds}秒前）`
  const minutes = Math.floor(seconds / 60)
  return `（${minutes}分${seconds % 60}秒前）`
})

const onRefresh = () => {
  lastUpdateTime.value = new Date()
  emit('refresh')
}

const onUnpin = () => emit('unpin')
const onPin = () => emit('pin')

const getStatusColor = (status) => {
  if (!status) return '#999'
  if (status.service === 'IN') return '#52c41a'
  if (status.service === 'OUT') return '#ff4d4f'
  return '#999'
}

const getpresentColor = (status) => {
  if (!status) return '#999'
  const present = status.present || ''
  const trayId = status.trayId || ''
  if ((present === 'ON' && trayId) || (present === 'OFF' && !trayId)) return '#52c41a'
  if ((present === 'ON' && !trayId) || (present === 'OFF' && trayId)) return '#ff4d4f'
  return '#999'
}

const isCacheMismatch = (item) => item.cacheMatch === false
const isLocked = (item) => !!item.lockSource
const hasBothIds = (item) => !!(item.trayId && item.cacheCarrierId)

const selectedItem = ref(null)

const onCellClick = (item) => {
  selectedItem.value = selectedItem.value?.cmsIndex === item.cmsIndex && selectedItem.value?.portPos === item.portPos ? null : item
}

const formatRelativeTime = (dateStr) => {
  if (!dateStr) return ''
  const now = new Date()
  const target = new Date(dateStr.replace(' ', 'T'))
  const diffMs = now - target
  if (diffMs < 0) return '0h'
  const hours = diffMs / 3600000
  if (hours < 1) return `${(hours * 60).toFixed(0)}m`
  return `${hours.toFixed(1)}h`
}

const groupedData = computed(() => {
  const groups = {}
  props.statusData.forEach(item => {
    const key = item.portPos || 'UNKNOWN'
    if (!groups[key]) groups[key] = []
    groups[key].push(item)
  })
  return groups
})

const WCS_KEYS = ['cmsIndex', 'portPos', 'present', 'service', 'trayId', 'traySize', 'manualOp', 'eqRequest']
const SKIP_KEYS = ['cacheMatch']

const showMappingTable = ref(false)

const toggleMappingTable = () => {
  showMappingTable.value = !showMappingTable.value
}

const allMappingFields = computed(() => {
  const fields = new Set()
  props.statusData.forEach(item => {
    for (const [key, value] of Object.entries(item)) {
      if (!WCS_KEYS.includes(key) && !SKIP_KEYS.includes(key) && (value || value === 0 || value === false)) {
        fields.add(key)
      }
    }
  })
  return [...fields]
})

const selectedDetail = computed(() => {
  if (!selectedItem.value) return { wcs: [], port: [] }
  const wcs = []
  const port = []
  for (const [key, value] of Object.entries(selectedItem.value)) {
    if (SKIP_KEYS.includes(key)) continue
    if (WCS_KEYS.includes(key)) {
      wcs.push({ key, value })
    } else if (value || value === 0 || value === false) {
      port.push({ key, value })
    }
  }
  return { wcs, port }
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
        <NButton size="tiny" @click="toggleMappingTable" :type="showMappingTable ? 'primary' : 'default'" style="margin-right: 6px;">映射</NButton>
        <NButton type="default" size="small" @click="onRefresh" circle style="margin-right: 6px;">
          <template #icon>
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" /><path d="M3 3v5h5" /><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" /><path d="M16 21h5v-5" />
            </svg>
          </template>
        </NButton>
        <NButton v-if="isPinned" type="default" size="small" @click="onUnpin" circle>
          <template #icon>
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 6 6 18" /><path d="m6 6 12 12" />
            </svg>
          </template>
        </NButton>
        <NButton v-if="!isPinned" type="default" size="small" @click="onPin" circle style="margin: 0 5px;">
          <template #icon>
            <svg t="1772969854733" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="2076" width="20" height="20">
              <path d="M648.728381 130.779429a73.142857 73.142857 0 0 1 22.674286 15.433142l191.561143 191.756191a73.142857 73.142857 0 0 1-22.137905 118.564571l-67.876572 30.061715-127.341714 127.488-10.093714 140.239238a73.142857 73.142857 0 0 1-124.684191 46.445714l-123.66019-123.782095-210.724572 211.699809-51.833904-51.614476 210.846476-211.821714-127.926857-128.024381a73.142857 73.142857 0 0 1 46.299428-124.635429l144.237715-10.776381 125.074285-125.220571 29.379048-67.779048a73.142857 73.142857 0 0 1 96.207238-38.034285z m-29.086476 67.120761l-34.913524 80.530286-154.087619 154.331429-171.398095 12.751238 303.323428 303.542857 12.044191-167.399619 156.233143-156.428191 80.384-35.59619-191.585524-191.73181z" p-id="2077" fill="#7EE8C5"></path>
            </svg>
          </template>
        </NButton>
      </template>

      <div v-if="statusData.length > 0" class="grid-wrapper">

        <!-- UP 层 -->
        <div v-if="groupedData.UP && groupedData.UP.length > 0" class="grid-section">
          <div class="section-label">UP</div>
          <div class="grid-content">
            <div v-for="item in groupedData.UP" :key="item.cmsIndex + item.portPos" class="device-cell"
              :class="{ 'cell-mismatch': isCacheMismatch(item), 'cell-locked': isLocked(item), 'cell-selected': selectedItem?.cmsIndex === item.cmsIndex && selectedItem?.portPos === item.portPos }"
              @click="onCellClick(item)">
              <div class="device-icon"
                :style="{ backgroundColor: getStatusColor(item), border: '4px solid ' + getpresentColor(item) + '' }">
                <!-- 匹配状态 -->
                <span v-if="hasBothIds(item) && !isCacheMismatch(item)" class="match-icon match-ok">✓</span>
                <span v-if="isCacheMismatch(item)" class="match-icon match-fail">✗</span>
                <span v-if="!hasBothIds(item) && item.trayId && !item.cacheCarrierId" class="match-icon match-arrow">📦</span>
                <!-- 锁定 -->
                <span v-if="isLocked(item)" class="lock-icon" :title="item.lockSource">🔒</span>
              </div>
              <div class="device-number" :title="item.cmsIndex">{{ item.bufPort || item.cmsIndex.slice(-2) }}</div>
              <div v-if="item.dateChg" class="device-datechg">{{ formatRelativeTime(item.dateChg) }}</div>
            </div>
          </div>
        </div>

        <!-- DOWN 层 -->
        <div v-if="groupedData.DOWN && groupedData.DOWN.length > 0" class="grid-section">
          <div class="section-header">
            <span class="section-label">DOWN</span>
          </div>
          <div class="grid-content">
            <div v-for="item in groupedData.DOWN" :key="item.cmsIndex + item.portPos" class="device-cell"
              :class="{ 'cell-mismatch': isCacheMismatch(item), 'cell-locked': isLocked(item), 'cell-selected': selectedItem?.cmsIndex === item.cmsIndex && selectedItem?.portPos === item.portPos }"
              @click="onCellClick(item)">
              <div class="device-icon"
                :style="{ backgroundColor: getStatusColor(item), border: '4px solid ' + getpresentColor(item) + '' }">
                <span v-if="hasBothIds(item) && !isCacheMismatch(item)" class="match-icon match-ok">✓</span>
                <span v-if="isCacheMismatch(item)" class="match-icon match-fail">✗</span>
                <span v-if="!hasBothIds(item) && item.trayId && !item.cacheCarrierId" class="match-icon match-arrow">📦</span>
                <span v-if="isLocked(item)" class="lock-icon" :title="item.lockSource">🔒</span>
              </div>
              <div class="device-number" :title="item.cmsIndex">{{ item.bufPort || item.cmsIndex.slice(-2) }}</div>
              <div v-if="item.dateChg" class="device-datechg">{{ formatRelativeTime(item.dateChg) }}</div>
            </div>
          </div>
        </div>

        <!-- 映射列表弹窗 -->
        <div v-if="showMappingTable" class="mapping-modal" @click.self="showMappingTable = false">
          <div class="mapping-modal-content">
            <div class="mapping-modal-header">
              <span>{{ dName || deviceType }} 全部映射 ({{ statusData.length }}项)</span>
              <NButton size="tiny" @click="showMappingTable = false" circle>✕</NButton>
            </div>
            <div class="mapping-modal-body">
              <table>
                <thead>
                  <tr>
                    <th>port</th>
                    <th>cmsIndex</th>
                    <th>pos</th>
                    <th>trayId</th>
                    <th>carrierId</th>
                    <th v-if="allMappingFields.includes('lockSource')">lock</th>
                    <th v-if="allMappingFields.includes('dateChg')">修改时间</th>
                    <th v-if="allMappingFields.includes('present')">present</th>
                    <th v-if="allMappingFields.includes('service')">service</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in statusData" :key="item.cmsIndex + item.portPos"
                    :class="{ 'row-mismatch': isCacheMismatch(item), 'row-locked': isLocked(item) }">
                    <td>{{ item.bufPort || '-' }}</td>
                    <td>{{ item.cmsIndex }}</td>
                    <td>{{ item.portPos }}</td>
                    <td :class="{ 'text-mismatch': isCacheMismatch(item) }">{{ item.trayId || '-' }}</td>
                    <td :class="{ 'text-mismatch': isCacheMismatch(item) }">{{ item.cacheCarrierId || '-' }}</td>
                    <td v-if="allMappingFields.includes('lockSource')" class="text-locked">{{ item.lockSource || '-' }}</td>
                    <td v-if="allMappingFields.includes('dateChg')">{{ item.dateChg || '-' }}</td>
                    <td v-if="allMappingFields.includes('present')">{{ item.present || '-' }}</td>
                    <td v-if="allMappingFields.includes('service')">{{ item.service || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- 详情面板 -->
        <div v-if="selectedItem" class="detail-panel">
          <div class="detail-header">
            <span>{{ selectedItem.cmsIndex }} / {{ selectedItem.portPos }}</span>
            <NButton size="tiny" @click="selectedItem = null" circle>✕</NButton>
          </div>
          <div class="detail-body">
            <div class="detail-section">
              <div class="detail-section-title">实时信息 (WCS)</div>
              <div v-for="field in selectedDetail.wcs" :key="field.key" class="detail-row">
                <span class="dl">{{ field.key }}</span>
                <span class="dv" :class="{ 'text-mismatch': field.key === 'trayId' && isCacheMismatch(selectedItem) }">{{ field.value || '-' }}</span>
              </div>
            </div>
            <div class="detail-section">
              <div class="detail-section-title">映射信息 (Port)</div>
              <div v-for="field in selectedDetail.port" :key="field.key" class="detail-row">
                <span class="dl">{{ field.key }}</span>
                <span class="dv" :class="{ 'text-mismatch': field.key === 'cacheCarrierId' && isCacheMismatch(selectedItem), 'text-locked': field.key === 'lockSource' && selectedItem.lockSource }">{{ field.value ?? '-' }}</span>
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
.device-grid-wrapper { margin-bottom: 20px; }
.grid-wrapper { display: flex; flex-direction: column; gap: 0px; }
.grid-section { background: var(--n-card-color); border-radius: 8px; padding: 5px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.section-label { font-size: 12px; font-weight: 600; color: var(--n-text-color-2); padding-left: 2px; }
.grid-content { display: flex; flex-wrap: wrap; gap: 6px; align-items: flex-start; width: 100%; }

.device-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: pointer;
  padding: 2px;
  border-radius: 6px;
  border: 2px solid transparent;
  transition: all 0.2s ease;
  min-width: 44px;
}
.device-cell:hover { background: var(--n-item-color-hover); }
.device-cell.cell-selected { border-color: #1890ff; background: rgba(24,144,255,0.08); }
.device-cell.cell-mismatch { background: rgba(255,77,79,0.06); }
.device-cell.cell-locked { background: rgba(250,173,20,0.06); }

.device-icon {
  width: 40px; height: 40px;
  display: flex; align-items: center; justify-content: center;
  position: relative;
  transition: all 0.3s ease;
}

.match-icon { font-size: 18px; font-weight: bold; line-height: 1; }
.match-ok { color: #1890ff; }
.match-fail { color: #ff4d4f; animation: pulse 1s ease-in-out infinite; }
.match-arrow { font-size: 20px; }

.lock-icon {
  position: absolute; top: -6px; right: -6px;
  font-size: 11px; line-height: 1;
}

.device-number {
  font-size: 13px; text-align: center; color: var(--n-text-color);
  margin-top: 2px; font-weight: 600;
}
.device-datechg {
  font-size: 10px; text-align: center; color: var(--n-text-color-2);
  margin-top: 1px; white-space: nowrap;
  max-width: 60px; overflow: hidden; text-overflow: ellipsis;
}

/* 详情面板 */
.detail-panel {
  margin-top: 12px;
  border: 1px solid #1890ff;
  border-radius: 8px;
  background: var(--n-card-color);
  overflow: hidden;
}
.detail-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px;
  background: rgba(24,144,255,0.08);
  border-bottom: 1px solid var(--n-divider-color);
  font-weight: 600; font-size: 14px;
}
/* 映射列表弹窗 */
.mapping-modal {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
}
.mapping-modal-content {
  background: #fff; border-radius: 12px;
  width: 92vw; max-width: 960px; max-height: 85vh;
  display: flex; flex-direction: column; box-shadow: 0 12px 48px rgba(0,0,0,0.25);
}
[data-theme="dark"] .mapping-modal-content { background: #1a1a1a; }
.mapping-modal-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 20px; border-bottom: 1px solid #e8e8e8;
  font-weight: 600; font-size: 16px;
}
[data-theme="dark"] .mapping-modal-header { border-bottom-color: #333; }
.mapping-modal-body { overflow: auto; padding: 12px 16px; }
.mapping-modal-body table { width: 100%; border-collapse: collapse; font-size: 13px; }
.mapping-modal-body th {
  position: sticky; top: 0; background: #fafafa;
  padding: 8px 10px; text-align: left; border-bottom: 2px solid #e8e8e8;
  white-space: nowrap; z-index: 1; font-weight: 600;
}
[data-theme="dark"] .mapping-modal-body th { background: #222; border-bottom-color: #333; }
.mapping-modal-body td {
  padding: 6px 10px; border-bottom: 1px solid #f0f0f0;
  white-space: nowrap; max-width: 160px; overflow: hidden; text-overflow: ellipsis;
}
[data-theme="dark"] .mapping-modal-body td { border-bottom-color: #2a2a2a; }
.mapping-modal-body tbody tr:hover { background: rgba(24,144,255,0.04); }
.row-mismatch { background: rgba(255,77,79,0.06); }
.row-locked { background: rgba(250,173,20,0.06); }
.row-mismatch.row-locked { background: rgba(255,77,79,0.10); }
.detail-body { display: flex; gap: 0; flex-wrap: wrap; }
.detail-section {
  flex: 1; min-width: 260px; padding: 10px 12px;
}
.detail-section + .detail-section {
  border-left: 1px solid var(--n-divider-color);
}
.detail-section-title {
  font-size: 13px; font-weight: 600; color: var(--n-primary-color);
  margin-bottom: 8px; padding-bottom: 4px;
  border-bottom: 1px dashed var(--n-divider-color);
}
.detail-row { display: flex; margin-bottom: 3px; font-size: 12px; }
.dl { width: 90px; flex-shrink: 0; color: var(--n-text-color-2); }
.dv { flex: 1; word-break: break-all; color: var(--n-text-color); }

.text-mismatch { color: #ff4d4f; font-weight: 600; }
.text-locked { color: #faad14; font-weight: 600; }

.empty-grid { padding: 40px 20px; text-align: center; color: var(--n-text-color-2); }
.empty-grid-text { font-size: 14px; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

@media (max-width: 768px) {
  .device-grid-wrapper { margin-bottom: 10px; }
  .grid-section { padding: 8px; }
  .grid-content { gap: 4px; }
  .device-cell { min-width: 36px; }
  .device-icon { width: 32px; height: 32px; }
  .device-icon .match-icon { font-size: 14px; }
  .match-arrow { font-size: 16px; }
  .device-number { font-size: 11px; }
  .device-datechg { font-size: 9px; }
  .detail-body { flex-direction: column; }
  .detail-section + .detail-section { border-left: none; border-top: 1px solid var(--n-divider-color); }
}

@media (max-width: 480px) {
  .device-cell { min-width: 30px; }
  .device-icon { width: 28px; height: 28px; }
  .device-icon .match-icon { font-size: 12px; }
  .match-arrow { font-size: 14px; }
  .device-number { font-size: 10px; }
  .device-datechg { font-size: 8px; }
  .detail-row { font-size: 11px; }
  .dl { width: 70px; }
}
</style>
