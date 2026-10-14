<template>
  <div class="setting-page">

    <!-- ── 客户端设置 ── -->
    <n-card size="small" title="客户端设置" :bordered="false">
      <div class="local-grid">
        <div class="local-item">
          <div class="local-info">
            <span class="local-label">主题</span>
            <span class="local-desc">深色 / 浅色主题</span>
          </div>
          <n-switch v-model:value="darkMode" @update:value="saveDarkMode" size="small">
            <template #checked>暗色</template>
            <template #unchecked>亮色</template>
          </n-switch>
        </div>
        <div class="local-item">
          <div class="local-info">
            <span class="local-label">背景图片</span>
            <span class="local-desc">关闭不影响其他客户端</span>
          </div>
          <n-switch v-model:value="hasCustomBg" size="small" />
        </div>
      </div>
    </n-card>

    <!-- ── 外观设置 ── -->
    <n-card size="small" title="外观设置" :bordered="false" style="margin-top:16px">
      <div class="bg-section">
        <div class="section-header">
          <span class="bg-label">自定义背景</span>
        </div>
        <div class="bg-body">
          <div class="bg-left">
            <div class="bg-preview-wrap" v-if="bgPreview || bgExists">
              <img :src="bgPreview || bgCurrentUrl" class="bg-preview" />
              <span class="bg-status" :class="{ 'is-new': bgPreview }">{{ bgPreview ? '待保存' : '已应用' }}</span>
            </div>
            <span v-if="!bgPreview && !bgExists" class="bg-hint">未设置</span>
            <n-button size="small" secondary @click="triggerFileInput">
              {{ bgExists ? '更换图片' : '选择图片' }}
            </n-button>
            <input ref="fileInputRef" type="file" accept="image/*" style="display:none" @change="onBgFileChange" />
          </div>
          <div class="bg-right" v-if="bgPreview || bgExists">
            <div class="slider-row">
              <span class="slider-label">前景透明度</span>
              <n-slider v-model:value="bgBodyOpacity" :min="0.5" :max="1" :step="0.05" class="slider-flex"
                @update:value="onBgSettingChange" />
              <span class="slider-val">{{ Math.round(bgBodyOpacity * 100) }}%</span>
            </div>
            <div class="slider-row">
              <span class="slider-label">滤镜效果</span>
              <n-select v-model:value="bgFilter" :options="filterOptions" size="small" style="width:85px;flex-shrink:0"
                @update:value="onBgSettingChange" />
              <template v-if="bgFilter !== 'none'">
                <n-slider v-model:value="bgFilterStrength" :min="filterStrengthMin" :max="filterStrengthMax"
                  :step="filterStrengthStep" class="slider-flex" @update:value="onBgSettingChange" />
                <span class="slider-val">{{ Math.round(bgFilterStrength) }}{{ filterStrengthUnit }}</span>
              </template>
            </div>
            <div class="bg-actions">
              <n-button v-if="bgExists" size="small" @click="resetBg" secondary>恢复默认</n-button>
              <n-button v-show="bgHasChanges()" size="small" @click="saveBg" type="primary"
                :loading="bgSaving">保存</n-button>
            </div>
          </div>
        </div>
      </div>

      <n-divider />
      <div class="accent-section">
        <div class="section-header">
          <span class="bg-label">强调色</span>
        </div>
        <n-space align="center" size="small" style="margin-top:8px">
          <button v-for="c in accentPresets" :key="c" class="accent-swatch" :class="{ active: accentColor === c }"
            :style="{ background: c }" @click="onAccentPick(c)" />
          <div style="width:200px"> <n-color-picker :value="accentColor || undefined" @update:value="onAccentChange"
              size="small" /></div>

          <n-button v-if="accentColor !== accentSaved" size="small" type="primary" @click="saveAccent">保存</n-button>
          <n-button v-if="accentColor" size="small" secondary @click="resetAccent">重置</n-button>
        </n-space>
      </div>
    </n-card>

    <!-- ── 系统设置 ── -->
    <n-card size="small" title="系统设置" :bordered="false" style="margin-top:16px">
      <UpdateNotification />
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
              <n-switch v-if="field.type === 'bool'" v-model:value="editData[field.key]" size="small"
                :disabled="!isLocalhost">
                <template #checked>on</template>
                <template #unchecked>off</template>
              </n-switch>

              <!-- 整数 -->
              <n-input-number v-else-if="field.type === 'int'" v-model:value="editData[field.key]" size="small"
                style="width:100%" :disabled="!isLocalhost" />

              <!-- 浮点数 -->
              <n-input-number v-else-if="field.type === 'float'" v-model:value="editData[field.key]" size="small"
                :step="0.1" style="width:100%" :disabled="!isLocalhost" />

              <!-- 列表 -->
              <div v-else-if="field.type === 'list'" class="list-editor">
                <div v-for="(item, idx) in editData[field.key]" :key="idx" class="list-row">
                  <n-input v-if="field.itemType === 'str'" v-model:value="editData[field.key][idx]" size="small"
                    style="flex:1" :disabled="!isLocalhost" />
                  <n-input-number v-else-if="field.itemType === 'number'" v-model:value="editData[field.key][idx]"
                    size="small" style="flex:1" :disabled="!isLocalhost" />
                  <n-input v-else v-model:value="editData[field.key][idx]" size="small" style="flex:1"
                    :disabled="!isLocalhost" />
                  <n-button v-if="isLocalhost" size="tiny" circle secondary @click="removeListItem(field.key, idx)"
                    :disabled="editData[field.key].length <= 1">
                    <template #icon><n-icon>
                        <RemoveOutline />
                      </n-icon></template>
                  </n-button>
                </div>
                <n-button v-if="isLocalhost" size="tiny" dashed @click="addListItem(field.key, field.itemType)">
                  <template #icon><n-icon>
                      <AddOutline />
                    </n-icon></template>
                  添加
                </n-button>
              </div>

              <!-- 字符串 -->
              <n-input v-else-if="field.type === 'str'" v-model:value="editData[field.key]" size="small"
                :disabled="!isLocalhost" />

              <!-- 对象 / 其他 → JSON textarea -->
              <n-input v-else v-model:value="editData[field.key]" type="textarea" size="small"
                :autosize="{ minRows: 2, maxRows: 4 }" style="font-family: monospace;" :disabled="!isLocalhost" />
            </div>
          </n-form>
        </n-collapse-item>
      </n-collapse>

      <n-alert type="info" size="small" style="margin-top:16px">修改需重启服务后生效</n-alert>
    </n-card>

    <!-- 确认变更模态框 -->
    <n-modal v-model:show="showChangesModal" preset="card" title="确认保存" style="max-width:520px">
      <n-descriptions label-placement="left" :column="1" size="small" class="diff-desc">
        <n-descriptions-item v-for="change in changesData" :key="change.key"
          :label="metaOf(change.key).label || change.key">
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
import { computed, inject, onMounted, reactive, ref, watch } from 'vue'
import UpdateNotification from '../components/UpdateNotification.vue'
import { applyBodyBg, resetBodyBg } from '../composables/bg'
import { useAccentColor } from '../composables/theme'
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

