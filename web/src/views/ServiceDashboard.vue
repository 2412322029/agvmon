<script setup>
import { NButton, NCard, NCheckbox, NMessageProvider, NResult, useMessage } from 'naive-ui'
import { ref } from 'vue'

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
}
</style>