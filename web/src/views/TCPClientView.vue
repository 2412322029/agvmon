<template>
  <div class="tcp-client-page">
    <!-- 顶部说明与状态 -->
    <n-card size="small" :bordered="false" class="head-card">
      <div class="head">
        <div>
          <h2 class="title">TCP 客户端</h2>
          <p class="desc">
            连接任意 host:port 进行文本 / HEX 收发调试。连接与收发记录保存在后端
            （每会话默认 500 条），页面通过 WebSocket 实时接收。
          </p>
        </div>
        <n-space align="center" size="small">
          <n-tag :type="wsTagType" size="small" :bordered="false">{{ wsLabel }}</n-tag>
          <n-button size="small" :loading="loadingSessions" @click="loadSessions">刷新会话</n-button>
        </n-space>
      </div>
    </n-card>

    <div class="layout">
      <!-- 左栏：新建 + 会话列表 -->
      <div class="col-left">
        <n-card size="small" title="新建连接" :bordered="false">
          <template #header-extra>
            <n-text depth="3" class="hint">回车即连接</n-text>
          </template>
          <n-form class="conn-form" label-placement="left" label-width="52" size="small" :show-feedback="false">
            <n-form-item label="地址">
              <n-input-group>
                <n-input v-model:value="form.host" placeholder="主机 / IP" @keyup.enter="createSession" />
                <n-input-number v-model:value="form.port" :min="1" :max="65535" :show-button="false"
                  placeholder="端口" class="port-input" @keyup.enter="createSession" />
              </n-input-group>
            </n-form-item>
            <n-form-item label="名称">
              <n-input v-model:value="form.name" placeholder="可选，默认 host:port" />
            </n-form-item>
            <n-form-item label="编码">
              <n-select v-model:value="form.encoding" :options="encodingOptions" />
            </n-form-item>
            <n-form-item label="重连">
              <div class="switch-row">
                <n-switch v-model:value="form.autoReconnect" size="small" />
                <n-text depth="3" class="hint">断线后自动重连</n-text>
              </div>
            </n-form-item>
          </n-form>
          <n-button type="primary" size="small" block :loading="creating" class="connect-btn" @click="createSession">
            新建并连接
          </n-button>

          <div v-if="history.length" class="history">
            <n-text depth="3" class="hint">最近使用：</n-text>
            <n-tag v-for="item in history" :key="item" size="small" :bordered="false" class="history-tag"
              @click="applyHistory(item)">{{ item }}</n-tag>
          </div>
        </n-card>

        <n-card size="small" :title="`会话（${sessions.length}）`" :bordered="false">
          <n-empty v-if="!sessions.length" description="暂无连接" size="small" style="margin: 12px 0" />
          <div v-for="s in sessions" :key="s.id" :class="['session', s.id === activeId ? 'session-active' : '']"
            @click="selectSession(s.id)">
            <div class="session-row">
              <n-tag :type="stateType(s.state)" size="tiny" :bordered="false">{{ stateLabel(s.state) }}</n-tag>
              <span class="session-name" :title="`${s.host}:${s.port}`">{{ s.name }}</span>
              <n-button text size="tiny" type="error" @click.stop="removeSession(s)">删除</n-button>
            </div>
            <div class="session-meta">
              <span>↑ {{ fmtBytes(s.bytes_sent) }} / {{ s.tx_count }} 包</span>
              <span>↓ {{ fmtBytes(s.bytes_recv) }} / {{ s.rx_count }} 包</span>
              <span v-if="s.auto_reconnect" class="auto-on">自动重连</span>
            </div>
            <div class="session-actions" @click.stop>
              <n-button size="tiny" :disabled="s.state === 'connected' || s.state === 'connecting'"
                @click="connectSession(s)">连接</n-button>
              <n-button size="tiny" :disabled="s.state !== 'connected' && s.state !== 'connecting'"
                @click="disconnectSession(s)">断开</n-button>
              <n-button size="tiny" @click="clearLog(s)">清空记录</n-button>
            </div>
          </div>
        </n-card>
      </div>

      <!-- 右栏：收发面板 -->
      <div class="col-right">
        <n-card size="small" :bordered="false" class="panel-card">
          <template #header>
            <div class="panel-head">
              <span class="panel-name" :title="activeSession ? `${activeSession.host}:${activeSession.port}` : ''">
                {{ activeSession ? activeSession.name : '收发面板' }}
              </span>
              <span class="panel-meta" :title="activeSession?.connected_at || ''">{{ panelMeta }}</span>
            </div>
          </template>
          <template #header-extra>
            <div class="panel-tools">
              <n-dropdown trigger="click" :options="liftMenuOptions" :disabled="!liftTotal" @select="sendBatchToLift">
                <n-button size="small" :disabled="!liftTotal" title="把收发记录以 HEX 形式送到「电梯报文解析」">
                  <template #icon>
                    <n-icon :component="CaretDownOutlined" />
                  </template>
                  报文解析
                </n-button>
              </n-dropdown>
              <n-checkbox v-model:checked="liftOnlyAb66" size="small"
                title="只交接电梯报文：AB66 开头的帧及其分片续帧，其它噪声（心跳/文本）会被丢掉">
                仅 AB66
              </n-checkbox>
              <n-radio-group v-model:value="displayMode" size="small">
                <n-radio-button value="text">文本</n-radio-button>
                <n-radio-button value="hex">HEX</n-radio-button>
                <n-radio-button value="both">全部</n-radio-button>
              </n-radio-group>
              <n-checkbox v-model:checked="showSys" size="small">系统消息</n-checkbox>
              <n-checkbox v-model:checked="autoScroll" size="small">自动滚动</n-checkbox>
              <n-button size="small" :disabled="!activeSession" @click="clearLog()">清空</n-button>
            </div>
          </template>

          <div ref="logBox" class="log-box">
            <n-empty v-if="!visibleEntries.length" description="暂无收发记录" size="small" style="margin-top: 60px" />
            <div v-for="entry in visibleEntries" :key="entry.seq" :class="['entry', `entry-${entry.direction}`]">
              <span class="entry-ts">{{ entry.ts }}</span>
              <span class="entry-dir">{{ dirLabel(entry.direction) }}</span>
              <span class="entry-size">{{ entry.size ? `${entry.size}B` : '' }}</span>
              <span class="entry-body">
                <template v-if="entry.direction === 'sys'">{{ entry.note }}</template>
                <template v-else>
                  <span v-if="displayMode !== 'hex'" class="entry-text">{{ entry.text }}</span>
                  <span v-if="displayMode !== 'text'" class="entry-hex">{{ entry.hex }}</span>
                  <span v-if="entry.note" class="entry-note">{{ entry.note }}</span>
                </template>
              </span>
              <span class="entry-lift">
                <n-button v-if="entry.hex" text size="tiny" title="发送到电梯报文解析（HEX）"
                  @click="sendEntryToLift(entry)">解析</n-button>
              </span>
            </div>
          </div>

          <div class="send-box">
            <n-space size="small" align="center" style="margin-bottom: 6px">
              <n-radio-group v-model:value="sendMode" size="small">
                <n-radio-button value="text">文本</n-radio-button>
                <n-radio-button value="hex">HEX</n-radio-button>
              </n-radio-group>
              <n-select v-model:value="sendNewline" :options="newlineOptions" size="small" style="width: 132px" />
            </n-space>

            <div class="loop-row">
              <n-checkbox v-model:checked="loopSend" size="small">定时发送</n-checkbox>
              <n-input-number v-model:value="loopInterval" :min="loopMin" :max="loopMax" :step="loopStep"
                :precision="loopUnit === 's' ? 2 : 0" :show-button="false" size="small" class="loop-input"
                @keyup.enter="onIntervalChange" />
              <n-select v-model:value="loopUnit" :options="loopUnitOptions" size="small" class="loop-unit" />
              <n-text v-if="loopSend" depth="3" class="hint">运行中 · 已发 {{ loopCount }} 帧 / 每 {{ loopDelayMs }} ms</n-text>
              <n-text v-else depth="3" class="hint">发送间隔，可随时修改</n-text>
            </div>

            <n-input v-model:value="sendText" type="textarea" :rows="3" :disabled="!activeSession"
              :placeholder="sendMode === 'hex' ? '十六进制，如 01 02 0A' : '输入要发送的内容，Ctrl+Enter 发送'"
              @keydown.ctrl.enter.prevent="sendManual" />
            <n-space justify="end" align="center" style="margin-top: 6px">
              <n-text v-if="lastSendInfo" depth="3" class="hint">{{ lastSendInfo }}</n-text>
              <n-button size="small" type="primary" :disabled="!canSend" :loading="sending" @click="sendManual">
                发送
              </n-button>
            </n-space>
          </div>
        </n-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { CaretDownOutlined } from '@vicons/antd'
