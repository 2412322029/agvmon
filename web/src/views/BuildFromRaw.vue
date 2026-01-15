<script setup>
import { NButton, NCard, NCheckbox, NResult, useMessage } from 'naive-ui'
import { ref } from 'vue'

const loading = ref(false)
const result = ref(null)
const useFakeData = ref(false)
const message = useMessage()

const buildFromRaw = async () => {
  loading.value = true
  result.value = null
  
  try {
    const url = `/api/rcms/build_from_raw?fake=${useFakeData.value}`
    const response = await fetch(url)
    const data = await response.json()
    
    if (data.message === 'RCMS raw data built successfully') {
      result.value = { success: true, message: data.message }
      message.success('Raw data built successfully')
    } else {
      result.value = { success: false, message: data.message, errors: data.errors }
      message.error('Failed to build raw data')
    }
  } catch (error) {
    result.value = { success: false, message: 'Network error', errors: [error.message] }
    message.error('Network error')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="main-container">
    <NCard title="Build from Raw" :bordered="false" style="max-width: 800px; margin: 0 auto;">
      <div class="content">
        <p>Click the button below to build RCMS data from raw source.</p>
        
        <div class="options">
          <NCheckbox v-model:checked="useFakeData">Use fake data</NCheckbox>
        </div>
        
        <NButton 
          type="primary" 
          @click="buildFromRaw" 
          :loading="loading"
          size="large"
        >
          Build from Raw
        </NButton>
        
        <div v-if="result" class="result-container">
          <NResult
            :status="result.success ? 'success' : 'error'"
            :title="result.success ? 'Success' : 'Error'"
            :description="result.message"
          >
            <template v-if="!result.success && result.errors" #extra>
              <div class="errors">
                <h4>Errors:</h4>
                <ul>
                  <li v-for="(error, index) in result.errors" :key="index">
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
</template>

<style scoped>
.main-container {
  min-height: 100vh;
  background-color: #f5f5f7;
  padding: 20px;
}

.content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  padding: 20px;
}

.options {
  align-self: flex-start;
  margin-bottom: 10px;
}

.result-container {
  margin-top: 20px;
  width: 100%;
}

.errors {
  text-align: left;
  margin-top: 10px;
}

.errors h4 {
  margin: 0 0 10px 0;
  font-size: 16px;
}

.errors ul {
  margin: 0;
  padding-left: 20px;
}

.errors li {
  margin-bottom: 5px;
  color: #ff4d4f;
}
</style>