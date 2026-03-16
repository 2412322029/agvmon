<template>
  <n-card title="DM码图片处理" :bordered="false" size="small" segmented>
    <n-tabs type="line" animated>
      <n-tab-pane name="decode" tab="图片识别">
        <input type="file" ref="fileInput" style="display: none" :accept="acceptTypes" @change="handleFileChange" />

        <n-button type="primary" @click="triggerFileInput" :loading="uploading">
          <n-icon style="margin-right: 8px;">
            <upload-outlined />
          </n-icon>
          选择图片上传
        </n-button>

        <div v-if="uploadedImageUrl" style="margin-top: 20px;">
          <div style="position: relative; display: inline-block;">
            <img :src="uploadedImageUrl" alt="上传图片"
              style="max-width: 100%; max-height: 600px; border-radius: 8px; border: 1px solid #e0e0e0;" ref="imageRef"
              @load="handleImageLoad" />
            <canvas ref="canvasRef" style="position: absolute; top: 0; left: 0; pointer-events: none;"></canvas>
          </div>
        </div>

        <div v-if="decodeResult" style="margin-top: 20px;">
          <n-alert type="success" title="识别成功" :show-icon="true">
            <p>共识别到 {{ decodeResult.length }} 个DM码</p>
          </n-alert>

          <div v-for="(result, index) in decodeResult" :key="index"
            style="margin-top: 15px; padding: 15px;border-radius: 8px; border: 1px solid #e0e0e0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
              <h4 style="margin: 0; color: #18a058;">DM码 {{ index + 1 }}</h4>
              <n-tag type="success" size="medium">
                {{ result.data }}
              </n-tag>
              <n-button type="primary" size="small" @click="copyToClipboard(result.data)">
                复制DM
              </n-button>
            </div>
          </div>
        </div>

        <div v-if="error" style="margin-top: 20px;">
          <n-alert type="error" :title="error" :show-icon="true" />
        </div>
      </n-tab-pane>

      <n-tab-pane name="encode" tab="生成DM码">
        <n-space vertical :size="16">
          <n-form-item label="要编码的内容" required>
            <n-input v-model:value="encodeData" type="textarea" placeholder="请输入要编码的内容" :rows="3" />
          </n-form-item>

          <n-space>
            <n-form-item label="尺寸">
              <n-select v-model:value="encodeSize" :options="sizeOptions" style="width: 150px" />
            </n-form-item>
            <n-form-item label="类型">
              <n-select v-model:value="encodeType" :options="typeOptions" style="width: 120px" />
            </n-form-item> 
            <n-form-item label="缩放" v-if="encodeType === 'png'">
              <n-select v-model:value="encodeScale" :options="scaleOptions" style="width: 100px" />
            </n-form-item>
          </n-space>

          <n-button type="primary" @click="handleEncode" :loading="encoding" :disabled="!encodeData">
            <n-icon style="margin-right: 8px;">
              <upload-outlined />
            </n-icon>
            生成DM码
          </n-button>

          <div v-if="encodedImageUrl" style="margin-top: 20px;">
            <n-alert type="success" title="生成成功" :show-icon="true" />

            <div style="margin-top: 15px; text-align: center;">
              <img :src="encodedImageUrl" alt="生成的DM码"
                style="max-width: 100%; border-radius: 8px; border: 1px solid #e0e0e0;" />
            </div>

            <div style="margin-top: 15px;">
              <n-button type="primary" @click="downloadEncodedImage">
                <n-icon style="margin-right: 8px;">
                  <upload-outlined />
                </n-icon>
                下载DM码图片
              </n-button>
            </div>
          </div>

          <div v-if="encodeError" style="margin-top: 20px;">
            <n-alert type="error" :title="encodeError" :show-icon="true" />
          </div>
        </n-space>
      </n-tab-pane>
    </n-tabs>
  </n-card>
</template>

<script setup>
import { UploadOutlined } from '@vicons/antd'
import { NAlert, NButton, NCard, NFormItem, NIcon, NInput, NSelect, NSpace, NTabPane, NTabs, NTag, useMessage } from 'naive-ui'
import { onMounted, ref } from 'vue'

const message = useMessage()

const uploadUrl = '/api/agv/decode_dmdtx_file'
const encodeUrl = '/api/agv/encode_dmdtx_file'
const sizeUrl = '/api/agv/get_dmdtx_all_size'
const acceptTypes = 'image/*'

const fileInput = ref(null)
const uploading = ref(false)
const decodeResult = ref(null)
const error = ref('')
const uploadedImageUrl = ref('')
const imageRef = ref(null)
const canvasRef = ref(null)
const imageLoaded = ref(false)

const encodeData = ref('')
const encodeSize = ref('14x14')
const encodeScale = ref(3)
const encodeType = ref('png')
const encoding = ref(false)
const encodedImageUrl = ref('')
const encodeError = ref('')
const availableSizes = ref([])

const sizeOptions = ref([
  { label: '14x14', value: '14x14' },
  { label: '18x18', value: '18x18' },
  { label: '22x22', value: '22x22' },
  { label: '26x26', value: '26x26' },
  { label: '32x32', value: '32x32' }
])
const scaleOptions = ref([
  { label: '1', value: 1 },
  { label: '2', value: 2 },
  { label: '3', value: 3 },
  { label: '4', value: 4 },
  { label: '5', value: 5 }
])
const typeOptions = ref([
  { label: 'PNG', value: 'png' },
  { label: 'SVG', value: 'svg' }
])

