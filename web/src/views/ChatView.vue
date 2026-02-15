<template>
  <n-layout style="height: calc(100vh - 80px); display: flex; flex-direction: column; margin: 0 auto; max-width: 100%;">


    <!-- Scrollable Content Area -->
    <n-layout-content ref="messagesContainer"
      style="overflow-y: auto; padding: 16px; background-color: #f9f9f9; flex: 1; margin-top: 0; margin-bottom: 0;">
      <div v-for="(group, groupIndex) in groupedMessages" :key="groupIndex" :style="{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: group.sender === getStoredNickname() ? ' ' : 'flex-start',
        flexDirection: group.sender === getStoredNickname() ? 'row-reverse' : 'row',
        marginBottom: '16px'
      }">
        <!-- Avatar circle with initials - only shown once per group -->
        <div :style="{
          width: '40px',
          height: '40px',
          borderRadius: '50%',
          backgroundColor: group.sender === getStoredNickname() ? '#1890ff' : '#66b3ff',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          fontWeight: 'bold',
          fontSize: '16px',
          marginRight: group.sender === getStoredNickname() ? '0' : '12px',
          marginLeft: group.sender === getStoredNickname() ? '12px' : '0',
          flexShrink: 0
        }">
          {{ getInitials(group.sender) }}
        </div>

        <!-- Message bubble container -->
        <div :style="{
          display: 'flex',
          flexDirection: 'column',
          maxWidth: '70%'
        }">
          <!-- Username (top right for own messages, top left for others) -->
          <div :style="{
            textAlign: group.sender === getStoredNickname() ? 'right' : 'left',
            marginBottom: '4px',
            fontSize: '0.85em',
            color: '#666'
          }">
            <span style="font-weight: bold; color: #333;">{{ group.sender }}</span>
          </div>

          <!-- All messages in the group -->
          <div v-for="(message, msgIndex) in group.messages" :key="message.id" :style="{
            display: 'flex',
            flexDirection: group.sender === getStoredNickname() ? 'row-reverse' : 'row',
          }">
            <!-- Message bubble -->
            <div :style="{
              padding: '10px 14px',
              borderRadius: group.sender === getStoredNickname() ? '18px 4px 18px 18px' : '4px 18px 18px 18px',
              backgroundColor: group.sender === getStoredNickname() ? '#9eea6a' : '#ffffff',
              border: group.sender === getStoredNickname() ? 'none' : '1px solid #e0e0e0',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
              wordWrap: 'break-word',
              wordBreak: 'break-word',
              width: 'max-content',
              marginTop: msgIndex > 0 ? '4px' : '0'
            }">
              <div v-if="message.content" style="margin-bottom: 6px; white-space: pre-wrap;">
                {{ message.content }}
              </div>

              <div v-if="message.file">
                <!-- Image preview -->
                <div v-if="isImageFile(message.file)" class="image-preview">
                  <div
                    style="max-width: 200px; max-height: 300px; display: flex; align-items: center; justify-content: center; border-radius: 8px; overflow: hidden; border: 1px solid #e0e0e0; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <img :src="`/api/util/download/${message.file.stored_filename}`"
                      :alt="message.file.original_filename"
                      @click="openImage(`/api/util/download/${message.file.stored_filename}`)"
                      style="overflow: auto; cursor: pointer; object-fit: contain;" />
                  </div>
                  <div style="font-size: 0.75em; color: #666; margin-top: 4px;">
                    <span style="cursor: pointer; text-decoration: underline;"
                      @click.stop="showFileDetails(message.file)">
                      {{ message.file.original_filename }}
                    </span>
                    <span> ({{ formatFileSize(message.file.size) }})</span>
                  </div>
                </div>
                <!-- Other file types -->
                <div v-else
                  style="display: flex; flex-direction: column; padding: 12px; background: #f5f5f5; border-radius: 8px; cursor: pointer; max-width: 200px; border: 1px solid #e0e0e0;"
                  @click="showFileDetails(message.file)">
                  <div style="display: flex; align-items: center;">
                    <n-icon size="24" style="margin-right: 8px; color: #1890ff;">
                      <document-text-outline />
                    </n-icon>
                    <div style="flex: 1; min-width: 0;">
                      <div
                        style="color: #1890ff; text-decoration: underline; cursor: pointer; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500;">
                        {{ message.file.original_filename }}
                      </div>
                      <div style="font-size: 0.8em; color: #888; margin-top: 2px;">
                        ({{ formatFileSize(message.file.size) }})
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Timestamp in the middle of the group -->
          <div :style="{
            textAlign: group.sender === getStoredNickname() ? 'right' : 'left',
            marginTop: '4px',
            fontSize: '0.75em',
            color: '#999'
          }">
            <span>{{ formatDate(group.lastTimestamp) }}</span>
          </div>
        </div>
      </div>
    </n-layout-content>

    <!-- Fixed Footer -->
    <n-layout-footer bordered
      style="background: #fff; padding: 12px; position: sticky; bottom: 0; z-index: 100; flex-shrink: 0;">
      <n-input v-model:value="messageText" type="textarea" placeholder="输入消息..." :autosize="{ minRows: 2, maxRows: 4 }"
        @keydown.enter.prevent="handleEnterKey" style="margin-bottom: 12px;" />

      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <FileSelectorComponent @file-selected="handleFileSelectedFromSelector" @file-uploaded="handleFileUploaded" />
          <span v-if="selectedFile"
            style="font-size: 0.9em; color: #666; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            {{ selectedFile.name }}
          </span>
          <n-tag :type="connectionStatusColor" size="small">
            {{ connectionStatusText }}
          </n-tag>
        </div>
        <div style="display: flex; align-items: center; gap: 10px;">
          <span>
            name:<n-input v-model:value="nickname" placeholder="昵称" size="small" style="width: 120px;"
              @blur="saveNickname" />
          </span>
          <n-button @click="sendMessage" :disabled="!canSendMessage" type="primary" :loading="sending">
            发送
          </n-button>
        </div>
      </div>
    </n-layout-footer>

    <n-modal v-model:show="imageModalVisible" preset="card"
      style="width: 80vw; max-width: 90vw; height: 80vh; max-height: 90vh;">
      <div style="display: flex; justify-content: center; align-items: center; height: 100%;">
        <img :src="currentImage" :fallback-src="'https://placehold.co/800x600?text=Image'"
          style="overflow: auto; object-fit: contain; height: 90%;" :preview-src="currentImage" />
      </div>
    </n-modal>

    <!-- File Details Modal -->
    <n-modal v-model:show="fileDetailsModalVisible" preset="card"
      style="width: 800px; max-width: 90vw; height: 80vh; max-height: 90vh;"
      :title="selectedFileDetail?.original_filename || '文件详情'">
      <div v-if="selectedFileDetail.content_type.includes('mp4')"
        style="max-width: 100%; max-height: 60%; display: flex; align-items: center; justify-content: center; border-radius: 4px; overflow: hidden;">
        <video :src="`/api/util/download/${selectedFileDetail.stored_filename}`"
          style="overflow: auto;cursor: pointer; object-fit: contain; border-radius: 4px;" controls
          preload="metadata" />
      </div>
      <div v-else-if="selectedFileDetail.content_type.includes('image')"
        style="display: flex; align-items: center; justify-content: center; border-radius: 4px; overflow: hidden; margin-bottom: 16px;">
        <img :src="`/api/util/download/${selectedFileDetail.stored_filename}`"
          :alt="selectedFileDetail.original_filename"
          style="overflow: auto;; cursor: pointer; object-fit: contain; border-radius: 4px;"
          :preview-src="`/api/util/download/${selectedFileDetail.stored_filename}`"
          :fallback-src="'https://placehold.co/800x600?text=Image'" />
      </div>
      <div v-if="selectedFileDetail" style="padding: 16px; max-height: 40%; overflow-y: auto;">
        <div style="margin-bottom: 16px;">
          <strong>文件名:</strong> {{ selectedFileDetail.original_filename }}
        </div>
        <div style="margin-bottom: 16px;">
          <strong>文件大小:</strong> {{ formatFileSize(selectedFileDetail.size) }}
        </div>
        <div style="margin-bottom: 16px;">
          <strong>上传时间:</strong> {{ formatDate(selectedFileDetail.upload_time || new Date().toISOString()) }}
        </div>
        <div style="margin-bottom: 16px;">
          <strong>类型:</strong> {{ getFileType(selectedFileDetail.original_filename) }} | {{
            selectedFileDetail.content_type || '-' }}
        </div>
        <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px;">
          <n-button @click="fileDetailsModalVisible = false">关闭</n-button>
          <n-button
            @click="downloadFile(`/api/util/download/${selectedFileDetail.stored_filename}`, selectedFileDetail.original_filename)"
            type="primary">下载</n-button>
        </div>
      </div>
    </n-modal>
  </n-layout>
