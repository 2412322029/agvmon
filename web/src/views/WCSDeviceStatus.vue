<script setup>
import { NButton, NCard, NSpace, useMessage, NInput } from 'naive-ui'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import WCSDeviceGrid from '../components/WCSDeviceGrid.vue'

const message = useMessage()

const deviceTypes = ['BUFFER', 'EQ', 'STK', 'CV']
const selectedDeviceType = ref('BUFFER')
const cmsIndexMap = ref({
  BUFFER: ['202000', '203001', '203002', '203003', '203004', '203005', '203006'],
  STK: ['600501', '600502'],
  EQ: ['503101'],
  CV: ['300201', '300205', '300206', '300210']
})
const selectedCmsIndex = ref('202000')
const statusData = ref([])
const loading = ref(false)
const refreshInterval = ref(null)
const cmsSearchText = ref('')

const deviceTypeOptions = [
  { label: ' BUFFER ', value: 'BUFFER' },
  { label: ' EQ ', value: 'EQ' },
  { label: ' STK ', value: 'STK' },
  { label: ' CV ', value: 'CV' }
]

const cmsIndexOptions = ref([])

watch(selectedDeviceType, (newVal) => {
  selectedCmsIndex.value = cmsIndexMap.value[newVal]?.[0] || ''
  cmsSearchText.value = ''
  updateCmsIndexOptions()
})

const updateCmsIndexOptions = () => {
  cmsIndexOptions.value = cmsIndexMap.value[selectedDeviceType.value]?.map(index => ({
    label: index,
    value: index
  })) || []
}

const handleCmsIndexSelect = (value) => {
  selectedCmsIndex.value = value
  cmsSearchText.value = value
  fetchStatusData()
}

const handleCmsIndexSearch = (value) => {
  cmsSearchText.value = value
  const deviceCmsList = cmsIndexMap.value[selectedDeviceType.value] || []
  const matched = deviceCmsList.find(index => index === value)
  if (matched) {
    selectedCmsIndex.value = matched
    fetchStatusData()
  }
}

const fetchStatusData = async () => {
  loading.value = true
  try {
    const response = await fetch(`/api/wcs/searchDeviceStatusInfo?cms_index=${selectedCmsIndex.value}&device_type=${selectedDeviceType.value}`)
    const data = await response.json()

    if (data && data.params && data.params.status) {
      statusData.value = data.params.status
    } else {
      statusData.value = []
    }
    message.success('数据刷新成功')
  } catch (error) {
    console.error('获取状态数据失败:', error)
    message.error('获取数据失败')
    statusData.value = []
  } finally {
    loading.value = false
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
  updateCmsIndexOptions()
  fetchStatusData()
})

onBeforeUnmount(() => {
  stopAutoRefresh()
})
</script>

<template>
  <div class="main-container">
    <h1 class="page-title">WCS设备状态监控</h1>

    <NCard :bordered="false" style="max-width: 1200px; margin: 0 auto;">
      <div class="controls">
        <NSpace align="center">
          <span>设备类型：</span>
          <NButton v-for="deviceType in deviceTypeOptions" :key="deviceType.value"
            :type="selectedDeviceType === deviceType.value ? 'primary' : 'default'"
            @click="selectedDeviceType = deviceType.value" :bordered="false">
            {{ deviceType.label }}
          </NButton>

          <span>CMS索引：</span>
          <NInput v-model:value="cmsSearchText" placeholder="输入CMS索引" style="width: 150px"
            @press-enter="handleCmsIndexSearch" @change="handleCmsIndexSearch" />

          <NButton type="primary" @click="fetchStatusData" :loading="loading">
            刷新
          </NButton>

          <!-- <NButton type="success" @click="startAutoRefresh" :type="refreshInterval ? 'success' : 'default'">
            自动刷新
          </NButton> -->
        </NSpace>
      </div>

      <div style="margin-top: 20px;">
        <WCSDeviceGrid :device-type="selectedDeviceType" :cms-index="selectedCmsIndex" :status-data="statusData" />
      </div>
    </NCard>
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
</style>