const triggerFileInput = () => {
  fileInput.value?.click()
}

const handleFileChange = async (event) => {
  const file = event.target.files[0]
  if (!file) return

  const reader = new FileReader()
  reader.onload = (e) => {
    uploadedImageUrl.value = e.target.result
  }
  reader.readAsDataURL(file)

  uploading.value = true

  try {
    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch(uploadUrl, {
      method: 'POST',
      body: formData
    })

    const responseText = await response.text()
    const data = JSON.parse(responseText)

    if (Array.isArray(data)) {
      decodeResult.value = data
      error.value = ''
      message.success(`识别完成，共找到 ${data.length} 个DM码`)

      setTimeout(() => {
        drawRectangles()
      }, 300)
    } else if (data && data.error) {
      decodeResult.value = null
      error.value = data.error
      message.warning(data.error)
    } else {
      decodeResult.value = null
      error.value = '未知的响应格式'
      message.error('未知的响应格式')
    }
  } catch (e) {
    console.error('解析响应失败:', e)
    error.value = '解析识别结果失败: ' + e.message
    message.error('解析识别结果失败')
  } finally {
    uploading.value = false
    fileInput.value.value = ''
  }
}

const handleImageLoad = () => {
  imageLoaded.value = true
  if (decodeResult.value && decodeResult.value.length > 0) {
    drawRectangles()
  }
}

const drawRectangles = () => {
  const image = imageRef.value
  const canvas = canvasRef.value
  const ctx = canvas.getContext('2d')

  if (!image || !canvas || !decodeResult.value) return

  canvas.width = image.width
  canvas.height = image.height

  decodeResult.value.forEach((result, index) => {
    const { left, top, width, height } = result.rect

    const offsetTop = top + height

    ctx.strokeStyle = '#ff4d4f'
    ctx.lineWidth = 3
    ctx.strokeRect(left, offsetTop, width, height)

    ctx.fillStyle = 'rgba(255, 77, 79, 0.3)'
    ctx.fillRect(left, offsetTop, width, height)

    ctx.fillStyle = '#ff4d4f'
    ctx.font = 'bold 14px Arial'
    ctx.fillText(`DM-${index + 1}`, left + 5, offsetTop + 20)
  })
}

const copyToClipboard = (text) => {
  navigator.clipboard.writeText(text)
    .then(() => {
      message.success('已复制到剪贴板')
    })
    .catch(() => {
      message.error('复制失败')
    })
}

const clearCanvas = () => {
  const canvas = canvasRef.value
  if (canvas) {
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)
  }
}

const handleEncode = async () => {
  if (!encodeData.value) {
    message.warning('请输入要编码的内容')
    return
  }

  encoding.value = true
  encodeError.value = ''
  encodedImageUrl.value = ''

  try {
    const params = new URLSearchParams({
      data: encodeData.value,
      size: encodeSize.value,
      scale: encodeScale.value,
      types: encodeType.value
    })

    const response = await fetch(`${encodeUrl}?${params}`, {
      method: 'GET'
    })

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`)
    }

    const contentType = response.headers.get('content-type')

    if (contentType && contentType.includes('application/json')) {
      const data = await response.json()
      if (data.error) {
        encodeError.value = data.error
        message.error(data.error)
      } else {
        encodeError.value = '未知的响应格式'
        message.error('未知的响应格式')
      }
    } else {
      if (encodeType.value === 'svg') {
        const svgText = await response.text()
        encodedImageUrl.value = `data:image/svg+xml;base64,${btoa(decodeURIComponent(encodeURIComponent(svgText)))}`
      } else {
        const blob = await response.blob()
        encodedImageUrl.value = URL.createObjectURL(blob)
      }
      message.success('DM码生成成功')
    }
  } catch (e) {
    console.error('编码失败:', e)
    encodeError.value = '编码失败: ' + e.message
    message.error('编码失败')
  } finally {
    encoding.value = false
  }
}

const downloadEncodedImage = () => {
  if (!encodedImageUrl.value) return

  const link = document.createElement('a')
  link.href = encodedImageUrl.value
  link.download = `dmcode_${encodeType.value}`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  message.success('开始下载')
}

const fetchSizes = async () => {
  try {
    const response = await fetch(sizeUrl)
    const data = await response.json()
    if (Array.isArray(data)) {
      availableSizes.value = data
      sizeOptions.value = data.map(s => ({ label: s, value: s }))
    }
  } catch (e) {
    console.error('获取尺寸列表失败:', e)
  }
}

onMounted(() => {
  fetchSizes()
})
</script>

<style scoped>
.image-decode-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.upload-area {
  margin-bottom: 20px;
}

.result-container {
  margin-top: 20px;
}

.result-item {
  padding: 15px;
  background: #f5f5f5;
  border-radius: 8px;
  margin-bottom: 15px;
}

.result-data {
  font-size: 16px;
  font-weight: bold;
  color: #18a058;
  word-break: break-all;
}

.result-rect {
  margin-top: 10px;
  font-family: monospace;
  padding: 10px;
  border-radius: 4px;
  font-size: 12px;
}

/* Mobile responsiveness */
@media (max-width: 768px) {
  .image-decode-container {
    padding: 10px;
  }
}

@media (max-width: 480px) {
  .result-item {
    padding: 10px;
  }

  .result-data {
    font-size: 14px;
  }
}
</style>
