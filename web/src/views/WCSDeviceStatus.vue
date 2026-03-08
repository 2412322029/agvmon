<script setup>
import { NButton, NCard, NInput, NSelect, NSpace, useMessage } from 'naive-ui'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import WCSDeviceGrid from '../components/WCSDeviceGrid.vue'

const message = useMessage()

const selectedDeviceType = ref('BUFFER')
const options = ref({})
const loadingOptions = ref(false)
const selectname = ref('')
const selectlable = ref('')
watch(selectname, (newVal) => {
  if (newVal) {
    cmsSearchText.value = newVal.split('_')[0]
    selectlable.value = options.value[selectedDeviceType.value].find(item => item.value === newVal).label
  }
})
watch(selectedDeviceType, (newVal) => {
  if (newVal) {
    selectname.value = ""
    cmsSearchText.value = ""
    selectlable.value = ""
  }
})
const mapname = ref("")
const getmaplist = async () => {
  const response = await fetch('/api/rcms/maplist', {
    method: 'GET',
  })
  const data = await response.json()
  if (data?.length == 0) {
    message.error("获取地图列表失败")
    return
  }
  mapname.value = data[0]['name']
  console.log(mapname.value);

}

const pinnedItems = ref([])
const loadPinnedItems = () => {
  if (mapname.value) {
    const cached = localStorage.getItem(`pinned_${mapname.value}`)
    if (cached) {
      try {
        pinnedItems.value = JSON.parse(cached)
      } catch (e) {
        console.error('加载固定项失败:', e)
        pinnedItems.value = []
      }
    }
  }
}
const savePinnedItems = () => {
  if (mapname.value) {
    localStorage.setItem(`pinned_${mapname.value}`, JSON.stringify(pinnedItems.value))
  }
}
const isItemPinned = (cmsIndex, deviceType) => {
  return pinnedItems.value.some(
    item => item.cmsIndex === cmsIndex && item.deviceType === deviceType
  )
}
const addPinnedItem = (cmsIndex, deviceType, label) => {
  if (!isItemPinned(cmsIndex, deviceType)) {
    pinnedItems.value.push({ cmsIndex, deviceType, label })
    savePinnedItems()
  }
}
const removePinnedItem = (cmsIndex, deviceType) => {
  pinnedItems.value = pinnedItems.value.filter(
    item => !(item.cmsIndex === cmsIndex && item.deviceType === deviceType)
  )
  savePinnedItems()
}
const refreshPinnedItem = ({ cmsIndex, deviceType }) => {
  fetchStatusData({ index: cmsIndex, deviceType })
}
const refreshAllPinned = () => {
  pinnedItems.value.forEach(item => {
    refreshPinnedItem(item)
  })
}

const deviceTypeOptions = ref([
  { label: ' BUFFER ', value: 'BUFFER' },
  { label: ' EQ ', value: 'EQ' },
  { label: ' STK ', value: 'STK' },
  { label: ' CV ', value: 'CV' }
])

const fetchDeviceTypeOptions = async () => {
  loadingOptions.value = true
  try {
    const response = await fetch('/api/rcs_web/get_device_type_options')
    const data = await response.json()
    if (data && data.options) {
      options.value = data.options
      processDuplicateValues()
      deviceTypeOptions.value = Object.keys(options.value).map(key => ({
        label: key,
        value: key
      }))
    }
  } catch (error) {
    console.error('获取设备类型选项失败:', error)
  } finally {
    loadingOptions.value = false
  }
}

const processDuplicateValues = () => {
  for (const deviceType in options.value) {
    const valueMap = new Map()
    options.value[deviceType] = options.value[deviceType].map((item) => {
      if (valueMap.has(item.value)) {
        const count = valueMap.get(item.value)
        valueMap.set(item.value, count + 1)
        return {
          value: `${item.value}_${count + 1}`,
          label: item.label,
        }
      } else {
        valueMap.set(item.value, 1)
        return {
          value: item.value,
          label: item.label,
        }
      }
    })
  }
}
// console.log(options.value[selectedDeviceType.value]);

