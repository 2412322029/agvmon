<template>
  <n-popover trigger="click" :width="400">
    <template #trigger>
      <n-button text>
        <n-icon size="24">
          <attach-outline />
        </n-icon>
      </n-button>
    </template>
    
    <div class="file-selector">
      <h3 style="margin-top: 0;">选择文件</h3>
      
      <n-tabs type="line" animated>
        <n-tab-pane name="upload" tab="上传新文件">
          <n-upload
            multiple
            :max="5"
            :custom-request="handleUpload"
            :show-file-list="false"
            :headers="{ 'Content-Type': 'multipart/form-data' }"
          >
            <n-button type="primary" ghost size="small" block>
              选择文件上传
            </n-button>
          </n-upload>
          
          <!-- 过期时间选择 -->
          <n-form :model="uploadForm" label-placement="left" label-width="auto" size="tiny" style="margin-top: 10px;">
            <n-form-item label="过期天数">
              <n-input-number
                v-model:value="uploadForm.expireDays"
                :min="1"
                :max="365"
                size="tiny"
                :show-button="false"
                placeholder="天数"
                style="width: 100px;"
              />
            </n-form-item>
          </n-form>
        </n-tab-pane>
        
        <n-tab-pane name="existing" tab="选择已有文件">
          <n-spin :show="listLoading">
            <div v-if="fileList.length > 0" class="file-grid-small">
              <div 
                v-for="file in fileList" 
                :key="file.stored_filename"
                class="file-item-small"
                @click="selectFileToSend(file)"
              >
                <div class="file-icon-small">
                  <n-icon size="24" v-if="isImageFile(file.content_type)">
                    <image-outline />
                  </n-icon>
                  <n-icon size="24" v-else-if="isDocumentFile(file.content_type)">
                    <document-text-outline />
                  </n-icon>
                  <n-icon size="24" v-else-if="isVideoFile(file.content_type)">
                    <videocam-outline />
                  </n-icon>
                  <n-icon size="24" v-else-if="isAudioFile(file.content_type)">
                    <musical-notes-outline />
                  </n-icon>
                  <n-icon size="24" v-else>
                    <document-outline />
                  </n-icon>
                </div>
                <div class="file-info-small">
                  <div class="file-name-small">{{ truncateFileName(file.original_filename, 15) }}</div>
                  <div class="file-size-small">{{ formatFileSize(file.size) }}</div>
                </div>
              </div>
            </div>
            
            <n-empty v-if="fileList.length === 0 && !listLoading" description="暂无文件" />
          </n-spin>
        </n-tab-pane>
      </n-tabs>
    </div>
  </n-popover>
</template>

<script setup>
import {
    AttachOutline,
    DocumentOutline,
    DocumentTextOutline,
    ImageOutline,
    MusicalNotesOutline,
    VideocamOutline
} from '@vicons/ionicons5'
import {
    NButton,
    NEmpty,
    NForm,
    NFormItem,
    NIcon,
    NInputNumber,
    NPopover,
    NSpin,
    NTabPane,
    NTabs,
    NUpload,
    useMessage
} from 'naive-ui'
import { onMounted, ref } from 'vue'

const emit = defineEmits(['file-selected', 'file-uploaded'])

// 响应式数据
const message = useMessage()
const uploadLoading = ref(false)
const listLoading = ref(false)
const uploadProgress = ref(0)
const fileList = ref([])

// 上传表单
const uploadForm = ref({
  expireDays: 7
})

// 自定义上传请求
const handleUpload = async (options) => {
  const { file, onFinish, onError, onProgress } = options
  
  uploadLoading.value = true
  uploadProgress.value = 0
  
  try {
    const formData = new FormData()
    formData.append('file', file.file)
    formData.append('expire_days', uploadForm.value.expireDays)
    
    const xhr = new XMLHttpRequest()
    
    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText)
          if (response.message && response.message.includes('成功')) {
            message.success(`文件 ${file.name} 上传成功！`)
            loadFileList() // 重新加载文件列表
            emit('file-uploaded', response) // 发送上传成功的事件
            onFinish()
          } else {
            message.error(response.error || '上传失败')
            onError()
          }
        } catch (e) {
          message.error('响应解析失败')
          onError()
        }
      } else {
        message.error(`上传失败: ${xhr.statusText}`)
        onError()
      }
    })
    
    xhr.addEventListener('error', () => {
      message.error('网络错误')
      onError()
    })
    
    xhr.open('POST', '/api/util/upload')
    xhr.send(formData)
  } catch (error) {
    message.error(error.message)
    onError()
  } finally {
    uploadLoading.value = false
    uploadProgress.value = 0
  }
}

// 加载文件列表
const loadFileList = async () => {
  listLoading.value = true
  try {
    const response = await fetch('/api/util/list')
    const data = await response.json()
    
    if (response.ok) {
      fileList.value = data.files || []
    } else {
      message.error(data.error || '获取文件列表失败')
    }
  } catch (error) {
    message.error('网络错误: ' + error.message)
  } finally {
    listLoading.value = false
  }
}

// 选择文件发送
const selectFileToSend = (file) => {
  emit('file-selected', file)
}

// 检查是否为图片文件
const isImageFile = (contentType) => {
  return contentType && contentType.startsWith('image/')
}

// 检查是否为文档文件
const isDocumentFile = (contentType) => {
  return contentType && (
    contentType.startsWith('application/pdf') ||
    contentType.startsWith('application/msword') ||
    contentType.startsWith('application/vnd.') ||
    contentType.includes('text/')
  )
}

// 检查是否为视频文件
const isVideoFile = (contentType) => {
  return contentType && contentType.startsWith('video/')
}

// 检查是否为音频文件
const isAudioFile = (contentType) => {
  return contentType && contentType.startsWith('audio/')
}

// 截断文件名
const truncateFileName = (fileName, maxLength) => {
  if (!fileName) return ''
  return fileName.length > maxLength ? fileName.substring(0, maxLength) + '...' : fileName
}

// 格式化文件大小
const formatFileSize = (bytes) => {
  if (!bytes) return '未知'
  
  if (bytes < 1024) {
    return bytes + ' B'
  } else if (bytes < 1024 * 1024) {
    return (bytes / 1024).toFixed(1) + ' KB'
  } else if (bytes < 1024 * 1024 * 1024) {
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  } else {
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB'
  }
}

// 页面加载时获取文件列表
onMounted(() => {
  loadFileList()
})
</script>

<style scoped>
.file-selector {
  padding: 10px;
}

.file-grid-small {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
  padding: 5px 0;
}

.file-item-small {
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  padding: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  background-color: #fafafa;
  display: flex;
  align-items: center;
}

.file-item-small:hover {
  background-color: #e8f4ff;
  border-color: #2080f0;
}

.file-icon-small {
  margin-right: 6px;
}

.file-info-small {
  flex: 1;
  min-width: 0;
}

.file-name-small {
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
  color: #333;
}

.file-size-small {
  font-size: 10px;
  color: #666;
}
</style>