<template>
  <div class="setting-page">
    <UpdateNotification />
    <n-card size="small" title="系统设置" :bordered="false">
      <template #header-extra>
        <n-space align="center">
          <n-text depth="3" style="font-size:12px;">v{{ currentVersion }}</n-text>
          <n-button size="small" @click="handleCheckUpdate" :loading="checkingUpdate" secondary>
            {{ checkingUpdate ? '检查中...' : '检查更新' }}
          </n-button>
          <n-button size="small" @click="reloadConfig" :loading="loading" secondary>重新加载</n-button>
          <n-tooltip v-if="!isLocalhost" trigger="hover">
            <template #trigger><n-button size="small" type="primary" disabled>保存全部</n-button></template>
            非本机不可修改配置
          </n-tooltip>
          <n-button v-else size="small" @click="saveAllConfig" type="primary" :loading="saving">保存全部</n-button>
        </n-space>
      </template>

      <n-collapse :default-expanded-names="defaultExpanded">
        <n-collapse-item v-for="group in configGroups" :key="group.name" :name="group.name">
          <template #header>
            <span class="section-title">{{ SECTION_LABELS[group.name] || group.name || '全局' }}</span>
            <span class="section-count">{{ group.fields.length }} 项</span>
          </template>
          <n-form label-placement="top" size="small" :model="editData">
            <div v-for="field in group.fields" :key="field.key" class="field-block">
              <div class="field-row">
                <div class="field-left">
                  <div class="field-label">{{ metaOf(field.key).label }}</div>
                  <div class="field-key">{{ field.key }}</div>
                </div>
                <div class="field-right">
                  <div class="field-desc" v-if="metaOf(field.key).desc">{{ metaOf(field.key).desc }}</div>
                  <div class="field-hint" v-if="metaOf(field.key).hint">{{ metaOf(field.key).hint }}</div>
                </div>
              </div>

              <!-- 布尔 -->
              <n-switch v-if="field.type === 'bool'" v-model:value="editData[field.key]" size="small" :disabled="!isLocalhost">
                <template #checked>on</template>
                <template #unchecked>off</template>
              </n-switch>

              <!-- 整数 -->
              <n-input-number v-else-if="field.type === 'int'" v-model:value="editData[field.key]" size="small" style="width:100%" :disabled="!isLocalhost" />

              <!-- 浮点数 -->
              <n-input-number v-else-if="field.type === 'float'" v-model:value="editData[field.key]" size="small" :step="0.1" style="width:100%" :disabled="!isLocalhost" />

              <!-- 列表 -->
              <div v-else-if="field.type === 'list'" class="list-editor">
                <div v-for="(item, idx) in editData[field.key]" :key="idx" class="list-row">
                  <n-input v-if="field.itemType === 'str'" v-model:value="editData[field.key][idx]" size="small" style="flex:1" :disabled="!isLocalhost" />
                  <n-input-number v-else-if="field.itemType === 'number'" v-model:value="editData[field.key][idx]" size="small" style="flex:1" :disabled="!isLocalhost" />
                  <n-input v-else v-model:value="editData[field.key][idx]" size="small" style="flex:1" :disabled="!isLocalhost" />
                  <n-button v-if="isLocalhost" size="tiny" circle secondary @click="removeListItem(field.key, idx)" :disabled="editData[field.key].length <= 1">
                    <template #icon><n-icon><RemoveOutline /></n-icon></template>
                  </n-button>
                </div>
                <n-button v-if="isLocalhost" size="tiny" dashed @click="addListItem(field.key, field.itemType)">
                  <template #icon><n-icon><AddOutline /></n-icon></template>
                  添加
                </n-button>
              </div>

              <!-- 字符串 -->
              <n-input v-else-if="field.type === 'str'" v-model:value="editData[field.key]" size="small" :disabled="!isLocalhost" />

              <!-- 对象 / 其他 → JSON textarea -->
              <n-input v-else v-model:value="editData[field.key]" type="textarea" size="small" :autosize="{ minRows: 2, maxRows: 4 }" style="font-family: monospace;" :disabled="!isLocalhost" />
            </div>
          </n-form>
        </n-collapse-item>
      </n-collapse>

      <n-alert type="info" size="small" style="margin-top:16px">修改需重启服务后生效</n-alert>

      <n-divider style="margin-top:20px" />
      <div class="bg-section">
        <div class="bg-label">自定义背景</div>
        <div class="bg-body">
          <div class="bg-left">
            <div class="bg-preview-wrap" v-if="bgPreview || hasCustomBg">
              <img :src="bgPreview || bgCurrentUrl" class="bg-preview" />
              <span class="bg-status" :class="{ 'is-new': bgPreview }">{{ bgPreview ? '待保存' : '已应用' }}</span>
            </div>
            <n-space align="center">
              <n-button size="small" secondary @click="triggerFileInput">
                {{ hasCustomBg ? '更换图片' : '选择图片' }}
              </n-button>
              <input ref="fileInputRef" type="file" accept="image/*" style="display:none" @change="onBgFileChange" />
              <span v-if="!bgPreview && !hasCustomBg" class="bg-hint">未设置</span>
            </n-space>
            <n-space v-if="bgPreview || hasCustomBg" size="small">
              <n-button v-if="bgHasChanges()" size="small" @click="saveBg" type="primary" :loading="bgSaving">保存</n-button>
              <n-button v-if="hasCustomBg" size="small" @click="resetBg" secondary>恢复默认</n-button>
            </n-space>
          </div>
          <div class="bg-right" v-if="bgPreview || hasCustomBg">
            <div class="slider-row">
              <span class="slider-label">前景透明度</span>
              <n-slider v-model:value="bgBodyOpacity" :min="0.5" :max="1" :step="0.05" class="slider-flex" @update:value="onBgSettingChange" />
              <span class="slider-val">{{ Math.round(bgBodyOpacity * 100) }}%</span>
            </div>
            <div class="slider-row">
              <span class="slider-label">滤镜效果</span>
              <n-select v-model:value="bgFilter" :options="filterOptions" size="small" style="width:85px;flex-shrink:0" @update:value="onBgSettingChange" />
              <template v-if="bgFilter !== 'none'">
                <n-slider v-model:value="bgFilterStrength" :min="filterStrengthMin" :max="filterStrengthMax" :step="filterStrengthStep" class="slider-flex" @update:value="onBgSettingChange" />
                <span class="slider-val">{{ Math.round(bgFilterStrength) }}{{ filterStrengthUnit }}</span>
              </template>
            </div>
          </div>
        </div>
      </div>

      <n-divider />
      <div class="accent-section">
        <span class="bg-label">强调色</span>
        <n-space align="center" size="small">
          <button
            v-for="c in accentPresets" :key="c"
            class="accent-swatch"
            :class="{ active: accentColor === c }"
            :style="{ background: c }"
            @click="onAccentPick(c)"
          />
          <div style="width:200px"> <n-color-picker
            :value="accentColor || undefined"
            @update:value="onAccentChange"
            size="small"
          /></div>
         
          <n-button v-if="accentColor !== accentSaved" size="small" type="primary" @click="saveAccent">保存</n-button>
          <n-button v-if="accentColor" size="small" secondary @click="resetAccent">重置</n-button>
        </n-space>
      </div>
    </n-card>

    <!-- 确认变更模态框 -->
    <n-modal v-model:show="showChangesModal" preset="card" title="确认保存" style="max-width:520px">
      <n-descriptions label-placement="left" :column="1" size="small" class="diff-desc">
        <n-descriptions-item v-for="change in changesData" :key="change.key" :label="metaOf(change.key).label || change.key">
          <span class="old-val">{{ formatValue(change.old) }}</span>
          <n-icon size="14" name="arrow-right" />
          <span class="new-val">{{ formatValue(change.new) }}</span>
        </n-descriptions-item>
      </n-descriptions>
      <template #footer>
        <n-space justify="end">
          <n-button size="small" @click="cancelSave">取消</n-button>
          <n-button size="small" @click="confirmSave" type="primary">确认</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { AddOutline, RemoveOutline } from '@vicons/ionicons5'
