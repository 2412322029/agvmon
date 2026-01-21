<script setup>
import { NButton, NCard, NCheckbox, NResult, useMessage } from 'naive-ui'
import { onMounted, onUnmounted, ref } from 'vue'

// Build from Cache
const cacheLoading = ref(false)
const cacheResult = ref(null)

// Build from Raw
const rawLoading = ref(false)
const rawResult = ref(null)
const useFakeData = ref(false)

const message = useMessage()

// Build from Cache function
const buildFromCache = async () => {
  cacheLoading.value = true
  cacheResult.value = null
  
  try {
    const response = await fetch('/api/rcms/build_from_cache')
    const data = await response.json()
    
    if (data.message === 'RCMS cache built successfully') {
      cacheResult.value = { success: true, message: data.message }
      message.success('Cache built successfully')
    } else {
      cacheResult.value = { success: false, message: data.message, errors: data.errors }
      message.error('Failed to build cache')
    }
  } catch (error) {
    cacheResult.value = { success: false, message: 'Network error', errors: [error.message] }
    message.error('Network error')
  } finally {
    cacheLoading.value = false
  }
}

// Build from Raw function
const buildFromRaw = async () => {
  rawLoading.value = true
  rawResult.value = null
  
  try {
    const url = `/api/rcms/build_from_raw?fake=${useFakeData.value}`
    const response = await fetch(url)
    const data = await response.json()
    
    if (data.message === 'RCMS raw data built successfully') {
      rawResult.value = { success: true, message: data.message }
      message.success('Raw data built successfully')
    } else {
      rawResult.value = { success: false, message: data.message, errors: data.errors }
      message.error('Failed to build raw data')
    }
  } catch (error) {
    rawResult.value = { success: false, message: 'Network error', errors: [error.message] }
    message.error('Network error')
  } finally {
    rawLoading.value = false
  }
}

// ZeroMQ Process Management
const zeromqLoading = ref(false)
const zeromqResult = ref(null)
const zeromqInfo = ref(null)
const zeromqStatus = ref('stopped') // stopped, running, error
const isStopActionPending = ref(false)

// Helper functions
const hasErrorInResult = (result) => {
  return result.error || (result.message && result.message.includes('错误'));
}

const getResultTitle = (result) => {
  if (result.error) return 'Error';
  if (result.message) return 'Result';
  return 'Info';
}

// Get ZeroMQ program info
const getZeromqInfo = async () => {
  try {
    const response = await fetch('/api/rcms/zeromq_program_info')
    const data = await response.json()
    
    if (data.message === '程序信息获取成功') {
      zeromqInfo.value = data.info
      zeromqStatus.value = 'running'
    } else if (data.message === '未找到程序信息') {
      zeromqInfo.value = null
      zeromqStatus.value = 'stopped'
    } else {
      zeromqInfo.value = null
      zeromqStatus.value = 'error'
    }
  } catch (error) {
    zeromqInfo.value = null
    zeromqStatus.value = 'error'
  }
}

// Start ZeroMQ process
const startZeromqProcess = async () => {
  zeromqLoading.value = true
  isStopActionPending.value = false
  zeromqResult.value = null
  
  try {
    const response = await fetch('/api/rcms/start_zeromq_map_update', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({})
    })
    const data = await response.json()
    
    zeromqResult.value = data
    
    if (data.message.includes('已启动') || data.message.includes('已存在')) {
      message.success(data.message)
      zeromqStatus.value = 'running'
    } else {
      message.warning(data.message)
    }
  } catch (error) {
    zeromqResult.value = { success: false, message: 'Network error', error: error.message }
    message.error('Network error')
  } finally {
    zeromqLoading.value = false
    // Refresh info after operation
    await getZeromqInfo()
  }
}

// Stop ZeroMQ process
const stopZeromqProcess = async () => {
  zeromqLoading.value = true
  isStopActionPending.value = true
  zeromqResult.value = null
  
  try {
    const response = await fetch('/api/rcms/stop_zeromq_map_update', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({})
    })
    const data = await response.json()
    
    zeromqResult.value = data
    
    if (data.message.includes('已停止')) {
      message.success(data.message)
      zeromqStatus.value = 'stopped'
    } else {
      message.warning(data.message)
    }
  } catch (error) {
    zeromqResult.value = { success: false, message: 'Network error', error: error.message }
    message.error('Network error')
  } finally {
    zeromqLoading.value = false
    isStopActionPending.value = false
    // Refresh info after operation
    await getZeromqInfo()
  }
}