const statusData = ref([])
const pinnedStatusData = ref({})
const loading = ref(false)
const refreshInterval = ref(null)
const cmsSearchText = ref('')


// watch(cmsSearchText, (newVal) => {
//   fetchStatusData()
// })
watch(loading, (newVal) => {
    console.log(loading.value);
})

const fetchStatusData = async ({ index, deviceType } = {}) => {
  if (!deviceType) deviceType = selectedDeviceType.value
  if (!index) index = cmsSearchText.value
  if (!index) {
    message.error('请输入CMS索引')
    loading.value = false
    return
  }
  console.log('[fetchStatusData] called with index:', index, 'deviceType:', deviceType)
  loading.value = true

  try {
    const response = await fetch(`/api/wcs/searchDeviceStatusInfo?cms_index=${index}&device_type=${deviceType}`)
    const data = await response.json()

    if (data && data.params && data.params.status) {
      const key = `${index}_${deviceType}`
      pinnedStatusData.value[key] = data.params.status
      if (!isItemPinned(index, deviceType)) {
        statusData.value = data.params.status
      }
    } else {
      const key = `${index}_${deviceType}`
      pinnedStatusData.value[key] = []
      if (!isItemPinned(index, deviceType)) {
        statusData.value = []
      }
    }
    if (data.code === 0) {
      message.success(`${deviceType} ${index} 数据刷新成功`)
    } else {
      message.error(`${deviceType} ${index} 数据刷新失败: ${data.message}`)
    }
  } catch (error) {
    console.error('获取状态数据失败:', error)
    message.error('获取数据失败')
    const key = `${index}_${deviceType}`
    pinnedStatusData.value[key] = []
    if (!isItemPinned(index, deviceType)) {
      statusData.value = []
    }
  } finally {
    loading.value = false
  }
}

const onPinClick = () => {
  console.log('[onPinClick] called, cmsSearchText:', cmsSearchText.value, 'selectlable:', selectlable.value)
  if (cmsSearchText.value) {
    const label = selectlable.value
    addPinnedItem(cmsSearchText.value, selectedDeviceType.value, label)
    message.success('已固定到顶部')
  } else {
    message.error('请输入CMS索引')
  }
}

const onSidebarItemClick = (item) => {
  const element = document.querySelector(`[data-item-key="${item.cmsIndex}_${item.deviceType}"]`)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

const startAutoRefresh = () => {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
  }
  refreshInterval.value = setInterval(fetchStatusData, 3000)
}

const stopAutoRefresh = () => {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
    refreshInterval.value = null
  }
}

onMounted(() => {
  fetchDeviceTypeOptions()
  getmaplist()
  setTimeout(() => {
    loadPinnedItems()
  }, 50)
  loading.value = false
})

onBeforeUnmount(() => {
  stopAutoRefresh()
})
</script>

<template>
  <div class="main-container">
    <div style="">
      <h1 class="page-title">WCS设备状态监控</h1>
      <div class="sidebar">
        固定项:
        <div v-for="item in pinnedItems" :key="`${item.cmsIndex}_${item.deviceType}`" class="sidebar-item"
          :class="{ 'sidebar-item-active': item.cmsIndex === cmsSearchText && item.deviceType === selectedDeviceType }"
          @click="onSidebarItemClick(item)">
          <div class="sidebar-item-label">{{ item.label }}</div>
        </div>
      </div>
    </div>


    <div class="content">
      <NCard :bordered="false" style="max-width: 1200px; margin: 0 auto;">
        <div class="controls">
          <NSpace align="center">
            <span>设备类型：</span>
            <NButton v-for="deviceType in deviceTypeOptions" :key="deviceType.value"
              :type="selectedDeviceType === deviceType.value ? 'primary' : 'default'"
              @click="selectedDeviceType = deviceType.value" :bordered="false">
              {{ deviceType.label }}
            </NButton>
            <NSelect v-if='options[selectedDeviceType]' :options='options[selectedDeviceType]'
              v-model:value="selectname" style="width: 160px;">
            </NSelect>
            <span v-else>加载中...</span>
            <span>CMS索引：</span>
            <NInput v-model:value="cmsSearchText" placeholder="输入CMS索引" style="width: 100px" />
            <NButton type="primary" @click="fetchStatusData" :loading="loading" :disabled="!cmsSearchText">
              刷新
            </NButton>
            

            <!-- <NButton type="success" @click="startAutoRefresh" :type="refreshInterval ? 'success' : 'default'">
            自动刷新
          </NButton> -->
          </NSpace>
        </div>
        <div style="margin-top: 20px;">
          <WCSDeviceGrid :device-type="selectedDeviceType" :d-name="selectlable" :cms-index="cmsSearchText"
            :status-data="pinnedStatusData[`${cmsSearchText}_${selectedDeviceType}`] || statusData"
            :is-pinned="false" @pin="onPinClick" />
        </div>
        <div style="border: 1px solid green;">
          <div v-for="item in pinnedItems" :key="`${item.cmsIndex}_${item.deviceType}`" style="margin-top: 20px;"
            :data-item-key="`${item.cmsIndex}_${item.deviceType}`">
            <WCSDeviceGrid :device-type="item.deviceType" :d-name="item.label" :cms-index="item.cmsIndex"
              :status-data="pinnedStatusData[`${item.cmsIndex}_${item.deviceType}`] || []" :is-pinned="true"
              @refresh="refreshPinnedItem(item)" @unpin="removePinnedItem(item.cmsIndex, item.deviceType)" />
          </div>
        </div>
      </NCard>
    </div>
  </div>