import {
  NAlert, NButton, NCard, NCollapse, NCollapseItem, NColorPicker,
  NDescriptions, NDescriptionsItem, NDivider, NForm,
  NIcon,
  NInput, NInputNumber, NModal, NSelect, NSlider, NSpace, NSwitch, NText, NTooltip,
  useMessage
} from 'naive-ui'
import { computed, onMounted, reactive, ref } from 'vue'
import { applyBodyBg, resetBodyBg } from '../composables/bg'
import { useAccentColor } from '../composables/theme'
import UpdateNotification from '../components/UpdateNotification.vue'
import { useUpdate } from '../composables/useUpdate'

const { currentVersion, checkForUpdates } = useUpdate()

const checkingUpdate = ref(false)

async function handleCheckUpdate() {
  checkingUpdate.value = true
  try {
    await checkForUpdates()
  } finally {
    checkingUpdate.value = false
  }
}

const { accentColor, setAccent, resetAccent: resetAccentColor } = useAccentColor()
const accentSaved = ref('')

const accentPresets = [
  '#18a058', '#2080f0', '#e04040', '#f0a020', '#8b5cf6',
  '#ec4899', '#14b8a6', '#6366f1', '#d946ef', '#0ea5e9',
]

const isCustomAccent = computed(() => accentColor.value && !accentPresets.includes(accentColor.value))

