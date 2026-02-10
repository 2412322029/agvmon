<template>
  <n-card :title="title" class="file-management-container">
    <!-- 文件上传区域 -->
    <n-space horizontal :size="16">
      <n-upload v-if="showUpload" multiple :max="5" :custom-request="handleUpload" :show-file-list="false"
        :headers="{ 'Content-Type': 'multipart/form-data' }">
        <n-button type="primary" :loading="uploadLoading">
          {{ uploadButtonText }}
        </n-button>
      </n-upload>

      <!-- 添加文件选择器组件作为备选方式 -->
      <FileSelectorComponent v-if="showUpload" @file-selected="selectFileFromSelector"
        @file-uploaded="onFileUploadedFromSelector" />

      <!-- 过期时间选择 -->
      <n-form v-if="showUpload" :model="uploadForm" label-placement="left" label-width="auto">
        <n-form-item label="过期时间（天）">
          <n-input-number v-model:value="uploadForm.expireDays" :min="1" :max="365" placeholder="请输入过期天数"
            style="width: 200px;" />
          <n-button @click="setDefaultExpireDays" style="margin-left: 10px;">默认 (7天)</n-button>
        </n-form-item>
      </n-form>
    </n-space>

    <!-- 上传进度条 -->
    <n-progress v-if="uploadProgress > 0 && uploadProgress < 100" type="line" :percentage="uploadProgress"
      :show-indicator="true" indicator-placement="inside" style="margin-top: 10px;" />

    <!-- 文件网格 -->
    <n-divider v-if="showFiles" />
    <h3 v-if="showFiles">已上传文件</h3>

    <n-spin :show="listLoading">
      <div v-if="fileList.length > 0 && showFiles" class="file-grid">
        <div v-for="file in fileList" :key="file.stored_filename" class="file-item" @click="selectFile(file)">
          <div class="file-icon">
            <n-icon size="48" v-if="isImageFile(file.content_type)">
              <image-outline />
            </n-icon>
            <n-icon size="48" v-else-if="isDocumentFile(file.content_type)">
              <document-text-outline />
            </n-icon>
            <n-icon size="48" v-else-if="isVideoFile(file.content_type)">
              <videocam-outline />
            </n-icon>
            <n-icon size="48" v-else-if="isAudioFile(file.content_type)">
              <musical-notes-outline />
            </n-icon>
            <n-icon size="48" v-else>
              <document-outline />
            </n-icon>
          </div>
          <div class="file-info">
            <div class="file-name">{{ truncateFileName(file.original_filename, 20) }}</div>
            <div class="file-size">{{ formatFileSize(file.size) }}</div>
            <div class="file-date">{{ formatDateShort(file.upload_time) }}</div>
          </div>
          <div class="file-expire">
            <span>{{ file.expire_days }} 天</span>
          </div>
        </div>
      </div>

      <n-empty v-if="fileList.length === 0 && !listLoading && showFiles" description="暂无文件" />
    </n-spin>

    <!-- 文件详情模态框 -->
    <n-modal v-model:show="showFileDetail" :mask-closable="true" preset="card" title="文件详情"
      style="width: 600px; max-width: 90vw;" :closable="true" :on-close="closeFileDetailModal">
      <div v-if="selectedFile" class="file-detail-content">
        <!-- 文件预览 -->
        <div v-if="isImageFile(selectedFile.content_type)" class="file-preview">
          <img :src="`/api/util/download/${selectedFile.stored_filename}`" :alt="selectedFile.original_filename"
            class="preview-image" />
        </div>

        <!-- 视频预览 -->
        <div v-else-if="isVideoFile(selectedFile.content_type)" class="file-preview">
          <video :src="`/api/util/download/${selectedFile.stored_filename}`" controls class="preview-video">
            您的浏览器不支持视频播放
          </video>
        </div>

        <!-- 文件信息表格 -->
        <n-table :bordered="false" :single-line="false" size="small">
          <tbody>
            <tr>
              <td><strong>原始文件名</strong></td>
              <td>{{ selectedFile.original_filename }}</td>
            </tr>
            <tr>
              <td><strong>存储文件名</strong></td>
              <td>{{ selectedFile.stored_filename }}</td>
            </tr>
            <tr>
              <td><strong>文件大小</strong></td>
              <td>{{ formatFileSize(selectedFile.size) }}</td>
            </tr>
            <tr>
              <td><strong>内容类型</strong></td>
              <td>{{ selectedFile.content_type || '未知' }}</td>
            </tr>
            <tr>
              <td><strong>上传时间</strong></td>
              <td>{{ formatDate(selectedFile.upload_time) }}</td>
            </tr>
            <tr>
              <td><strong>过期时间</strong></td>
              <td>
                <n-flex :wrap="false" justify="space-between" style="width: 100%;">
                  <span>{{ selectedFile.expire_days }} 天</span>
                  <n-space>
                    <n-button size="tiny" @click="openEditExpireDialog(selectedFile)" :disabled="editExpireLoading">
                      修改
                    </n-button>
                  </n-space>
                </n-flex>
              </td>
            </tr>
          </tbody>
        </n-table>

        <!-- 操作按钮 -->
        <n-space justify="space-between" style="margin-top: 20px; width: 100%;">
          <n-button type="primary" size="small"
            @click="downloadFile(selectedFile.stored_filename, selectedFile.original_filename)">
            下载
          </n-button>
          <n-button type="error" size="small" @click="confirmDeleteFile(selectedFile.stored_filename)"
            :disabled="deleteLoading">
            删除
          </n-button>
        </n-space>
      </div>
    </n-modal>

    <!-- 编辑过期时间对话框 -->
    <n-modal v-model:show="showEditExpireDialog" :mask-closable="false">
      <n-card style="width: 500px" title="修改过期时间" :bordered="false" size="huge" role="dialog" aria-modal="true">
        <n-form label-placement="left" label-width="auto">
          <n-form-item label="文件名">
            <n-input :value="editFile?.original_filename" readonly />
          </n-form-item>
          <n-form-item label="当前过期时间">
            <n-input :value="`${editFile?.expire_days} 天`" readonly />
          </n-form-item>
          <n-form-item label="新过期时间（天）">
            <n-input-number v-model:value="newExpireDays" :min="1" :max="365" placeholder="请输入过期天数"
              style="width: 100%;" />
          </n-form-item>
        </n-form>
        <template #footer>
          <n-space justify="end">
            <n-button @click="showEditExpireDialog = false">取消</n-button>
            <n-button type="primary" :loading="editExpireLoading" @click="updateExpireTime">确认修改</n-button>
          </n-space>
        </template>
      </n-card>
    </n-modal>

    <!-- 删除确认对话框 -->
    <n-modal v-model:show="showDeleteConfirm" :mask-closable="false">
      <n-card style="width: 500px" title="确认删除" :bordered="false" size="huge" role="dialog" aria-modal="true">
        <p>确定要删除文件 "{{ deleteFileName }}" 吗？此操作不可撤销。</p>
        <template #footer>
          <n-space justify="end">
            <n-button @click="showDeleteConfirm = false">取消</n-button>
            <n-button type="error" :loading="deleteLoading" @click="deleteFile">确认删除</n-button>
          </n-space>
        </template>
      </n-card>
    </n-modal>
  </n-card>
