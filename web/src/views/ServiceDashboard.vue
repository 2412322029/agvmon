<script setup>
import RedisInfo from '@/components/redis.vue'
import { NButton, NCard, NCheckbox, NResult, useMessage } from 'naive-ui'
import { onMounted, ref } from 'vue'

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
      message.success('缓存构建成功')
    } else {
      cacheResult.value = { success: false, message: data.message, errors: data.errors }
      message.error('缓存构建失败')
    }
  } catch (error) {
    cacheResult.value = { success: false, message: '网络错误', errors: [error.message] }
    message.error('网络错误')
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
      message.success('原始数据构建成功')
    } else {
      rawResult.value = { success: false, message: data.message, errors: data.errors }
      message.error('原始数据构建失败')
    }
  } catch (error) {
    rawResult.value = { success: false, message: '网络错误', errors: [error.message] }
    message.error('网络错误')
  } finally {
    rawLoading.value = false
  }
}

// ZeroMQ Process Management
const zeromqLoading = ref(false)
const zeromqResult = ref(null)
const zeromqInfo = ref(null)
const zmq_auto = ref(null)
const zmq_auto_kill_timedelta = ref(null)
const zeromqStatus = ref('stopped') // stopped, running, error
const isStopActionPending = ref(false)

// Helper functions
const hasErrorInResult = (result) => {
  return result.error || (result.message && result.message.includes('错误'));
}

const getResultTitle = (result) => {
  if (result.error) return '错误';
  if (result.message) return '结果';
  return '信息';
}

// Get ZeroMQ program info
const getZeromqInfo = async () => {
  try {
    const response = await fetch('/api/rcms/zeromq_program_info')
    const data = await response.json()

    if (data.message === '程序信息获取成功') {
      zeromqInfo.value = data.info
      zmq_auto.value = data.zmq_auto
      zmq_auto_kill_timedelta.value = data.zmq_auto_kill_timedelta
      message.success(data.message)
      zeromqStatus.value = 'running'
    } else if (data.message === '未找到程序信息') {
      zeromqInfo.value = null
      message.success(data.message)
      zeromqStatus.value = 'stopped'
    } else {
      zeromqInfo.value = null
      message.error(JSON.stringify(data))
      zeromqStatus.value = 'error'
    }
  } catch (error) {
    zeromqInfo.value = null
    zeromqStatus.value = 'error'
    message.info(error)
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
    zeromqResult.value = { success: false, message: '网络错误', error: error.message }
    message.error('网络错误')
  } finally {
    zeromqLoading.value = false
    // Refresh info after operation
    setTimeout(() => {
      getZeromqInfo()
    }, 4000)
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
    zeromqResult.value = { success: false, message: '网络错误', error: error.message }
    message.error('网络错误')
  } finally {
    zeromqLoading.value = false
    isStopActionPending.value = false
    getZeromqInfo()
  }
}

// Initialize when component mounts
onMounted(() => {
  getZeromqInfo()
})
</script>

