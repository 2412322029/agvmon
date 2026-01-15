<script setup>
import { NButton, NCard, NResult, useMessage } from 'naive-ui'
import { ref } from 'vue'

const loading = ref(false)
const result = ref(null)
const message = useMessage()

const buildFromCache = async () => {
  loading.value = true
  result.value = null
  
  try {
    const response = await fetch('/api/rcms/build_from_cache')
    const data = await response.json()
    
    if (data.message === 'RCMS cache built successfully') {
      result.value = { success: true, message: data.message }
      message.success('Cache built successfully')
    } else {
      result.value = { success: false, message: data.message, errors: data.errors }
      message.error('Failed to build cache')
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
    <NCard title="Build from Cache" :bordered="false" style="max-width: 800px; margin: 0 auto;">
      <div class="content">
        <p>Click the button below to build RCMS data from cache.</p>
        
        <NButton 
          type="primary" 
          @click="buildFromCache" 
          :loading="loading"
          size="large"
        >
          Build from Cache
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