// Refresh ZeroMQ info periodically
let refreshInterval = null

const startAutoRefresh = () => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
  refreshInterval = setInterval(async () => {
    await getZeromqInfo()
  }, 5000) // Refresh every 5 seconds
}

const stopAutoRefresh = () => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

// Initialize when component mounts
onMounted(() => {
  getZeromqInfo()
  startAutoRefresh()
})

// Clean up on component unmount
onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<template>
  <div class="main-container">
    <h1 class="page-title">Service Dashboard</h1>
    
    <div class="services-grid">
      <!-- Build from Cache Card -->
      <NCard title="Build from Cache" :bordered="true" class="service-card">
        <div class="service-content">
          <p>Build RCMS data from cache.</p>
          
          <NButton 
            type="primary" 
            @click="buildFromCache" 
            :loading="cacheLoading"
            size="medium"
          >
            Build from Cache
          </NButton>
          
          <div v-if="cacheResult" class="result-container">
            <NResult
              :status="cacheResult.success ? 'success' : 'error'"
              :title="cacheResult.success ? 'Success' : 'Error'"
              :description="cacheResult.message"
              size="small"
            >
              <template v-if="!cacheResult.success && cacheResult.errors" #extra>
                <div class="errors">
                  <h4>Errors:</h4>
                  <ul>
                    <li v-for="(error, index) in cacheResult.errors" :key="index">
                      {{ error }}
                    </li>
                  </ul>
                </div>
              </template>
            </NResult>
          </div>
        </div>
      </NCard>

      <!-- Build from Raw Card -->
      <NCard title="Build from Raw" :bordered="true" class="service-card">
        <div class="service-content">
          <p>Build RCMS data from raw source.</p>
          
          <div class="options">
            <NCheckbox v-model:checked="useFakeData">Use fake data</NCheckbox>
          </div>
          
          <NButton 
            type="primary" 
            @click="buildFromRaw" 
            :loading="rawLoading"
            size="medium"
          >
            Build from Raw
          </NButton>
          
          <div v-if="rawResult" class="result-container">
            <NResult
              :status="rawResult.success ? 'success' : 'error'"
              :title="rawResult.success ? 'Success' : 'Error'"
              :description="rawResult.message"
              size="small"
            >
              <template v-if="!rawResult.success && rawResult.errors" #extra>
                <div class="errors">
                  <h4>Errors:</h4>
                  <ul>
                    <li v-for="(error, index) in rawResult.errors" :key="index">
                      {{ error }}
                    </li>
                  </ul>
                </div>
              </template>
            </NResult>
          </div>
        </div>
      </NCard>
    </div>
    
    <!-- ZeroMQ Process Management Card -->
    <NCard title="ZeroMQ Process Management" :bordered="true" class="service-card">
      <div class="service-content">
        <p>Manage ZeroMQ Map Update process.</p>
        
        <div class="zeromq-controls">
          <NButton 
            type="success" 
            @click="startZeromqProcess" 
            :loading="zeromqLoading && !isStopActionPending"
            :disabled="zeromqStatus === 'running'"
            size="medium"
            style="margin-right: 10px;"
          >
            Start Process
          </NButton>
          
          <NButton 
            type="error" 
            @click="stopZeromqProcess" 
            :loading="zeromqLoading && isStopActionPending"
            :disabled="zeromqStatus !== 'running'"
            size="medium"
          >
            Stop Process
          </NButton>
        </div>
        
        <div class="status-indicator">
          <span :class="['status-badge', 
            zeromqStatus === 'running' ? 'status-running' : 
            zeromqStatus === 'stopped' ? 'status-stopped' : 'status-error'
          ]">
            Status: {{ zeromqStatus }}
          </span>
        </div>
        
        <div v-if="zeromqInfo" class="zeromq-info">
          <h4>Process Information:</h4>
          <div class="info-item">
            <strong>PID:</strong> {{ zeromqInfo.pid }}
          </div>
          <div class="info-item">
            <strong>Start Time:</strong> {{ zeromqInfo.start_time }}
          </div>
          <div class="info-item">
            <strong>Last Update:</strong> {{ zeromqInfo.last_update }}
          </div>
          <div class="info-item">
            <strong>Message Count:</strong> {{ zeromqInfo.message_count }}
          </div>
          <details class="msg-dict-details">
            <summary><strong>Message Dictionary:</strong></summary>
            <div v-for="(value, key) in zeromqInfo.msg_dict" :key="key" class="msg-item">
              <span class="msg-key">{{ key }}:</span>
              <span class="msg-value">{{ value }}</span>
            </div>
          </details>
        </div>
        
        <div v-if="zeromqResult" class="result-container">
          <NResult
            :status="hasErrorInResult(zeromqResult) ? 'error' : 'info'"
            :title="getResultTitle(zeromqResult)"
            :description="zeromqResult.message || zeromqResult.error"
            size="small"
          >
            <template #footer>
              <div v-if="zeromqResult.info" class="result-info">
                <p><strong>PID:</strong> {{ zeromqResult.info.pid }}</p>
                <p><strong>Status:</strong> {{ zeromqResult.info.start_time ? 'Running' : 'Stopped' }}</p>
              </div>
            </template>
          </NResult>
        </div>
      </div>
    </NCard>
  </div>
