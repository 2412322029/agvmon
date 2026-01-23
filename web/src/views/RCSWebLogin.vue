<script setup>
import { NButton, NCard, NForm, NFormItem, NInput, NResult, useMessage } from 'naive-ui'
import { ref } from 'vue'

const message = useMessage()

// 表单数据
const formData = ref({
  username: '',
  password: ''
})

// 加载状态
const loading = ref(false)
const manualLoginLoading = ref(false)
const configLoginLoading = ref(false)

// 结果显示
const loginResult = ref(null)

// 验证规则
const rules = {
  username: {
    required: true,
    message: '请输入用户名',
    trigger: 'blur'
  },
  password: {
    required: true,
    message: '请输入密码',
    trigger: 'blur'
  }
}

// 手动登录（使用输入的用户名密码）
const manualLogin = async () => {
  if (!formData.value.username || !formData.value.password) {
    message.warning('请输入用户名和密码')
    return
  }
  
  manualLoginLoading.value = true
  configLoginLoading.value = false
  loginResult.value = null
  
  try {
    const response = await fetch('/api/rcs_web/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        username: formData.value.username,
        password: formData.value.password,
        pwd_safe_level: '3'
      })
    })
    const data = await response.json()
    
    loginResult.value = data
    
    if (data.success) {
      message.success('登录成功')
    } else {
      message.error('登录失败')
    }
  } catch (error) {
    loginResult.value = { success: false, message: '网络错误', error: error.message }
    message.error('网络错误')
  } finally {
    manualLoginLoading.value = false
  }
}

// 使用配置文件中的凭据登录（无需用户输入）
const loginWithConfigCredentials = async () => {
  configLoginLoading.value = true
  manualLoginLoading.value = false
  loginResult.value = null
  
  try {
    // 直接调用后端的login2接口，该接口会使用配置文件中的凭据
    const response = await fetch('/api/rcs_web/login2', {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    })
    const data = await response.json()
    
    loginResult.value = data
    
    if (data.success) {
      message.success('使用配置文件凭据登录成功')
    } else {
      message.error('登录失败')
    }
  } catch (error) {
    loginResult.value = { success: false, message: '网络错误', error: error.message }
    message.error('网络错误')
  } finally {
    configLoginLoading.value = false
  }
}
</script>

<template>
  <div class="main-container">
    <h1 class="page-title">RCS Web Login</h1>
    
    <div class="login-options">
      <!-- 方式一：使用配置文件凭据登录 -->
      <NCard title="方式一：使用配置文件凭据登录" :bordered="true" class="login-card">
        <div class="login-content">
          <p>直接使用系统配置文件中的用户名密码进行登录，无需手动输入。</p>
          
          <div class="login-actions">
            <NButton 
              type="primary" 
              @click="loginWithConfigCredentials" 
              :loading="configLoginLoading"
              size="large"
            >
              使用配置文件凭据登录
            </NButton>
          </div>
        </div>
      </NCard>
      
      <!-- 方式二：手动输入凭据登录 -->
      <NCard title="方式二：手动输入凭据登录" :bordered="true" class="login-card">
        <div class="login-content">
          <p>手动输入用户名和密码进行登录。</p>
          
          <NForm :model="formData" :rules="rules" label-placement="top">
            <NFormItem label="用户名" path="username">
              <NInput 
                v-model:value="formData.username" 
                placeholder="请输入用户名"
                :input-props="{ autocomplete: 'username' }"
              />
            </NFormItem>
            
            <NFormItem label="密码" path="password">
              <NInput 
                v-model:value="formData.password" 
                type="password"
                placeholder="请输入密码"
                :input-props="{ autocomplete: 'current-password' }"
              />
            </NFormItem>
          </NForm>
          
          <div class="login-actions">
            <NButton 
              type="success" 
              @click="manualLogin" 
              :loading="manualLoginLoading"
              size="large"
            >
              手动登录
            </NButton>
          </div>
        </div>
      </NCard>
    </div>
    
    <!-- 登录结果卡片 -->
    <NCard title="登录结果" :bordered="true" class="result-card">
      <div class="result-content">
        <p>最近一次登录操作的结果。</p>
        
        <div v-if="loginResult" class="result-container">
          <NResult
            :status="loginResult.success ? 'success' : 'error'"
            :title="loginResult.success ? '登录成功' : '登录失败'"
            :description="loginResult.message || loginResult.msg || JSON.stringify(loginResult)"
          >
            <template v-if="!loginResult.success && (loginResult.errors || loginResult.error)" #extra>
              <div class="errors">
                <h4>错误信息：</h4>
                <ul>
                  <li v-for="(error, index) in (loginResult.errors || [loginResult.error])" :key="index">
                    {{ error }}
                  </li>
                </ul>
              </div>
            </template>
          </NResult>
        </div>
        
        <div v-else class="no-result">
          <p>暂无登录结果，请执行登录操作。</p>
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

.login-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
  gap: 20px;
  max-width: 1200px;
  margin: 0 auto 20px;
}

.login-card {
  max-width: 100%;
}

.login-content {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 15px;
  padding: 15px;
}

.login-actions {
  display: flex;
  justify-content: center;
  margin-top: 10px;
}

.result-card {
  max-width: 1200px;
  margin: 0 auto;
}

.result-content {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 15px;
  padding: 15px;
}

.result-container {
  margin-top: 15px;
  width: 100%;
}

.no-result {
  text-align: center;
  padding: 20px;
  color: #999;
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

/* 响应式调整 */
@media (max-width: 768px) {
  .login-options {
    grid-template-columns: 1fr;
    gap: 15px;
  }
  
  .login-card {
    margin-bottom: 15px;
  }
  
  .main-container {
    padding: 15px;
  }
  
  .page-title {
    font-size: 20px;
    margin-bottom: 20px;
  }
  
  .login-actions {
    flex-direction: column;
    align-items: center;
  }
  
  .login-actions .n-button {
    width: 100%;
    max-width: 300px;
    margin-bottom: 10px;
  }
}
</style>