function onAccentPick(v) { setAccent(v) }
function onAccentChange(v) { setAccent(v) }
function resetAccent() { resetAccentColor() }

async function saveAccent() {
  try {
    await fetch('/api/util/background/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accent_color: accentColor.value }),
    })
    accentSaved.value = accentColor.value
    message.success('强调色已保存')
  } catch { message.error('保存失败') }
}

const message = useMessage()

const loading = ref(false)
const saving = ref(false)
const showChangesModal = ref(false)
const changesData = ref([])
const editData = reactive({})
const originalData = ref({})
const defaultExpanded = ref([])

// ── 本机检测 ──
const isLocalhost = ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname)

// ── 自定义背景 ──
const bgPreview = ref('')
const bgFile = ref(null)
const fileInputRef = ref(null)
const hasCustomBg = ref(localStorage.getItem('has_custom_bg') === '1')
const bgCurrentUrl = '/api/util/background?' + Date.now()
const bgBodyOpacity = ref(1)
const bgFilter = ref('none')
const bgFilterStrength = ref(0)
const bgSaving = ref(false)
const bgSettingsSaved = ref({ body_opacity: 1, filter: 'none', strength: 0 })

const FILTER_META = {
  blur:        { min: 1,  max: 20, step: 1, unit: 'px' },
  grayscale:   { min: 10, max: 100, step: 5, unit: '%' },
  sepia:       { min: 10, max: 100, step: 5, unit: '%' },
  brightness:  { min: 10, max: 100, step: 5, unit: '%' },
  contrast:    { min: 50, max: 200, step: 5, unit: '%' },
  saturate:    { min: 0,  max: 100, step: 5, unit: '%' },
}

const filterStrengthMin = computed(() => FILTER_META[bgFilter.value]?.min ?? 0)
const filterStrengthMax = computed(() => FILTER_META[bgFilter.value]?.max ?? 100)
const filterStrengthStep = computed(() => FILTER_META[bgFilter.value]?.step ?? 5)
const filterStrengthUnit = computed(() => FILTER_META[bgFilter.value]?.unit ?? '%')