</template>

<script setup>
import {
  DocumentOutline,
  DocumentTextOutline,
  ImageOutline,
  MusicalNotesOutline,
  VideocamOutline
} from '@vicons/ionicons5'
import {
  NButton,
  NCard,
  NDivider,
  NEmpty,
  NFlex,
  NForm,
  NFormItem,
  NIcon,
  NInputNumber,
  NModal,
  NProgress,
  NSpace,
  NSpin,
  NTable,
  NUpload,
  NInput,
  useMessage
} from 'naive-ui'
import { onMounted, onUnmounted, ref } from 'vue'
import FileSelectorComponent from './FileSelectorComponent.vue'

const props = defineProps({
  title: {
    type: String,
    default: '文件上传管理'
  },
  showUpload: {
    type: Boolean,
    default: true
  },
  showFiles: {
    type: Boolean,
    default: true
  },
  uploadButtonText: {
    type: String,
    default: '选择文件上传'
  },
  defaultExpireDays: {
    type: Number,
    default: 7
  }
})

const emit = defineEmits(['file-selected', 'file-uploaded', 'file-deleted'])

// 响应式数据
const message = useMessage()
const uploadLoading = ref(false)
const listLoading = ref(false)
const deleteLoading = ref(false)
const editExpireLoading = ref(false)
const uploadProgress = ref(0)
const fileList = ref([])
const showDeleteConfirm = ref(false)
const showEditExpireDialog = ref(false)
const showFileDetail = ref(false)
const deleteFileName = ref('')
const deleteFileStoredName = ref('')
const editFile = ref(null)
const newExpireDays = ref(7)
const selectedFile = ref(null)
const isMobile = ref(window.innerWidth < 768)

// 上传表单
const uploadForm = ref({
  expireDays: 7
})

// 设置默认过期天数
uploadForm.value.expireDays = props.defaultExpireDays

// Additional methods for handling events from FileSelectorComponent
const selectFileFromSelector = (file) => {
  selectedFile.value = file
  showFileDetail.value = true
  emit('file-selected', file) // Also emit to parent components
}

const onFileUploadedFromSelector = (response) => {
  loadFileList() // Refresh the file list
  emit('file-uploaded', response) // Emit to parent components
}

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

    // 监听上传进度
    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) {
        const percentComplete = Math.round((event.loaded / event.total) * 100)
        uploadProgress.value = percentComplete
        onProgress({ percent: percentComplete })
      }
    })

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

// 设置默认过期时间
const setDefaultExpireDays = () => {
  uploadForm.value.expireDays = props.defaultExpireDays
}

// 删除文件确认
const confirmDeleteFile = (storedFilename) => {
  deleteFileStoredName.value = storedFilename
  // Find the original filename for display
  const file = fileList.value.find(f => f.stored_filename === storedFilename)
  deleteFileName.value = file ? file.original_filename : storedFilename
  showDeleteConfirm.value = true
}