import {
  NButton,
  NCard,
  NCheckbox,
  NDropdown,
  NEmpty,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NInputGroup,
  NInputNumber,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpace,
  NSwitch,
  NTag,
  NText,
  useMessage,
} from 'naive-ui'
import { computed, nextTick, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const message = useMessage()
const router = useRouter()

// ── 状态 ──
const sessions = ref([])
const activeId = ref('')
const entries = ref([])
const loadingSessions = ref(false)
const creating = ref(false)
const sending = ref(false)
const lastSendInfo = ref('')

const wsState = ref('closed') // closed | connecting | open | gone
const wsAttempts = ref(0)
let ws = null
let wsTimer = null
let stopWs = false
let pollTimer = null

const HISTORY_KEY = 'tcp-client:history'
const MAX_ENTRIES = 1000

// ── 表单与显示选项 ──
const form = reactive({
  host: '',
  port: null,
  name: '',
  encoding: 'utf-8',
  autoReconnect: false,
})

const history = ref(loadHistory())

const encodingOptions = ['utf-8', 'gbk', 'gb2312', 'ascii', 'latin-1'].map((v) => ({ label: v, value: v }))
const newlineOptions = [
  { label: '不追加', value: '' },
  { label: '\\n (LF)', value: 'lf' },
  { label: '\\r\\n (CRLF)', value: 'crlf' },
  { label: '\\r (CR)', value: 'cr' },
]

const displayMode = ref('text')
const showSys = ref(true)
const autoScroll = ref(true)
const sendMode = ref('text')
const sendNewline = ref('crlf')
const sendText = ref('')

// 定时发送：间隔 + 单位（毫秒 / 秒），运行中可随时改，改完立即按新间隔生效
const loopSend = ref(false)
const loopInterval = ref(1000)
const loopUnit = ref('ms')
const loopCount = ref(0)
let loopTimer = null
let intervalDebounce = null

const loopUnitOptions = [
  { label: '毫秒', value: 'ms' },
  { label: '秒', value: 's' },
]

const loopMin = computed(() => (loopUnit.value === 's' ? 0.05 : 50))
const loopMax = computed(() => (loopUnit.value === 's' ? 3600 : 3600000))
const loopStep = computed(() => (loopUnit.value === 's' ? 0.5 : 100))
const loopDelayMs = computed(() => {
  const raw = Number(loopInterval.value)
  if (!Number.isFinite(raw) || raw <= 0) return loopMin.value
  const ms = loopUnit.value === 's' ? raw * 1000 : raw
  return Math.max(50, Math.min(3600000, Math.round(ms)))
})

const logBox = ref(null)

// ── 计算属性 ──
const activeSession = computed(() => sessions.value.find((s) => s.id === activeId.value) || null)

/** 面板标题下的副标题：名称已等于 host:port 时不重复，时间只显示时分秒 */
const panelMeta = computed(() => {
  const s = activeSession.value
  if (!s) return '请选择或新建连接'
  const addr = `${s.host}:${s.port}`
  const parts = []
  if (s.name !== addr) parts.push(addr)
  parts.push(s.state === 'connected' && s.connected_at ? `连接于 ${shortTime(s.connected_at)}` : stateLabel(s.state))
  return parts.join(' · ')
})

const visibleEntries = computed(() => (showSys.value ? entries.value : entries.value.filter((e) => e.direction !== 'sys')))
const canSend = computed(
  () => !!activeSession.value && activeSession.value.state === 'connected' && !!sendText.value.trim(),
)

const wsLabel = computed(() => {
  if (!activeSession.value) return '未选择会话'
  return { open: '实时通道已连接', connecting: '实时通道连接中', closed: '实时通道已断开', gone: '会话不存在' }[wsState.value]
})
const wsTagType = computed(
  () => ({ open: 'success', connecting: 'info', closed: 'warning', gone: 'error' })[wsState.value],
)

// ── 工具函数 ──
function stateLabel(state) {
  return {
    idle: '未连接',
    connecting: '连接中',
    connected: '已连接',
    closed: '已断开',
    error: '错误',
  }[state] || state
}

function stateType(state) {
  return { connected: 'success', connecting: 'info', closed: 'default', idle: 'default', error: 'error' }[state] || 'default'
}

function dirLabel(direction) {
  return { tx: '发送 →', rx: '接收 ←', sys: '系统' }[direction] || direction
}

function dirName(direction) {
  return { tx: '发送', rx: '接收', sys: '系统' }[direction] || direction
}

/** 2026-09-20 14:33:12 → 今天只显示 14:33:12，其它日期显示 09-20 14:33:12 */
function shortTime(value) {
  if (!value) return ''
  const m = String(value).match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}:\d{2}:\d{2})/)
  if (!m) return String(value)
  const now = new Date()
  const isToday =
    Number(m[1]) === now.getFullYear() && Number(m[2]) === now.getMonth() + 1 && Number(m[3]) === now.getDate()
  return isToday ? m[4] : `${m[2]}-${m[3]} ${m[4]}`
}