function bgHasChanges() {
  return bgPreview.value
    || bgBodyOpacity.value !== bgSettingsSaved.value.body_opacity
    || bgFilter.value !== bgSettingsSaved.value.filter
    || bgFilterStrength.value !== bgSettingsSaved.value.strength
    || accentColor.value !== accentSaved.value
}

function triggerFileInput() { fileInputRef.value?.click() }

const filterOptions = [
  { label: '无', value: 'none' },
  { label: '模糊', value: 'blur' },
  { label: '灰度', value: 'grayscale' },
  { label: '复古', value: 'sepia' },
  { label: '暗调', value: 'brightness' },
  { label: '高对比', value: 'contrast' },
  { label: '饱和', value: 'saturate' },
]

function onBgSettingChange() {
  if (hasCustomBg.value) applyBodyBg({ body_opacity: bgBodyOpacity.value, filter: bgFilter.value, strength: bgFilterStrength.value })
}

function onBgFileChange(e) {
  const file = e.target.files?.[0]
  if (!file) return
  bgFile.value = file
  const reader = new FileReader()
  reader.onload = () => { bgPreview.value = reader.result }
  reader.readAsDataURL(file)
}

async function saveBg() {
  bgSaving.value = true
  try {
    // 有新图片则上传
    if (bgFile.value) {
      const form = new FormData()
      form.append('file', bgFile.value)
      const res = await fetch('/api/util/background', { method: 'POST', body: form })
      if (!res.ok) { message.error('上传失败'); return }
      bgFile.value = null
    }
    // 保存设置
    await fetch('/api/util/background/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body_opacity: bgBodyOpacity.value, filter: bgFilter.value, strength: bgFilterStrength.value, accent_color: accentColor.value }),
    })
    localStorage.setItem('has_custom_bg', '1')
    hasCustomBg.value = true
    bgPreview.value = ''
    bgFile.value = null
    bgSettingsSaved.value = { body_opacity: bgBodyOpacity.value, filter: bgFilter.value, strength: bgFilterStrength.value }
    accentSaved.value = accentColor.value
    applyBodyBg({ body_opacity: bgBodyOpacity.value, filter: bgFilter.value, strength: bgFilterStrength.value })
    message.success('背景已保存')
  } catch (e) {
    message.error('保存失败: ' + e.message)
  } finally {
    bgSaving.value = false
  }
}

async function resetBg() {
  try {
    await fetch('/api/util/background', { method: 'DELETE' })
    resetBodyBg()
    hasCustomBg.value = false
    bgPreview.value = ''
    bgFile.value = null
    bgBodyOpacity.value = 1
    bgFilter.value = 'none'
    bgFilterStrength.value = 0
    bgSettingsSaved.value = { body_opacity: 1, filter: 'none', strength: 0 }
    message.success('已恢复默认背景')
  } catch (e) {
    message.error('操作失败')
  }
}