</template>

<script setup>
import { DocumentTextOutline } from '@vicons/ionicons5';
import {
  NButton,
  NIcon,
  NInput,
  NLayout,
  NLayoutContent,
  NLayoutFooter,
  NModal,
  NTag,
  useMessage
} from 'naive-ui';
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue';

// Import icons
// import { DescriptionOutline } from '@vicons/ionicons5';

// Import FileSelectorComponent
import FileSelectorComponent from '../components/FileSelectorComponent.vue';

const message = useMessage();

const messages = ref([]);
const messageText = ref('');
const nickname = ref(getStoredNickname());
const selectedFile = ref(null);
const ws = ref(null);
const messagesContainer = ref(null);
const imageModalVisible = ref(false);
const currentImage = ref('');
const fileDetailsModalVisible = ref(false);
const selectedFileDetail = ref(null);
const sending = ref(false);

// Group messages for display (to show sender and timestamp only when needed)
const groupedMessages = computed(() => {
  const groups = [];
  let currentGroup = null;

  messages.value.forEach((message, index) => {
    // Check if this message should be grouped with the previous one
    const shouldGroup = currentGroup &&
      currentGroup.sender === message.sender &&
      // Group if the time difference is less than 5 minutes (300000 ms)
      new Date(message.timestamp) - new Date(currentGroup.lastTimestamp) < 300000;

    if (shouldGroup) {
      // Add message to current group
      currentGroup.messages.push(message);
      currentGroup.lastTimestamp = message.timestamp;
    } else {
      // Start a new group
      currentGroup = {
        sender: message.sender,
        lastTimestamp: message.timestamp,
        messages: [message]
      };
      groups.push(currentGroup);
    }
  });

  return groups;
});