function fmtBytes(size) {
  if (!size) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = size
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i += 1
  }
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

// ── 交接给「电梯报文解析」──
// 复用日志分析的那套 sessionStorage 协议：lift-protocol:frames / lift-protocol:source
const LIFT_HANDOFF_KEY = 'lift-protocol:frames'
const LIFT_HANDOFF_SRC = 'lift-protocol:source'
const LIFT_TOOL_PATH = '/lift-protocol'
const LIFT_MAX_FRAMES = 500

/** 记录里的 HEX 转成连续十六进制串（解析器会忽略所有非 HEX 字符）*/
function frameHex(entry) {
  return (entry.hex || '').replace(/[^0-9A-Fa-f]/g, '')
}

/** 是否像一帧 AB66 电梯报文（至少够读到 LEN 字节）*/
function isAb66Frame(entry) {
  const hex = frameHex(entry)
  return hex.length >= 10 && hex.slice(0, 4).toUpperCase() === 'AB66'
}

/**
 * 「仅 AB66」过滤：保留 AB66 开头的帧；上一帧没读完时，分片的续帧也保留，
 * 读完再恢复过滤。TX / RX 是两条独立流，各自记进度。
 * 帧总长 = 5(AB 66 BNK NOD LEN) + LEN + 2(SUM ETX) = LEN + 7
 */