// ── 字段元数据 ──────────────────────────────────────────────
const FIELD_META = {
  'fake':                { label: '测试模式',       desc: '启用后使用内置模拟数据，不连接真实 RCMS 系统' },
  'log_level':           { label: '日志级别',       desc: 'Python logging 输出等级', hint: 'DEBUG / INFO / WARNING / ERROR' },
  'zmq_auto':            { label: 'ZeroMQ 自动启停', desc: '有 WebSocket 连接时自动启动 ZeroMQ 推送，无连接超时后自动停止' },
  'zmq_auto_kill_timedelta': { label: '自动停止延迟', desc: '所有 WebSocket 断开后等待此分钟数，再终止 ZeroMQ 进程' },
  'test':                { label: '测试标记',       desc: '供开发调试使用的开关，部分接口返回 mock 数据' },

  'rcms.host':           { label: 'RCMS Web 地址',  desc: 'RCS2000 管理后台地址，用于 Web 登录与页面操作', hint: 'http(s)://host:port' },
  'rcms.rcms_rest_api':  { label: 'RCMS REST API',  desc: 'RCMS 数据接口，获取地图/设备/告警等数据', hint: 'http(s)://host:port' },
  'rcms.wcs_rest_api':   { label: 'WCS REST API',   desc: '仓储控制系统 (WCS) 接口地址', hint: 'http(s)://host:port' },
  'rcms.wcs_log_base':   { label: 'WCS 日志服务',    desc: 'WCS 日志查询服务地址，用于远程日志解析', hint: 'http(s)://host:port' },
  'rcms.map_code':       { label: '地图代码',        desc: '默认地图短码，如 DD / AA' },
  'rcms.hash':           { label: '密码哈希算法',     desc: '登录 RCMS 时密码所使用的哈希方式', hint: 'md5 / sha256' },
  'rcms.username':       { label: 'RCMS 用户名',     desc: '登录 RCMS 系统的账号' },
  'rcms.password':       { label: 'RCMS 密码',       desc: '登录 RCMS 系统的密码，非本机访问时隐藏' },

  'redis.host':          { label: 'Redis 地址',      desc: 'Redis 服务器 IP 或主机名' },
  'redis.port':          { label: 'Redis 端口',      desc: 'Redis 服务器端口号', hint: '1-65535' },
  'redis.db':            { label: 'Redis 数据库',    desc: 'Redis 逻辑数据库编号', hint: '0-15' },

  'web.host':            { label: '监听地址',         desc: 'uvicorn 绑定的 IP 地址', hint: '0.0.0.0 所有网卡 / 127.0.0.1 仅本机' },
  'web.port':            { label: 'Web 端口',         desc: 'FastAPI 服务端口', hint: '1-65535' },
  'web.workers':         { label: '工作进程数',       desc: 'uvicorn worker 数量', hint: '建议 1-4' },

  'agv.usernames':       { label: 'AGV SSH 用户名',   desc: 'SSH 连接 AGV 小车时依次尝试的用户名列表' },
  'agv.passwords':       { label: 'AGV SSH 密码',     desc: 'SSH 连接 AGV 小车时依次尝试的密码列表，非本机隐藏' },

  'webshell.enabled':        { label: '启用 Web Shell',     desc: '关闭后隐藏前端菜单并拒绝所有连接' },
  'webshell.allowed_hosts':  { label: '允许访问的 IP',       desc: 'Web Shell 访问白名单' },
  'webshell.max_sessions':   { label: '最大并发会话',        desc: '同一时间允许的最大 Web Shell 会话数' },
  'webshell.buffer_size_kb': { label: '缓冲区大小(KB)',       desc: '终端输出历史缓冲区，刷新页面时回放' },
  'webshell.disconnect_timeout': { label: '断连超时(秒)',     desc: '断开后保留进程的时间，期间刷新页面可恢复' },
  'webshell.cols':           { label: '终端列宽',            desc: '默认 PTY 列数' },
  'webshell.rows':           { label: '终端行高',            desc: '默认 PTY 行数' },

  'chat.expire_days':    { label: '消息保留天数',     desc: '聊天记录在 Redis 中的 TTL 天数' },

  'update.update_url':  { label: '更新服务器地址',   desc: 'AGVmon 更新服务器 URL', hint: 'http(s)://host:port' },
  'update.channel':     { label: '更新通道',         desc: 'stable 正式版 / beta 测试版', hint: 'stable / beta' },
  'update.auto_check':  { label: '自动检查更新',     desc: '启动时自动检查是否有新版本' },
  'update.check_interval_hours': { label: '检查间隔(小时)', desc: '自动检查更新的时间间隔' },
}

const SECTION_LABELS = {
  '':       '全局',
  'rcms':   'RCMS 连接',
  'redis':  'Redis',
  'web':    'Web 服务',
  'agv':    'AGV SSH',
  'webshell': 'Web Shell',
  'chat':   '聊天',
  'update': '更新',
}

function metaOf(key) {
  return FIELD_META[key] || { label: key, desc: '', hint: '' }
}