// WebSocket connection status
const connectionStatus = ref('connecting'); // 'connecting', 'connected', 'disconnected'

// WebSocket connection status computed properties
const connectionStatusText = computed(() => {
  switch (connectionStatus.value) {
    case 'connected':
      return '已连接';
    case 'disconnected':
      return '已断开';
    case 'connecting':
    default:
      return '连接中...';
  }
});

const connectionStatusColor = computed(() => {
  switch (connectionStatus.value) {
    case 'connected':
      return 'success';
    case 'disconnected':
      return 'error';
    case 'connecting':
    default:
      return 'warning';
  }
});

// Initialize WebSocket connection to global chat
function initWebSocket() {
  // Close existing connection if any
  if (ws.value) {
    ws.value.close();
  }

  // Set connecting status
  connectionStatus.value = 'connecting';

  // Connect to WebSocket
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/chat`;

  try {
    ws.value = new WebSocket(wsUrl);

    ws.value.onopen = () => {
      console.log('Connected to global chat room');
      connectionStatus.value = 'connected';
      message.success('已连接到聊天室');
      // Load chat history when connected
      loadChatHistory();
    };

    ws.value.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Check if it's an error message
        if (data.error) {
          console.error('Chat error:', data.error);
          message.error(data.error);
          return;
        }

        // Add message to the list
        messages.value.push(data);

        // Show browser notification if it's not from the current user and notifications are enabled
        showNotification(data);

        // Scroll to bottom
        nextTick(() => scrollToBottom());
      } catch (error) {
        console.error('Error parsing message:', error);
        message.error('消息解析错误');
      }
    };

    ws.value.onclose = () => {
      console.log('Disconnected from global chat room');
      connectionStatus.value = 'disconnected';
      message.warning('已断开聊天室连接');
    };

    ws.value.onerror = (error) => {
      console.error('WebSocket error:', error);
      connectionStatus.value = 'disconnected';
      message.error('WebSocket连接错误');
    };
  } catch (error) {
    console.error('Failed to create WebSocket connection:', error);
    connectionStatus.value = 'disconnected';
    message.error('WebSocket连接创建失败');
  }
}

// Load chat history
async function loadChatHistory() {
  try {
    const response = await fetch('/api/util/chat/history?limit=50');
    const result = await response.json();

    if (result.messages) {
      messages.value = [...result.messages].reverse(); // Reverse to show oldest first
      nextTick(() => scrollToBottom());
    }
  } catch (error) {
    console.error('Failed to load chat history:', error);
    message.error('加载历史消息失败');
  }
}

// Send a message
async function sendMessage() {
  if (!canSendMessage.value) return;
  console.log('Sending message:', messageText.value);
  sending.value = true;

  let messageType = 'text';
  let fileData = null;

  // Handle file if present (file already uploaded by FileSelectorComponent)
  if (selectedFile.value) {
    // File was already uploaded via FileSelectorComponent, use the stored info
    fileData = selectedFile.value.file;
    messageType = messageText.value.trim() ? 'text_file' : 'file';
  } else if (messageText.value.trim()) {
    messageType = 'text';
  } else {
    sending.value = false;
    return; // Nothing to send
  }

  // Prepare message data
  const messageData = {
    type: messageType,
    content: messageText.value.trim(),
    sender: nickname.value || Math.random().toString(36).substring(2, 8),
    timestamp: new Date().toISOString()
  };

  // Add file info if present
  if (fileData) {
    messageData.file = fileData;
  }

  // Send message via WebSocket
  if (ws.value && ws.value.readyState === WebSocket.OPEN) {
    ws.value.send(JSON.stringify(messageData));

    // Clear input
    messageText.value = '';
    selectedFile.value = null;
  } else {
    message.error('WebSocket未连接');
  }

  sending.value = false;
}

// Handle file selection from FileSelectorComponent
function handleFileSelectedFromSelector(file) {
  // For files selected from the component, we can directly use the file object
  selectedFile.value = {
    name: file.original_filename,
    file: file // Store the file info object from the selector
  };
}

// Handle file uploaded event from FileSelectorComponent
function handleFileUploaded(uploadResult) {
  // Optional: Handle successful upload notification
  console.log('File uploaded via selector:', uploadResult);
}

// Format date for display
function formatDate(dateString) {
  const date = new Date(dateString);
  return date.toLocaleString();
}

// Get first letter of username for avatar
function getInitials(username) {
  if (!username) return '?';
  return username.charAt(0).toUpperCase();
}

// Show file details modal
function showFileDetails(file) {
  selectedFileDetail.value = file;
  // console.log('showFileDetails', file);

  fileDetailsModalVisible.value = true;
}

// Get file type from extension
function getFileType(filename) {
  const ext = filename.split('.').pop()?.toLowerCase();
  if (!ext) return '未知类型';

  const imageTypes = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'];
  const docTypes = ['pdf', 'doc', 'docx', 'txt', 'xls', 'xlsx', 'ppt', 'pptx'];
  const archiveTypes = ['zip', 'rar', '7z', 'tar', 'gz'];

  if (imageTypes.includes(ext)) return '图片文件';
  if (docTypes.includes(ext)) return '文档文件';
  if (archiveTypes.includes(ext)) return '压缩文件';

  return `${ext.toUpperCase()} 文件`;
}

// Download file function
function downloadFile(url, filename) {
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// Format file size
function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Check if file is an image
function isImageFile(file) {
  if (!file.original_filename) return false;
  if (!file.content_type) return false;
  if (!file.content_type.includes('image')) return false;

  const ext = file.original_filename.split('.').pop()?.toLowerCase();
  if (!ext) return false;

  const imageExtensions = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'];
  return imageExtensions.includes(ext);
}

// Check if file is a video
function isVideoFile(file) {
  if (!file.original_filename) return false;
  if (!file.content_type) return false;
  if (!file.content_type.includes('video')) return false;

  const ext = file.original_filename.split('.').pop()?.toLowerCase();
  if (!ext) return false;

  const videoExtensions = ['mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv', 'm4v'];
  return videoExtensions.includes(ext);
}

// Request notification permission and show browser notification
function showNotification(data) {
  // Don't show notification if it's from the current user
  if (data.sender === getStoredNickname()) {
    return;
  }

  // Check if browser supports notifications
  if (!('Notification' in window)) {
    console.log('This browser does not support desktop notification');
    return;
  }

  // Check if permission has been granted
  if (Notification.permission === 'granted') {
    // Create notification
    createNotification(data);
  } 
  // If permission hasn't been granted, request it
  else if (Notification.permission !== 'denied') {
    Notification.requestPermission().then(function(permission) {
      if (permission === 'granted') {
        createNotification(data);
      }
    });
  }
}

// Create and show the actual notification
function createNotification(data) {
  let title = data.sender;
  let body = '';

  // Set body content based on message type
  if (data.content) {
    body = data.content.length > 50 ? data.content.substring(0, 50) + '...' : data.content;
  }

  if (data.file) {
    if (body) {
      body += ' '; // Add space if there's already content
    }
    body += `[文件: ${data.file.original_filename}]`;
  }

  // Create notification with fallback options
  const notificationOptions = {
    body: body,
    icon: '/favicon.ico', // Use the app's favicon
    badge: '/favicon.ico', // Badge icon for notification
    requireInteraction: false, // Auto-dismiss after a few seconds
    tag: 'chat-message-' + Date.now() // Unique tag to prevent duplicates
  };

  try {
    const notification = new Notification(title, notificationOptions);
    
    // Add click handler to focus the window when notification is clicked
    notification.onclick = function() {
      window.focus();
      notification.close();
    };
  } catch (error) {
    console.error('Error creating notification:', error);
  }
}

// Scroll to bottom of messages
function scrollToBottom() {
  if (messagesContainer.value?.el) {
    messagesContainer.value.el.scrollTop = messagesContainer.value.el.scrollHeight;
  }
  document.querySelector(".n-layout-scroll-container").scrollTo(0,100011)
}

// Open image in modal
function openImage(imageSrc) {
  currentImage.value = imageSrc;
  imageModalVisible.value = true;
}

// Close image modal
function closeImageModal() {
  imageModalVisible.value = false;
  currentImage.value = '';
}

// Save nickname to localStorage
function saveNickname() {
  if (nickname.value.trim()) {
    localStorage.setItem('chatNickname', nickname.value.trim());
  }
}

// Get stored nickname
function getStoredNickname() {
  return localStorage.getItem('chatNickname') || Math.random().toString(36).substring(2, 8);
}

// Handle Enter key press
function handleEnterKey(event) {
  if (event.ctrlKey) {
    messageText.value += '\n';
  } else {
    sendMessage();
  }
}

// Computed properties
const canSendMessage = computed(() => {
  return (messageText.value.trim() !== '' || selectedFile.value !== null) &&
    ws.value && ws.value.readyState === WebSocket.OPEN && !sending.value;
});

// Lifecycle hooks
onMounted(() => {
  // Set initial nickname
  if (!nickname.value) {
    nickname.value = getStoredNickname();
  }

  // Initialize WebSocket
  initWebSocket();

  // Set up auto-scroll
  const observer = new MutationObserver(scrollToBottom);
  if (messagesContainer.value?.el) {
    observer.observe(messagesContainer.value.el, {
      childList: true,
      subtree: true
    });
  }
});

onUnmounted(() => {
  // Close WebSocket connection
  if (ws.value) {
    ws.value.close();
  }
});

// Expose variables and functions
defineExpose({
  messages,
  messageText,
  nickname,
  selectedFile,
  ws,
  messagesContainer,
  imageModalVisible,
  currentImage,
  sendMessage,
  handleFileSelectedFromSelector,
  handleFileUploaded,
  formatDate,
  formatFileSize,
  scrollToBottom,
  openImage,
  closeImageModal,
  saveNickname,
  getStoredNickname,
  canSendMessage,
  handleEnterKey,
  sending,
  connectionStatus,
  connectionStatusText,
  connectionStatusColor,
  downloadFile,
  getInitials
});
</script>

<style scoped>
/* No custom styles needed as we're using Naive UI components */
</style>