// 删除文件
const deleteFile = async () => {
  deleteLoading.value = true
  try {
    const response = await fetch('/api/util/delete', {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        stored_filename: deleteFileStoredName.value
      })
    })

    const data = await response.json()

    if (response.ok) {
      message.success('文件删除成功')
      showDeleteConfirm.value = false
      loadFileList() // 重新加载文件列表
      emit('file-deleted', deleteFileStoredName.value) // 发送删除成功的事件
    } else {
      message.error(data.error || '删除失败')
    }
  } catch (error) {
    message.error('网络错误: ' + error.message)
  } finally {
    deleteLoading.value = false
  }
}

// 下载文件
const downloadFile = async (storedFilename, originalFilename) => {
  try {
    // 构建下载链接
    const downloadUrl = `/api/util/download/${storedFilename}`

    // 创建一个隐藏的链接元素来触发下载
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = originalFilename
    link.target = '_blank'  // 在新标签页打开，允许浏览器处理下载
    link.style.display = 'none'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } catch (error) {
    message.error('下载失败: ' + error.message)
  }
}

// 选择文件以显示详细信息
const selectFile = (file) => {
  selectedFile.value = file
  showFileDetail.value = true
  emit('file-selected', file) // 发送文件选中的事件
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

// 格式化短日期
const formatDateShort = (dateString) => {
  if (!dateString) return '未知'
  const date = new Date(dateString)
  return date.toLocaleDateString('zh-CN')
}

// 格式化文件大小
const formatFileSize = (bytes) => {
  if (!bytes) return '未知'

  if (bytes < 1024) {
    return bytes + ' B'
  } else if (bytes < 1024 * 1024) {
    return (bytes / 1024).toFixed(2) + ' KB'
  } else if (bytes < 1024 * 1024 * 1024) {
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB'
  } else {
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
  }
}

// 格式化日期
const formatDate = (dateString) => {
  if (!dateString) return '未知'
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN')
}

// 关闭文件详情模态框
const closeFileDetailModal = () => {
  showFileDetail.value = false
}

// 打开编辑过期时间对话框
const openEditExpireDialog = (file) => {
  editFile.value = file
  newExpireDays.value = file.expire_days
  showEditExpireDialog.value = true
}

// 修改文件过期时间
const updateExpireTime = async () => {
  if (!editFile.value) return

  editExpireLoading.value = true
  try {
    const response = await fetch(`/api/util/expire/${editFile.value.stored_filename}?expire_days=${newExpireDays.value}`, {
      method: 'PUT'
    })

    const data = await response.json()

    if (response.ok) {
      message.success('过期时间更新成功')
      showEditExpireDialog.value = false
      loadFileList() // 重新加载文件列表
    } else {
      message.error(data.error || '更新失败')
    }
  } catch (error) {
    message.error('网络错误: ' + error.message)
  } finally {
    editExpireLoading.value = false
  }
}

// 页面加载时获取文件列表
onMounted(() => {
  loadFileList()

  // 监听窗口大小变化以检测移动设备模式
  const handleResize = () => {
    isMobile.value = window.innerWidth < 768
  }

  window.addEventListener('resize', handleResize)

  // 组件卸载时移除事件监听
  onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
  })
})
</script>

<style scoped>
.file-management-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.file-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 16px;
  padding: 10px 0;
}

.file-item {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
  background-color: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.file-item:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
  border-color: #2080f0;
}

.file-icon {
  margin-bottom: 8px;
}

.file-name {
  font-size: 13px;
  font-weight: 500;
  word-break: break-word;
  margin-bottom: 4px;
  color: #333;
}

.file-size {
  font-size: 12px;
  color: #666;
  margin-bottom: 4px;
}

.file-date {
  font-size: 11px;
  color: #999;
}

.file-expire {
  margin-top: 8px;
  font-size: 12px;
  color: #2080f0;
  font-weight: 500;
}

.file-preview {
  text-align: center;
  margin-bottom: 20px;
}

.preview-image {
  max-width: 100%;
  max-height: 200px;
  object-fit: contain;
  border-radius: 4px;
  border: 1px solid #e0e0e0;
}

.preview-video {
  max-width: 100%;
  max-height: 300px;
  border-radius: 4px;
  border: 1px solid #e0e0e0;
}

.file-detail-content {
  padding: 16px 0;
}

/* Mobile responsiveness */
@media (max-width: 768px) {
  .file-management-container {
    padding: 10px;
  }

  .file-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 12px;
  }

  .file-item {
    padding: 8px;
  }

  .file-name {
    font-size: 12px;
  }

  .file-size {
    font-size: 11px;
  }

  .file-date {
    font-size: 10px;
  }

  .preview-image,
  .preview-video {
    max-height: 150px;
  }
}

@media (max-width: 480px) {
  .file-grid {
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 10px;
  }

  .file-name {
    font-size: 11px;
  }

  .file-size,
  .file-date {
    font-size: 10px;
  }
}
</style>