// ── 扁平化 ──
function flattenConfig(obj, prefix = '') {
  const result = {}
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${k}` : k
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      Object.assign(result, flattenConfig(v, full))
    } else {
      result[full] = v
    }
  }
  return result
}

// ── 类型 ──
function inferType(v) {
  if (typeof v === 'boolean') return 'bool'
  if (typeof v === 'number') return Number.isInteger(v) ? 'int' : 'float'
  if (typeof v === 'string') return 'str'
  if (Array.isArray(v)) return 'list'
  return 'object'
}

function inferItemType(arr) {
  if (!arr || !arr.length) return 'str'
  const t = typeof arr[0]
  if (t === 'boolean') return 'bool'
  if (t === 'number') return 'number'
  if (t === 'string') return 'str'
  return 'object'
}

// ── 分组 ──
const configGroups = computed(() => {
  const map = {}
  const order = []
  for (const key of Object.keys(editData).sort()) {
    const sec = key.includes('.') ? key.split('.')[0] : ''
    if (!map[sec]) { map[sec] = []; order.push(sec) }
    const val = editData[key]
    const type = inferType(val)
    const field = { key, type }
    if (type === 'list') field.itemType = inferItemType(val)
    map[sec].push(field)
  }
  return order.map(name => ({ name, fields: map[name] }))
})

// ── 列表操作 ──
function addListItem(key, itemType) {
  if (!Array.isArray(editData[key])) editData[key] = []
  const defaults = { str: '', number: 0, bool: false, object: '' }
  editData[key].push(defaults[itemType] ?? '')
}

function removeListItem(key, idx) {
  if (Array.isArray(editData[key]) && editData[key].length > 1) {
    editData[key].splice(idx, 1)
  }
}

// ── 加载 ──
async function loadConfig() {
  loading.value = true
  try {
    const res = await fetch('/api/rcms/get_config')
    const data = await res.json()
    if (data.message === 'success') {
      const flat = flattenConfig(data.data)
      for (const k of Object.keys(editData)) delete editData[k]
      Object.assign(editData, flat)
      originalData.value = JSON.parse(JSON.stringify(flat))
      defaultExpanded.value = Object.keys(flat).length <= 12
        ? [...new Set(Object.keys(flat).map(k => k.includes('.') ? k.split('.')[0] : ''))]
        : ['']
    } else {
      message.error('加载配置失败')
    }
  } catch (e) {
    message.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function reloadConfig() { loadConfig().then(() => message.success('已重新加载')) }

// ── 保存 ──
function saveAllConfig() {
  const changes = getChanges()
  if (!changes.length) { message.warning('没有修改'); return }
  changesData.value = changes
  showChangesModal.value = true
}

async function confirmSave() {
  showChangesModal.value = false
  saving.value = true
  try {
    const payload = {}
    for (const c of getChanges()) payload[c.key] = c.new
    const res = await fetch('/api/rcms/update_config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const r = await res.json()
    if (r.message === 'success') {
      message.success('已保存')
      originalData.value = JSON.parse(JSON.stringify(editData))
    } else {
      message.error('保存失败: ' + (r.errors?.[0] || ''))
    }
  } catch (e) {
    message.error('保存失败: ' + e.message)
  } finally {
    saving.value = false
  }
}

function cancelSave() { showChangesModal.value = false }

// ── 变更 ──
function getChanges() {
  const changes = []
  const orig = originalData.value
  for (const k of Object.keys(editData)) {
    if (JSON.stringify(orig[k]) !== JSON.stringify(editData[k])) {
      changes.push({ key: k, old: orig[k], new: editData[k] })
    }
  }
  return changes
}

function formatValue(v) {
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (v === null || v === undefined) return '-'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

onMounted(async () => {
  loadConfig()
  if (hasCustomBg.value) {
    const s = await applyBodyBg()
    if (s) {
      bgBodyOpacity.value = s.body_opacity ?? 1
      bgFilter.value = s.filter ?? 'none'
      bgFilterStrength.value = s.strength ?? s.blur ?? 0
      bgSettingsSaved.value = { body_opacity: bgBodyOpacity.value, filter: bgFilter.value, strength: bgFilterStrength.value }
    }
  }
  accentSaved.value = accentColor.value
})
</script>

<style scoped>
.setting-page {
  max-width: 860px;
  margin: 24px auto;
  padding: 0 16px;
}
.section-title {
  font-weight: 600;
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.section-count {
  margin-left: 12px;
  font-size: 12px;
  color: var(--n-text-color-3);
}
.field-block {
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--n-border-color);
}
.field-block:last-child {
  border-bottom: none;
}
.field-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
  margin-bottom: 6px;
}
.field-left {
  flex-shrink: 0;
}
.field-label {
  font-size: 13px;
  font-weight: 600;
}
.field-key {
  font-size: 11px;
  font-family: monospace;
  color: var(--n-text-color-3);
  margin-top: 1px;
}
.field-right {
  text-align: right;
  min-width: 0;
}
.field-desc {
  font-size: 12px;
  color: var(--n-text-color-2);
  line-height: 1.5;
}
.field-hint {
  font-size: 11px;
  color: var(--n-text-color-3);
  font-family: monospace;
  margin-top: 2px;
}
.list-editor {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.list-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.diff-desc .old-val {
  color: var(--n-text-color-3);
  text-decoration: line-through;
  word-break: break-all;
}
.diff-desc .new-val {
  color: #18a058;
  font-weight: 600;
  word-break: break-all;
}
.bg-section {
  padding: 4px 0;
}
.bg-label {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 10px;
}
.bg-body {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}
.bg-left {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex-shrink: 0;
}
.bg-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.bg-preview-wrap {
  position: relative;
  display: inline-block;
}
.bg-preview {
  width: 220px;
  height: 110px;
  border-radius: 6px;
  border: 1px solid var(--n-border-color);
  object-fit: cover;
  display: block;
}
.bg-status {
  position: absolute;
  top: 6px;
  right: 6px;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 3px;
  background: rgba(0,0,0,.5);
  color: #fff;
}
.bg-status.is-new {
  background: #18a058;
}
.bg-hint {
  font-size: 12px;
  color: var(--n-text-color-3);
}
.slider-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.slider-label {
  font-size: 12px;
  color: var(--n-text-color-3);
  width: 60px;
  flex-shrink: 0;
}
.accent-section {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
}
.accent-label {
  font-size: 13px;
  font-weight: 600;
}
.accent-hex {
  font-size: 12px;
  font-family: monospace;
  color: var(--n-text-color-2);
  background: var(--n-color-embedded);
  padding: 2px 6px;
  border-radius: 3px;
}
.accent-swatch {
  width: 22px;
  height: 22px;
  border-radius: 4px;
  border: 1px solid var(--n-border-color);
  cursor: pointer;
  transition: transform .15s, border-color .15s;
}
.accent-swatch:hover { transform: scale(1.1); }
.accent-swatch.active { border-color: var(--n-text-color); border-width: 2px; }
.accent-reset {
  position: relative;
  background: var(--n-color-embedded) !important;
}
.accent-reset::after {
  content: '';
  position: absolute;
  inset: 2px;
  border-radius: 2px;
  background: conic-gradient(#18a058 0deg 90deg, #2080f0 90deg 180deg, #f0a020 180deg 270deg, #e04040 270deg 360deg);
}
.slider-flex {
  flex: 1;
  min-width: 0;
}
.slider-val {
  font-size: 12px;
  font-family: monospace;
  color: var(--n-text-color-2);
  width: 40px;
  text-align: right;
  flex-shrink: 0;
}
.diff-desc .n-icon {
  margin: 0 6px;
  flex-shrink: 0;
}
</style>