function filterAb66(entries) {
  const remain = { tx: 0, rx: 0 }
  const kept = []
  for (const entry of entries) {
    const hex = frameHex(entry)
    if (!hex) continue
    const dir = entry.direction
    const bytes = hex.length / 2
    let keep = false
    if (remain[dir] > 0) {
      keep = true
      remain[dir] -= bytes
    } else if (isAb66Frame(entry)) {
      keep = true
      const len = parseInt(hex.slice(8, 10), 16)
      remain[dir] = Number.isFinite(len) ? len + 7 - bytes : 0
    }
    if (keep) {
      kept.push(entry)
      if (remain[dir] < 0) remain[dir] = 0
    }
  }
  return kept
}

const liftOnlyAb66 = ref(false)

const liftGroups = computed(() => {
  // 解析器遇到非 AB66 字节会中止并丢掉后面的帧，所以混有噪声时可只交接 AB66 帧
  const data = liftOnlyAb66.value
    ? filterAb66(entries.value)
    : entries.value.filter((e) => frameHex(e))
  return {
    tx: data.filter((e) => e.direction === 'tx'),
    rx: data.filter((e) => e.direction === 'rx'),
    all: data,
  }
})

const liftTotal = computed(() => liftGroups.value.all.length)

const liftMenuOptions = computed(() => [
  { label: `发送记录（${liftGroups.value.tx.length}）`, key: 'tx' },
  { label: `接收记录（${liftGroups.value.rx.length}）`, key: 'rx' },
  { label: `全部收发记录（${liftTotal.value}）`, key: 'all' },
])

const LIFT_KIND_LABEL = { tx: '发送', rx: '接收', all: '全部收发' }