</template>

<style scoped>
.main-container {
  min-height: 100vh;
  background-color: #f5f5f7;
  padding: 20px;
}

.page-title {
  text-align: center;
  margin-bottom: 30px;
  font-size: 24px;
  color: #333;
}

.services-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.service-card {
  max-width: 100%;
}

.service-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 15px;
  padding: 15px;
}

.options {
  align-self: flex-start;
  margin-bottom: 5px;
}

.result-container {
  margin-top: 15px;
  width: 100%;
}

.errors {
  text-align: left;
  margin-top: 10px;
  font-size: 14px;
}

.errors h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
}

.errors ul {
  margin: 0;
  padding-left: 20px;
}

.errors li {
  margin-bottom: 4px;
  color: #ff4d4f;
}

.zeromq-controls {
  display: flex;
  gap: 10px;
  margin: 15px 0;
  justify-content: center;
}

.status-indicator {
  margin: 15px 0;
}

.status-badge {
  padding: 5px 10px;
  border-radius: 4px;
  font-weight: bold;
}

.status-running {
  background-color: #f6ffed;
  color: #52c41a;
  border: 1px solid #b7eb8f;
}

.status-stopped {
  background-color: #f9f9f9;
  color: #666;
  border: 1px solid #ddd;
}

.status-error {
  background-color: #fff2f0;
  color: #ff4d4f;
  border: 1px solid #ffccc7;
}

.zeromq-info {
  background-color: #f9f9f9;
  padding: 15px;
  border-radius: 4px;
  margin: 15px 0;
  width: 100%;
}

.zeromq-info h4 {
  margin-top: 0;
  margin-bottom: 10px;
  color: #333;
}

.info-item {
  margin-bottom: 8px;
  font-size: 14px;
}

.msg-dict-details {
  margin-top: 10px;
}

.msg-dict-details summary {
  cursor: pointer;
  font-weight: bold;
  margin-bottom: 5px;
}

.msg-item {
  display: flex;
  justify-content: space-between;
  padding: 2px 0;
  font-size: 13px;
}

.msg-key {
  font-weight: 500;
  color: #555;
  width: 120px;
}

.msg-value {
  color: #333;
  text-align: right;
  flex-grow: 1;
}

.result-info p {
  margin: 5px 0;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .services-grid {
    grid-template-columns: 1fr;
    gap: 15px;
  }
  
  .service-card {
    margin-bottom: 15px;
  }
  
  .main-container {
    padding: 15px;
  }
  
  .page-title {
    font-size: 20px;
    margin-bottom: 20px;
  }
  
  .zeromq-controls {
    flex-direction: column;
  }
  
  .zeromq-controls .n-button {
    width: 100%;
  }
  
  .msg-key {
    width: 100px;
    font-size: 12px;
  }
  
  .msg-value {
    font-size: 12px;
  }
}
</style>