</template>

<style scoped>
.main-container {
  min-height: 80vh;
  padding: 20px;
}

[data-theme="light"] {
  background-color: #f5f5f7;
}

[data-theme="dark"] {
  background-color: #141414;
}

.page-title {
  text-align: center;
  margin-bottom: 20px;
  font-size: 24px;
}

[data-theme="dark"] .page-title {
  color: #fff;
}

.controls {
  padding: 15px;
  background: var(--n-card-color);
  border-bottom: 1px solid var(--n-divider-color);
}

.n-card {
  margin-top: 10px;
}

.n-button {
  margin: 0 5px;
}

.layout-container {
  display: flex;
  gap: 20px;
}

.content {
  margin-top: 5px;
}

.sidebar {
  display: flex;
  top: 20px;
  /* background: var(--n-card-color); */
  border-radius: 8px;
  padding: 5px;
  height: fit-content;
  top: 20px;
  z-index: 10;
}

.sidebar-title {
  font-size: 16px;
  font-weight: 600;
  border-bottom: 1px solid var(--n-divider-color);
  color: var(--n-text-color);
}

.sidebar-empty {
  font-size: 14px;
  color: var(--n-text-color-2);
  text-align: center;
  padding: 20px 0;
}

.sidebar-item {
  padding: 0 6px;
  background: var(--n-card-color);
  border: 1px solid var(--n-divider-color);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.sidebar-item:hover {
  border-color: var(--n-primary-color);
  background: var(--n-item-color-hover);
}

.sidebar-item-active {
  border-color: var(--n-primary-color);
  background: var(--n-item-color-active);
  font-weight: 500;
}

.sidebar-item-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--n-text-color);
}

@media (max-width: 768px) {
  .main-container {
    padding: 10px;
  }

  .page-title {
    font-size: 20px;
    margin-bottom: 15px;
  }

  .controls {
    padding: 10px;
  }

  .controls .n-space {
    flex-wrap: wrap;
    gap: 8px;
  }

  .controls .n-input {
    width: 120px;
  }

  .controls .n-select {
    width: 120px;
  }

  .sidebar {
    width: 100%;
    min-width: auto;
    margin-bottom: 10px;
  }

  .sidebar-item {
    padding: 4px 8px;
    font-size: 13px;
  }

  .sidebar-item-label {
    font-size: 13px;
  }

  .n-card {
    margin-top: 15px;
  }
}

@media (max-width: 480px) {
  .page-title {
    font-size: 18px;
    margin-bottom: 12px;
  }

  .sidebar-item {
    padding: 3px 6px;
    font-size: 12px;
  }

  .sidebar-item-label {
    font-size: 12px;
  }

  .device-grid-wrapper {
    margin-bottom: 10px;
  }
}
</style>
