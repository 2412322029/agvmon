<template>
  <FileManagementComponent 
    title="文件上传管理"
    :show-upload="true"
    :show-files="true"
    upload-button-text="选择文件上传"
    :default-expire-days="7"
    @file-selected="onFileSelected"
    @file-uploaded="onFileUploaded"
    @file-deleted="onFileDeleted"
  />
</template>

<script setup>
import FileManagementComponent from '@/components/FileManagementComponent.vue'

// Event handlers
const onFileSelected = (file) => {
  console.log('File selected:', file)
}

const onFileUploaded = (response) => {
  console.log('File uploaded:', response)
}

const onFileDeleted = (filename) => {
  console.log('File deleted:', filename)
}
</script>

<style scoped>
.file-upload-container {
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
  .file-upload-container {
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

  .preview-image {
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