// ── 主题 ──
const darkMode = inject('darkMode', ref(localStorage.getItem('dark_mode') === 'true'))
function saveDarkMode(v) { localStorage.setItem('dark_mode', v) }

// ── 自定义背景 ──
const bgPreview = ref('')
const bgFile = ref(null)
const fileInputRef = ref(null)
const hasCustomBg = ref(localStorage.getItem('has_custom_bg') === '1')
const bgExists = ref(false)  // whether server has a custom background image
const bgCacheKey = ref(Date.now())
const bgCurrentUrl = computed(() => '/api/util/background?' + bgCacheKey.value)
function refreshBgPreview() { bgCacheKey.value = Date.now() }
const bgBodyOpacity = ref(1)
const bgFilter = ref('none')
const bgFilterStrength = ref(0)
const bgSaving = ref(false)
const bgSettingsSaved = ref({ body_opacity: 1, filter: 'none', strength: 0 })

const FILTER_META = {
  blur: { min: 1, max: 20, step: 1, unit: 'px' },
  grayscale: { min: 10, max: 100, step: 5, unit: '%' },
  sepia: { min: 10, max: 100, step: 5, unit: '%' },
  brightness: { min: 10, max: 100, step: 5, unit: '%' },
  contrast: { min: 50, max: 200, step: 5, unit: '%' },
  saturate: { min: 0, max: 100, step: 5, unit: '%' },
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
    bgExists.value = true
    bgPreview.value = ''
    bgFile.value = null
    refreshBgPreview()
    bgSettingsSaved.value = { body_opacity: bgBodyOpacity.value, filter: bgFilter.value, strength: bgFilterStrength.value }
    accentSaved.value = accentColor.value
    applyBodyBg({ body_opacity: bgBodyOpacity.value, filter: bgFilter.value, strength: bgFilterStrength.value }, { bustCache: true })
    message.success('背景已保存')
  } catch (e) {
    message.error('保存失败: ' + e.message)
  } finally {
    bgSaving.value = false
  }
}
watch(hasCustomBg, (v) => {
  localStorage.setItem('has_custom_bg', v ? '1' : '0')
  if (v) {
    applyBodyBg({ body_opacity: bgBodyOpacity.value, filter: bgFilter.value, strength: bgFilterStrength.value })
  } else {
    resetBodyBg()
  }
})
async function resetBg() {
  try {
    await fetch('/api/util/background', { method: 'DELETE' })
    // 同时重置服务器端背景设置（保留强调色）
    await fetch('/api/util/background/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body_opacity: 1, filter: 'none', strength: 0 }),
    })
    resetBodyBg()
    hasCustomBg.value = false
    bgExists.value = false
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
  'fake': { label: '测试模式', desc: '启用后使用内置模拟数据，不连接真实 RCMS 系统' },
  'log_level': { label: '日志级别', desc: 'Python logging 输出等级', hint: 'DEBUG / INFO / WARNING / ERROR' },
  'zmq_auto': { label: 'ZeroMQ 自动启停', desc: '有 WebSocket 连接时自动启动 ZeroMQ 推送，无连接超时后自动停止' },
  'zmq_auto_kill_timedelta': { label: '自动停止延迟', desc: '所有 WebSocket 断开后等待此分钟数，再终止 ZeroMQ 进程' },
  'test': { label: '测试标记', desc: '供开发调试使用的开关，部分接口返回 mock 数据' },

  'rcms.host': { label: 'RCMS Web 地址', desc: 'RCS2000 管理后台地址，用于 Web 登录与页面操作', hint: 'http(s)://host:port' },
  'rcms.rcms_rest_api': { label: 'RCMS REST API', desc: 'RCMS 数据接口，获取地图/设备/告警等数据', hint: 'http(s)://host:port' },
  'rcms.wcs_rest_api': { label: 'WCS REST API', desc: '仓储控制系统 (WCS) 接口地址', hint: 'http(s)://host:port' },
  'rcms.wcs_log_base': { label: 'WCS 日志服务', desc: 'WCS 日志查询服务地址，用于远程日志解析', hint: 'http(s)://host:port' },
  'rcms.map_code': { label: '地图代码', desc: '默认地图短码，如 DD / AA' },
  'rcms.hash': { label: '密码哈希算法', desc: '登录 RCMS 时密码所使用的哈希方式', hint: 'md5 / sha256' },
  'rcms.username': { label: 'RCMS 用户名', desc: '登录 RCMS 系统的账号' },
  'rcms.password': { label: 'RCMS 密码', desc: '登录 RCMS 系统的密码，非本机访问时隐藏' },

  'redis.host': { label: 'Redis 地址', desc: 'Redis 服务器 IP 或主机名' },
  'redis.port': { label: 'Redis 端口', desc: 'Redis 服务器端口号', hint: '1-65535' },
  'redis.db': { label: 'Redis 数据库', desc: 'Redis 逻辑数据库编号', hint: '0-15' },

  'web.host': { label: '监听地址', desc: 'uvicorn 绑定的 IP 地址', hint: '0.0.0.0 所有网卡 / 127.0.0.1 仅本机' },
  'web.port': { label: 'Web 端口', desc: 'FastAPI 服务端口', hint: '1-65535' },
  'web.workers': { label: '工作进程数', desc: 'uvicorn worker 数量，超过一个会有多进程数据不一致问题', hint: '建议 1-4' },

  'agv.usernames': { label: 'AGV SSH 用户名', desc: 'SSH 连接 AGV 小车时依次尝试的用户名列表' },
  'agv.passwords': { label: 'AGV SSH 密码', desc: 'SSH 连接 AGV 小车时依次尝试的密码列表，非本机隐藏' },

  'agvlog.parser': { label: 'AGV 日志解析器', desc: '默认Python的解析实现、跨平台, exe: 备选实现：调用原 parsezlib_2_7_8.exe' , hint: 'python / exe' },

  'webshell.enabled': { label: '启用 Web Shell', desc: '关闭后隐藏前端菜单并拒绝所有连接' },
  'webshell.allowed_hosts': { label: '允许访问的 IP', desc: 'Web Shell 访问白名单' },
  'webshell.max_sessions': { label: '最大并发会话', desc: '同一时间允许的最大 Web Shell 会话数' },
  'webshell.buffer_size_kb': { label: '缓冲区大小(KB)', desc: '终端输出历史缓冲区，刷新页面时回放' },
  'webshell.disconnect_timeout': { label: '断连超时(秒)', desc: '断开后保留进程的时间，期间刷新页面可恢复' },
  'webshell.cols': { label: '终端列宽', desc: '默认 PTY 列数' },
  'webshell.rows': { label: '终端行高', desc: '默认 PTY 行数' },

  'tcp_client.max_sessions': { label: '最大会话数', desc: '同时保留的 TCP 调试会话数上限，超出后需先删除不用的会话' },
  'tcp_client.max_log_entries': { label: '收发记录上限', desc: '每个会话保留的收发记录条数，超出后丢弃最旧的记录' },
  'tcp_client.max_preview_bytes': { label: '单条预览字节数', desc: '每条记录最多展示/解码的字节数，超出部分不显示' },
  'tcp_client.connect_timeout': { label: '连接超时(秒)', desc: '建立 TCP 连接的最长等待时间' },
  'tcp_client.reconnect_delay': { label: '重连间隔(秒)', desc: '开启自动重连后，两次重连之间的等待时间' },
  'tcp_client.allow_hosts': { label: '允许连接的主机', desc: '白名单，留空表示不限制；非空时只能连接列表内主机' },

  'user_script.enabled': { label: '启用用户脚本', desc: '关闭后用户脚本接口一律返回 403' },
  'user_script.allow_remote': { label: '允许远程调用', desc: '默认仅允许本机调用；开启后非本机调用必须携带正确的 API Key' },
  'user_script.api_key': { label: 'API Key', desc: '远程调用时校验的请求头 X-API-Key，留空表示拒绝一切远程调用' },
  'user_script.timeout_ms': { label: '执行超时(ms)', desc: '单次脚本执行的墙钟超时，超时直接终止子进程', hint: '50 - 60000' },
  'user_script.max_memory_mb': { label: '内存上限(MB)', desc: 'Lua 解释器可分配的内存硬上限', hint: '8 - 1024' },
  'user_script.max_payload_kb': { label: '请求体上限(KB)', desc: '提交脚本时请求体（含源码）的体积上限', hint: '1 - 8192' },
  'user_script.max_script_kb': { label: '脚本大小上限(KB)', desc: '单个脚本源码的体积上限', hint: '1 - 2048' },
  'user_script.max_result_kb': { label: '结果大小上限(KB)', desc: '返回结果 JSON 的体积上限', hint: '1 - 8192' },
  'user_script.max_log_lines': { label: '日志行数上限', desc: '单次执行保留的 print / console 日志行数', hint: '1 - 2000' },
  'user_script.max_concurrency': { label: '最大并发执行数', desc: '同时运行的脚本数上限，超出直接拒绝请求', hint: '1 - 32' },
  'user_script.max_depth': { label: '结果嵌套深度上限', desc: '结果 JSON 的最大嵌套层级，防止爆栈', hint: '4 - 256' },
  'user_script.max_nodes': { label: '结果节点数上限', desc: '结果 JSON 的最大节点数，防止超大表', hint: '100 - 2000000' },

  'user_script.http.enabled': { label: '启用脚本 HTTP', desc: '关闭后脚本里的 http.get / http.post 一律失败' },
  'user_script.http.allowed_hosts': { label: 'HTTP 主机白名单', desc: '留空表示不限制；支持 *.example.com 通配（不含裸域）' },
  'user_script.http.blocked_hosts': { label: 'HTTP 主机黑名单', desc: '优先级高于白名单，命中的主机一律拒绝' },
  'user_script.http.allow_private_hosts': { label: '允许访问内网地址', desc: '默认禁止内网/回环/链路本地地址（防 SSRF），访问内网接口需开启' },
  'user_script.http.timeout_ms': { label: 'HTTP 超时(ms)', desc: '单次外部 HTTP 请求超时，整体仍受执行超时约束', hint: '100 - 60000' },
  'user_script.http.max_request_kb': { label: 'HTTP 请求体上限(KB)', desc: '单次脚本 HTTP 请求体大小上限', hint: '1 - 8192' },
  'user_script.http.max_response_kb': { label: 'HTTP 响应体上限(KB)', desc: '单次脚本 HTTP 响应体大小上限', hint: '1 - 8192' },
  'user_script.http.max_requests_per_run': { label: '单次执行请求数', desc: '一次脚本执行中最多发起的 HTTP 请求数', hint: '1 - 64' },
  'user_script.http.max_redirects': { label: '最大重定向次数', desc: '跟随 HTTP 重定向的最大跳数', hint: '0 - 10' },
  'user_script.http.user_agent': { label: 'User-Agent', desc: '脚本 HTTP 请求使用的 User-Agent 头' },

  'chat.expire_days': { label: '消息保留天数', desc: '聊天记录在 Redis 中的 TTL 天数' },

  'update.update_url': { label: '更新服务器地址', desc: 'AGVmon 更新服务器 URL', hint: 'http(s)://host:port' },
  'update.channel': { label: '更新通道', desc: 'stable 正式版 / beta 测试版', hint: 'stable / beta' },
  'update.auto_check': { label: '自动检查更新', desc: '启动时自动检查是否有新版本' },
  'update.check_interval_hours': { label: '检查间隔(小时)', desc: '自动检查更新的时间间隔' },
}