<template>
  <div class="main-container">
    <h1 class="page-title">服务仪表盘</h1>

    <div class="services-grid">
      <!-- Build from Cache Card -->
      <NCard title="从缓存构建" :bordered="true" class="service-card">
        <div class="service-content">
          <p>从缓存构建 RCMS 数据。</p>

          <NButton type="primary" @click="buildFromCache" :loading="cacheLoading" size="medium">
            从缓存构建
          </NButton>

          <div v-if="cacheResult" class="result-container">
            <NResult :status="cacheResult.success ? 'success' : 'error'"
              :title="cacheResult.success ? '成功' : '错误'" :description="cacheResult.message" size="small">
              <template v-if="!cacheResult.success && cacheResult.errors" #extra>
                <div class="errors">
                  <h4>错误：</h4>
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
      <NCard title="从原始数据构建" :bordered="true" class="service-card">
        <div class="service-content">
          <p>从原始数据源构建 RCMS 数据。</p>

          <div class="options">
            <NCheckbox v-model:checked="useFakeData">使用假数据</NCheckbox>
          </div>

          <NButton type="primary" @click="buildFromRaw" :loading="rawLoading" size="medium">
            从原始数据构建
          </NButton>

          <div v-if="rawResult" class="result-container">
            <NResult :status="rawResult.success ? 'success' : 'error'" :title="rawResult.success ? '成功' : '错误'"
              :description="rawResult.message" size="small">
              <template v-if="!rawResult.success && rawResult.errors" #extra>
                <div class="errors">
                  <h4>错误：</h4>
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
    <NCard title="ZeroMQ 进程管理" :bordered="true" class="service-card">
      <div class="service-content">
        <p>管理 ZeroMQ 地图更新进程。</p>

        <div class="zeromq-controls">
          <NButton type="success" @click="startZeromqProcess" :loading="zeromqLoading && !isStopActionPending"
            :disabled="zeromqStatus === 'running'" size="medium" style="margin-right: 10px;">
            启动进程
          </NButton>

          <NButton type="error" @click="stopZeromqProcess" :loading="zeromqLoading && isStopActionPending"
            :disabled="zeromqStatus !== 'running'" size="medium" style="margin-right: 10px;">
            停止进程
          </NButton>

          <NButton type="primary" @click="getZeromqInfo" :loading="zeromqLoading" size="medium">
            刷新
          </NButton>
        </div>

        <div class="status-indicator">
          <span :class="['status-badge',
            zeromqStatus === 'running' ? 'status-running' :
              zeromqStatus === 'stopped' ? 'status-stopped' : 'status-error'
          ]">
            状态: {{ zeromqStatus }}
          </span>
        </div>

        <div v-if="zeromqInfo" class="zeromq-info">
          <h4>进程信息：</h4>
          <table class="info-table">
            <tbody>
              <tr>
                <td class="info-label"><strong>PID：</strong></td>
                <td class="info-value">{{ zeromqInfo.pid }}</td>
              </tr>
              <tr>
                <td class="info-label"><strong>启动时间：</strong></td>
                <td class="info-value">{{ zeromqInfo.start_time }}</td>
              </tr>
              <tr>
                <td class="info-label"><strong>最后更新：</strong></td>
                <td class="info-value">{{ zeromqInfo.last_update }}</td>
              </tr>
              <tr>
                <td class="info-label"><strong>zmq自动启停管理：</strong></td>
                <td class="info-value">{{ zmq_auto }}</td>
              </tr>
              <tr>
                <td class="info-label"><strong>zmq自动停止时间间隔：</strong></td>
                <td class="info-value">{{ zmq_auto_kill_timedelta }}</td>
              </tr>
            </tbody>
          </table>
          <table class="msg-table">
            <tbody>
              <tr v-for="(value, key) in zeromqInfo.msg_dict" :key="key">
                <td class="msg-key">{{ key }}</td>
                <td class="msg-value">{{ value }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="zeromqResult" class="result-container">
          <NResult :status="hasErrorInResult(zeromqResult) ? 'error' : 'info'" :title="getResultTitle(zeromqResult)"
            :description="zeromqResult.message || zeromqResult.error" size="small">
            <template #footer>
              <div v-if="zeromqResult.info" class="result-info">
                <p><strong>PID：</strong> {{ zeromqResult.info.pid }}</p>
                <p><strong>状态：</strong> {{ zeromqResult.info.start_time ? '运行中' : '已停止' }}</p>
              </div>
            </template>
          </NResult>
        </div>
      </div>
    </NCard>

    <!-- Redis Info Card -->
    <RedisInfo />
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
  margin-bottom: 30px;
  font-size: 24px;
}

[data-theme="dark"] .page-title {
  color: #fff;
}

[data-theme="light"] .services-grid {
  color: #333;
}


.services-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 20px;
  max-width: 1200px;
  margin: 0 auto;
  margin-bottom: 20px;
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
  /* background-color: #f6ffed; */
  color: #52c41a;
  border: 1px solid #b7eb8f;
}

.status-stopped {
  /* background-color: #f9f9f9; */
  /* color: #666; */
  border: 1px solid #ddd;
}

.status-error {
  /* background-color: #fff2f0; */
  color: #ff4d4f;
  border: 1px solid #ffccc7;
}

.zeromq-info {
  /* background-color: #f9f9f9; */
  padding: 15px;
  border-radius: 4px;
  margin: 15px 0;
  width: 100%;
}

.zeromq-info h4 {
  margin-top: 0;
  margin-bottom: 10px;
  /* color: #333; */
}

.info-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 15px;
}

.info-table td {
  padding: 8px 4px;
  border-bottom: 1px solid #eee;
}

.info-table tr:last-child td {
  border-bottom: none;
}

.info-label {
  width: 180px;
  vertical-align: top;
  text-align: right;
  padding-right: 10px;
  font-size: 14px;
}

.info-value {
  text-align: left;
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

.msg-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 10px;
}

.msg-table td {
  padding: 4px 0;
  border-bottom: 1px solid #eee;
}

.msg-table tr:last-child td {
  border-bottom: none;
}

.msg-key {
  font-weight: 500;
  width: 150px;
  padding-right: 10px;
  text-align: left;
}

.msg-value {
  text-align: left;
  font-size: 13px;
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