/** 把若干条记录按 HEX 逐行交接给电梯报文解析，并跳转过去 */
function handoffToLift(list, label) {
  const frames = (list || []).filter((e) => frameHex(e))
  if (!frames.length) {
    message.warning(`当前没有可解析的${label || '报文'}${liftOnlyAb66.value ? '（已开启「仅 AB66」过滤）' : ''}`)
    return false
  }
  const picked = frames.slice(-LIFT_MAX_FRAMES)
  const session = activeSession.value
  const source = `TCP 客户端 ${session ? session.name : ''} · ${label}${liftOnlyAb66.value ? ' · 仅 AB66' : ''} · ${picked.length} 帧`
  try {
    sessionStorage.setItem(LIFT_HANDOFF_KEY, picked.map(frameHex).join('\n'))
    sessionStorage.setItem(LIFT_HANDOFF_SRC, source)
  } catch (err) {
    message.error('报文交接失败（sessionStorage 写入异常），可先复制再手动粘贴')
    return false
  }
  if (frames.length > picked.length) {
    message.info(`报文较多，仅交接最近 ${picked.length} 帧`)
  }
  router.push(LIFT_TOOL_PATH)
  return true
}

/** 批量：发送 / 接收 / 全部收发记录 */
function sendBatchToLift(kind) {
  handoffToLift(liftGroups.value[kind], LIFT_KIND_LABEL[kind])
}

/** 单条记录右侧的「解析」 */
function sendEntryToLift(entry) {
  handoffToLift([entry], dirName(entry.direction))
}

async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  let body = null
  try {
    body = await resp.json()
  } catch {
    body = null
  }
  if (!resp.ok) {
    throw new Error(body?.detail || body?.error || `请求失败（HTTP ${resp.status}）`)
  }
  return body
}

// ── 历史记录 ──
function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]').slice(0, 6)
  } catch {
    return []
  }
}

function pushHistory(host, port) {
  const item = `${host}:${port}`
  history.value = [item, ...history.value.filter((h) => h !== item)].slice(0, 6)
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.value))
}

function applyHistory(item) {
  const idx = item.lastIndexOf(':')
  form.host = item.slice(0, idx)
  form.port = Number(item.slice(idx + 1)) || null
}

// ── 会话列表 ──
async function loadSessions() {
  loadingSessions.value = true
  try {
    const data = await api('/api/tcp/sessions')
    sessions.value = data.sessions || []
    if (!sessions.value.some((s) => s.id === activeId.value)) {
      activeId.value = sessions.value.length ? sessions.value[0].id : ''
    }
  } catch (err) {
    message.error(err.message)
  } finally {
    loadingSessions.value = false
  }
}

function mergeSession(snapshot) {
  if (!snapshot?.id) return
  const idx = sessions.value.findIndex((s) => s.id === snapshot.id)
  if (idx === -1) sessions.value.unshift(snapshot)
  else sessions.value[idx] = { ...sessions.value[idx], ...snapshot }
}

async function createSession() {
  const host = (form.host || '').trim()
  const port = Number(form.port)
  if (!host) return message.warning('请填写主机地址')
  if (!port || port < 1 || port > 65535) return message.warning('端口范围应为 1-65535')

  creating.value = true
  try {
    const data = await api('/api/tcp/sessions', {
      method: 'POST',
      body: JSON.stringify({
        host,
        port,
        name: form.name || null,
        encoding: form.encoding,
        auto_reconnect: form.autoReconnect,
        connect: true,
      }),
    })
    pushHistory(host, port)
    sessions.value = [data.session, ...sessions.value.filter((s) => s.id !== data.session.id)]
    activeId.value = data.session.id
    entries.value = data.log || []
    openWs()
    if (data.success) message.success(`已连接 ${host}:${port}`)
    else message.error(data.error || '连接失败')
  } catch (err) {
    message.error(err.message)
  } finally {
    creating.value = false
  }
}

async function connectSession(s) {
  try {
    const data = await api(`/api/tcp/sessions/${s.id}/connect`, { method: 'POST' })
    mergeSession(data.session)
    message.success(`已连接 ${s.host}:${s.port}`)
    if (s.id === activeId.value) openWs()
  } catch (err) {
    message.error(err.message)
    await loadSessions()
  }
}

