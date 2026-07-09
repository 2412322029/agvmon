/**
 * Update state management — singleton composable.
 *
 * Usage:
 *   import { useUpdate } from '../composables/useUpdate'
 *   const { status, checkForUpdates, downloadUpdate, applyUpdate } = useUpdate()
 */

import { ref } from 'vue'

// ── module-level singleton state ──────────────────────────────

const status = ref('idle')
// idle | checking | update_available | downloading | ready | applying | error

const updateInfo = ref(null)
const downloadProgress = ref(0)
const errorMessage = ref('')
const currentVersion = ref('')

// ── helpers ───────────────────────────────────────────────────

function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

// ── actions ───────────────────────────────────────────────────

async function checkForUpdates() {
  status.value = 'checking'
  errorMessage.value = ''

  try {
    const resp = await fetch('/api/update/check')
    const data = await resp.json()

    currentVersion.value = data.current_version || ''

    if (data.update_available) {
      status.value = 'update_available'
      updateInfo.value = data.latest
    } else if (data.error && data.error !== '更新服务器未配置') {
      status.value = 'error'
      errorMessage.value = data.error
    } else {
      status.value = 'idle'
      errorMessage.value = data.error || ''
    }
    _initDone = true
    return data
  } catch (e) {
    status.value = 'error'
    errorMessage.value = '网络错误: ' + e.message
    _initDone = true
    return { update_available: false, error: errorMessage.value }
  }
}

function downloadUpdate() {
  return new Promise((resolve, reject) => {
    status.value = 'downloading'
    downloadProgress.value = 0
    errorMessage.value = ''

    // Use EventSource for SSE progress
    const es = new EventSource('/api/update/download')

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)

        if (data.event === 'progress') {
          downloadProgress.value = data.percent
        } else if (data.event === 'complete') {
          status.value = 'ready'
          es.close()
          resolve(data)
        } else if (data.event === 'error') {
          status.value = 'error'
          errorMessage.value = data.message || '下载失败'
          es.close()
          reject(new Error(errorMessage.value))
        }
      } catch {
        // ignore parse errors
      }
    }

    es.onerror = () => {
      es.close()
      // If we're in 'ready' state, the stream closed after complete — that's OK
      if (status.value !== 'ready' && status.value !== 'error') {
        // SSE error might be normal close; check if we got progress
        if (downloadProgress.value > 0 && downloadProgress.value >= 99) {
          status.value = 'ready'
          resolve({ event: 'complete' })
        } else {
          status.value = 'error'
          errorMessage.value = '连接中断，请重试'
          reject(new Error(errorMessage.value))
        }
      }
    }
  })
}

async function applyUpdate() {
  status.value = 'applying'
  errorMessage.value = ''

  try {
    const resp = await fetch('/api/update/apply', { method: 'POST' })
    const data = await resp.json()

    if (data.status === 'error') {
      status.value = 'error'
      errorMessage.value = data.message || '应用更新失败'
    }
    // If applying, the server will shut down — status stays 'applying'
    return data
  } catch {
    // Server shutting down causes fetch to fail — that's expected
    status.value = 'applying'
  }
}

// ── restore state from backend ─────────────────────────────────

let _initDone = false

async function restoreState() {
  try {
    const resp = await fetch('/api/update/status')
    const data = await resp.json()
    // 仅在自动检查尚未完成时恢复状态（防止竞态覆盖）
    if (_initDone) return
    if (data.status === 'ready') {
      status.value = 'ready'
      if (data.latest) updateInfo.value = data.latest
    } else if (data.status === 'downloading') {
      status.value = 'downloading'
    }
  } catch {
    // ignore
  }
}

// Restore on module init (page refresh)
restoreState()

// ── export ────────────────────────────────────────────────────

export function useUpdate() {
  return {
    status,
    updateInfo,
    downloadProgress,
    errorMessage,
    currentVersion,
    formatSize,
    checkForUpdates,
    downloadUpdate,
    applyUpdate,
  }
}