const SECTION_LABELS = {
  '': '全局',
  'agvlog': 'AGV 日志解析器',
  'rcms': 'RCMS 连接',
  'redis': 'Redis 服务',
  'web': 'Web 服务',
  'agv': 'AGV SSH 登录',
  'webshell': 'Web Shell',
  'tcp_client': 'TCP 客户端',
  'user_script': '用户脚本',
  'chat': '聊天',
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

  // Always check server background (independent of local toggle)
  try {
    const res = await fetch('/api/util/background/settings')
    if (res.ok) {
      const s = await res.json()
      bgExists.value = true
      bgBodyOpacity.value = s.body_opacity ?? 1
      bgFilter.value = s.filter ?? 'none'
      bgFilterStrength.value = s.strength ?? s.blur ?? 0
      bgSettingsSaved.value = { body_opacity: bgBodyOpacity.value, filter: bgFilter.value, strength: bgFilterStrength.value }
    }
  } catch { /* no server bg */ }

  // Only apply background to body if locally enabled
  if (hasCustomBg.value) {
    applyBodyBg({ body_opacity: bgBodyOpacity.value, filter: bgFilter.value, strength: bgFilterStrength.value })
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

.bg-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
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
  background: rgba(0, 0, 0, .5);
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

/* ── 客户端设置 ── */
.local-grid {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.local-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--n-color-embedded);
}

.local-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.local-label {
  font-size: 13px;
  font-weight: 600;
}

.local-desc {
  font-size: 11px;
  color: var(--n-text-color-3);
}

/* ── 区块标题 ── */
.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.accent-section {
  display: flex;
  flex-direction: column;
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

.accent-swatch:hover {
  transform: scale(1.1);
}

.accent-swatch.active {
  border-color: var(--n-text-color);
  border-width: 2px;
}

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