async function disconnectSession(s) {
  try {
    const data = await api(`/api/tcp/sessions/${s.id}/disconnect`, { method: 'POST' })
    mergeSession(data.session)
    message.info('已断开连接')
  } catch (err) {
    message.error(err.message)
  }
}

async function removeSession(s) {
  try {
    await api(`/api/tcp/sessions/${s.id}`, { method: 'DELETE' })
    message.success('会话已删除')
    if (s.id === activeId.value) {
      stopLoopSend()
      closeWs()
      activeId.value = ''
      entries.value = []
    }
    await loadSessions()
  } catch (err) {
    message.error(err.message)
  }
}

async function clearLog(s) {
  const id = s?.id || activeId.value
  if (!id) return
  try {
    await api(`/api/tcp/sessions/${id}/log`, { method: 'DELETE' })
    if (id === activeId.value) entries.value = []
    message.success('收发记录已清空')
  } catch (err) {
    message.error(err.message)
  }
}

async function selectSession(id) {
  if (activeId.value === id) return
  activeId.value = id
  entries.value = []
  stopLoopSend('已切换会话，定时发送已停止')
  openWs()
  try {
    const data = await api(`/api/tcp/sessions/${id}/log?after_seq=0&limit=500`)
    entries.value = data.log || []
    mergeSession(data.session)
  } catch (err) {
    message.error(err.message)
  }
}

// ── WebSocket 实时通道 ──
function openWs() {
  closeWs()
  const id = activeId.value
  if (!id) return

  wsState.value = 'connecting'
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/tcp-client/${id}`)

  ws.onopen = () => {
    wsAttempts.value = 0
    wsState.value = 'open'
  }

  ws.onmessage = (event) => {
    let msg
    try {
      msg = JSON.parse(event.data)
    } catch {
      return
    }
    if (msg.type === 'snapshot') {
      mergeSession(msg.data)
      if (Array.isArray(msg.log)) entries.value = msg.log
      scrollToBottom()
    } else if (msg.type === 'log') {
      entries.value.push(msg.entry)
      if (entries.value.length > MAX_ENTRIES) entries.value.splice(0, entries.value.length - MAX_ENTRIES)
      scrollToBottom()
    } else if (msg.type === 'state') {
      const patch = { id, state: msg.state, ...(msg.stats || {}) }
      if (msg.state === 'error' && msg.note) patch.last_error = msg.note
      mergeSession(patch)
    } else if (msg.type === 'sent') {
      lastSendInfo.value = `已发送 ${msg.size} 字节`
    } else if (msg.type === 'cleared') {
      entries.value = []
    } else if (msg.type === 'error') {
      message.error(msg.message)
    }
  }

  ws.onclose = (event) => {
    ws = null
    if (stopWs) return
    if (event.code === 4404) {
      wsState.value = 'gone'
      message.error('该会话已不存在，请刷新列表')
      return
    }
    wsState.value = 'closed'
    // 退避重连：1s、2s、4s…最多 15s
    const delay = Math.min(15000, 1000 * 2 ** wsAttempts.value)
    wsAttempts.value += 1
    wsTimer = setTimeout(() => {
      if (!stopWs && activeId.value) openWs()
    }, delay)
  }

  ws.onerror = () => {
    // onclose 会处理后续重连
  }
}

function closeWs() {
  if (wsTimer) {
    clearTimeout(wsTimer)
    wsTimer = null
  }
  if (ws) {
    const socket = ws
    ws = null
    socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null
    try {
      socket.close()
    } catch {
      /* ignore */
    }
  }
}

// ── 发送（含定时发送）──
async function sendOnce({ silent = false } = {}) {
  const session = activeSession.value
  if (!session) return
  const text = sendText.value
  if (!text.trim()) return

  const payload = { data: text, mode: sendMode.value, newline: sendNewline.value }
  if (!silent) sending.value = true
  try {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'send', ...payload }))
    } else {
      const data = await api(`/api/tcp/sessions/${session.id}/send`, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      lastSendInfo.value = `已发送 ${data.size} 字节`
    }
  } catch (err) {
    message.error(err.message)
    stopLoopSend('发送失败，定时发送已停止')
  } finally {
    if (!silent) sending.value = false
  }
}

function sendManual() {
  if (!canSend.value) {
    if (!activeSession.value) message.warning('请先选择会话')
    else if (activeSession.value.state !== 'connected') message.warning('连接未建立')
    else message.warning('发送内容为空')
    return
  }
  sendOnce()
}

// ── 定时发送 ──
function clearLoopTimer() {
  if (loopTimer) {
    clearTimeout(loopTimer)
    loopTimer = null
  }
}

/**
 * 排下一帧。用 setTimeout 链而不是 setInterval：
 * 发送慢时不会堆叠，改间隔后也能立即按新值生效。
 */
function scheduleLoopTick(delay) {
  clearLoopTimer()
  loopTimer = setTimeout(async () => {
    loopTimer = null
    if (!loopSend.value) return
    if (canSend.value) {
      await sendOnce({ silent: true })
      if (loopSend.value) loopCount.value += 1
    }
    if (loopSend.value) scheduleLoopTick(loopDelayMs.value)
  }, delay)
}

/** 开启定时发送（announce=false 用于改参数后的静默重启）*/
function startLoopSend(announce = true) {
  clearLoopTimer()
  if (!activeSession.value) {
    loopSend.value = false
    message.warning('请先选择或新建连接')
    return
  }
  if (!sendText.value.trim()) {
    loopSend.value = false
    message.warning('请先填写要发送的内容')
    return
  }
  loopCount.value = 0
  if (announce) message.info(`定时发送已开启：每 ${loopDelayMs.value} ms`)
  scheduleLoopTick(0) // 立即发第一帧，随后按间隔循环
}

/** 停止定时发送（reason 非空时给出提示）*/
function stopLoopSend(reason = '') {
  clearLoopTimer()
  if (intervalDebounce) {
    clearTimeout(intervalDebounce)
    intervalDebounce = null
  }
  loopCount.value = 0
  if (loopSend.value) {
    loopSend.value = false
    if (reason) message.warning(reason)
  }
}

/** 改间隔/单位后即时生效（按新间隔重排，不额外补发一帧）*/
function onIntervalChange() {
  if (loopSend.value) {
    scheduleLoopTick(loopDelayMs.value)
    message.info(`发送间隔已改为 ${loopDelayMs.value} ms`)
  }
}

/** 输入框连续输入时防抖，避免每敲一个字符就重排一次 */
function queueIntervalChange() {
  if (!loopSend.value) return
  if (intervalDebounce) clearTimeout(intervalDebounce)
  intervalDebounce = setTimeout(() => {
    intervalDebounce = null
    onIntervalChange()
  }, 400)
}

// ── 其它 ──
function scrollToBottom() {
  if (!autoScroll.value) return
  nextTick(() => {
    const el = logBox.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function startPolling() {
  pollTimer = setInterval(async () => {
    if (ws && ws.readyState === WebSocket.OPEN) return
    try {
      const data = await api('/api/tcp/sessions')
      sessions.value = data.sessions || []
    } catch {
      /* 静默：后端可能正在重启 */
    }
  }, 5000)
}

// 开关切换：开启时才启动；关闭只清定时器（不能反过来改 loopSend，否则会自锁）
watch(loopSend, (on) => {
  if (on) startLoopSend()
  else clearLoopTimer()
})

// 切换单位时换算数值，例如 1000 毫秒 → 1 秒
watch(loopUnit, (unit) => {
  const raw = Number(loopInterval.value)
  if (!Number.isFinite(raw) || raw <= 0) return
  loopInterval.value = unit === 's' ? Number((raw / 1000).toFixed(3)) : Math.round(raw * 1000)
})

// 间隔 / 单位变化：运行中的定时发送按新值重排
watch([loopInterval, loopUnit], () => {
  queueIntervalChange()
})

// 连接不可用（断开、会话被删）时自动停止，避免空转
watch(canSend, (ok) => {
  if (!ok && loopSend.value) stopLoopSend('连接不可用，定时发送已停止')
})

watch(autoScroll, (on) => {
  if (on) scrollToBottom()
})

loadSessions().then(() => {
  if (activeId.value) openWs()
})
startPolling()

onUnmounted(() => {
  stopWs = true
  stopLoopSend()
  closeWs()
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.tcp-client-page {
  min-height: 80vh;
  padding: 8px 12px 24px;
}

.head-card {
  margin-bottom: 10px;
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.title {
  margin: 0;
  font-size: 18px;
}

.desc {
  margin: 4px 0 0;
  font-size: 12px;
  opacity: 0.65;
}

.layout {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.col-left,
.col-right {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hint {
  font-size: 12px;
  white-space: nowrap;
}

/* ── 新建连接表单 ── */
.conn-form :deep(.n-form-item) {
  margin-bottom: 10px;
}

.conn-form :deep(.n-form-item-label) {
  font-size: 13px;
  opacity: 0.75;
}

.port-input {
  width: 96px;
  flex: 0 0 96px;
}

.switch-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.connect-btn {
  margin-top: 2px;
}

.history {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--n-border-color, rgba(128, 128, 128, 0.24));
}

.history-tag {
  cursor: pointer;
  transition: color 0.2s;
}

.history-tag:hover {
  color: #1890ff;
}

/* ── 会话卡片 ── */
.session {
  border: 1px solid var(--n-border-color, rgba(128, 128, 128, 0.24));
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: border-color 0.2s, background-color 0.2s;
}

.session:hover {
  border-color: #1890ff;
}

.session-active {
  border-color: #1890ff;
  box-shadow: 0 0 0 1px rgba(24, 144, 255, 0.35);
}

.session-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.session-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 500;
}

.session-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 12px;
  opacity: 0.65;
  margin-top: 4px;
}

.auto-on {
  color: #18a058;
}

.session-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

/* ── 收发日志 ── */
/* 面板标题：名称 + 副标题（窄屏堆叠，超长省略而不是换行乱掉） */
.panel-head {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.panel-name {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-meta {
  font-size: 12px;
  opacity: 0.6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 工具栏按钮自动换行，不再挤成一行或溢出 */
.panel-tools {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 10px;
  justify-content: flex-end;
}

.panel-card :deep(.n-card-header) {
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-start;
}

.panel-card :deep(.n-card-header__main) {
  min-width: 0;
}

.panel-card :deep(.n-card-header__extra) {
  margin-left: auto;
}

.log-box {
  height: 52vh;
  min-height: 260px;
  overflow: auto;
  padding: 6px 8px;
  border-radius: 6px;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12.5px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  background: rgba(128, 128, 128, 0.08);
}

.entry {
  display: grid;
  grid-template-columns: max-content max-content max-content minmax(0, 1fr) max-content;
  column-gap: 8px;
  padding: 1px 0;
}

.entry-lift {
  opacity: 0.3;
  transition: opacity 0.15s;
  white-space: nowrap;
}

.entry:hover .entry-lift {
  opacity: 1;
}

.entry-ts {
  opacity: 0.55;
}

.entry-dir {
  white-space: nowrap;
}

.entry-size {
  text-align: right;
  opacity: 0.55;
}

/* 固定列（时间/方向/长度）始终单行显示，只有内容列换行 */
.entry-ts,
.entry-dir,
.entry-size {
  white-space: nowrap;
}

.entry-body {
  min-width: 0;
  white-space: pre-wrap;
}

.entry-tx .entry-dir {
  color: #18a058;
}

.entry-rx .entry-dir {
  color: #2080f0;
}

.entry-sys .entry-dir,
.entry-sys .entry-body {
  color: #f0a020;
}

.entry-hex {
  color: #d03050;
  margin-left: 6px;
}

.entry-note {
  margin-left: 6px;
  opacity: 0.6;
}

.send-box {
  margin-top: 10px;
}

.loop-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.loop-input {
  width: 104px;
}

.loop-unit {
  width: 84px;
}

/* 窄屏堆叠 */
@media (max-width: 992px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .log-box {
    height: 42vh;
  }
}

/* 移动端：标题与工具栏各占一行，工具栏左对齐换行 */
@media (max-width: 640px) {
  .panel-card :deep(.n-card-header) {
    flex-direction: column;
    align-items: stretch;
  }

  .panel-card :deep(.n-card-header__extra) {
    margin-left: 0;
    width: 100%;
  }

  .panel-tools {
    justify-content: flex-start;
    gap: 6px 8px;
  }

  .entry {
    grid-template-columns: max-content max-content minmax(0, 1fr);
    column-gap: 6px;
  }

  .entry-size,
  .entry-lift {
    display: none;
  }

  .log-box {
    font-size: 12px;
  }
}
</style>
