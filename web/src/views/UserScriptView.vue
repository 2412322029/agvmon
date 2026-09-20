<template>
  <div class="user-script-page">
    <!-- 顶部：说明 + 运行时状态 -->
    <n-card size="small" :bordered="false" class="head-card">
      <div class="head">
        <div class="head-main">
          <h2 class="title">
            用户脚本
            <n-tag size="tiny" :bordered="false" type="info">Lua 沙箱</n-tag>
          </h2>
          <p class="desc">
            在这里用 Lua 处理请求数据 脚本从
            <code>input</code> 拿请求体，返回值即响应。脚本以独立子进程 + 硬超时执行，
            默认只允许本机调用。
          </p>
        </div>
        <n-space align="center" size="small">
          <n-tag size="small" :bordered="false" :type="healthTag.type">{{ healthTag.label }}</n-tag>
          <n-button size="small" :loading="loading" @click="refreshAll">刷新</n-button>
        </n-space>
      </div>

      <div v-if="runtime" class="meta">
        <span>Lua {{ runtime.healthcheck?.runtime?.lua || '?' }}</span>
        <span>lupa {{ runtime.healthcheck?.runtime?.lupa || '?' }}</span>
        <span>超时 {{ runtime.config.timeout_ms }}ms</span>
        <span>内存 {{ runtime.config.max_memory_mb }}MB</span>
        <span>并发 {{ runtime.config.max_concurrency }}</span>
        <span>仅本机 {{ runtime.config.allow_remote ? '否（已开远程）' : '是' }}</span>
        <span :class="runtime.config.http?.enabled ? 'ok' : 'muted'">
          外部 API {{ runtime.config.http?.enabled ? '可用' : '已禁用' }}
          <template v-if="runtime.config.http?.enabled">
            （{{ fmtBytes((runtime.config.http?.max_response_kb || 0) * 1024) }} /
            {{ runtime.config.http?.max_requests_per_run }} 次每轮）
          </template>
        </span>
        <span class="dir" :title="runtime.storage?.db">脚本目录：{{ runtime.storage?.dir }}</span>
      </div>
    </n-card>

    <n-alert v-if="blocked" type="warning" class="blocked" closable @close="blocked = ''">
      {{ blocked }}
    </n-alert>

    <div class="layout">
      <!-- 左栏：脚本列表 -->
      <div class="col-left">
        <n-card size="small" :bordered="false">
          <template #header>
            <span>脚本（{{ filtered.length }}<template v-if="filtered.length !== scripts.length">/{{ scripts.length }}</template>）</span>
          </template>
          <template #header-extra>
            <n-button size="tiny" type="primary" @click="newScript">新建</n-button>
          </template>

          <n-input v-model:value="search" size="small" clearable placeholder="搜索 ID / 名称 / 说明"
            style="margin-bottom: 8px" />

          <n-empty v-if="!filtered.length" size="small" style="margin: 16px 0"
            :description="scripts.length ? '没有匹配的脚本' : '还没有脚本，点「新建」开始'" />

          <div v-for="s in filtered" :key="s.script_id" class="item"
            :class="{ 'item-active': s.script_id === currentId }" @click="openScript(s.script_id)">
            <div class="item-row">
              <n-tag size="tiny" :bordered="false" :type="s.enabled ? 'success' : 'default'">
                {{ s.enabled ? '启用' : '停用' }}
              </n-tag>
              <span class="item-id" :title="s.script_id">{{ s.script_id }}</span>
              <span class="item-ver">v{{ s.version }}</span>
            </div>
            <div class="item-row item-sub">
              <span class="item-name" :title="s.name || s.description">{{ s.name || '（未命名）' }}</span>
              <span v-if="s.run_count">{{ s.run_count }} 次</span>
            </div>
            <div class="item-row item-sub">
              <span>{{ s.code_lines }} 行 · {{ fmtBytes(s.code_bytes) }}</span>
              <span v-if="s.last_status" :class="s.last_status === 'ok' ? 'ok' : 'bad'">
                {{ s.last_status }}
              </span>
            </div>
          </div>
        </n-card>

        <n-card size="small" title="运行时" :bordered="false">
          <n-empty v-if="!runtime" size="small" description="未获取到运行时信息" />
          <div v-else class="runtime-box">
            <div class="rt-row">
              <span>自检</span>
              <span :class="runtime.success ? 'ok' : 'bad'">
                {{ runtime.success ? '通过' : '失败' }}
              </span>
            </div>
            <div class="rt-row">
              <span>worker 冷启动+执行</span>
              <span>{{ runtime.healthcheck?.duration_ms ?? '-' }}ms</span>
            </div>
            <div class="rt-row">
              <span>脚本上限</span>
              <span>{{ runtime.config.max_script_kb }}KB</span>
            </div>
            <div class="rt-row">
              <span>请求体上限</span>
              <span>{{ runtime.config.max_payload_kb }}KB</span>
            </div>
            <div class="rt-row">
              <span>结果上限</span>
              <span>{{ runtime.config.max_result_kb }}KB</span>
            </div>
            <div class="rt-row">
              <span>日志行数上限</span>
              <span>{{ runtime.config.max_log_lines }}</span>
            </div>
            <div class="rt-row">
              <span>外部 API</span>
              <span :class="runtime.config.http?.enabled ? 'ok' : 'bad'">
                {{ runtime.config.http?.enabled ? '允许调用' : '已禁用' }}
              </span>
            </div>
            <template v-if="runtime.config.http?.enabled">
              <div class="rt-row">
                <span>单次超时 / 每轮次数</span>
                <span>{{ runtime.config.http.timeout_ms }}ms / {{ runtime.config.http.max_requests_per_run }} 次</span>
              </div>
              <div class="rt-row">
                <span>请求 / 响应上限</span>
                <span>{{ fmtBytes((runtime.config.http.max_request_kb || 0) * 1024) }} /
                  {{ fmtBytes((runtime.config.http.max_response_kb || 0) * 1024) }}</span>
              </div>
              <div class="rt-row rt-col">
                <span>可访问主机</span>
                <code class="path">
                  {{ (runtime.config.http.allowed_hosts || []).length
                    ? runtime.config.http.allowed_hosts.join(', ')
                    : '（不限制，任意公网主机）' }}{{ runtime.config.http.allow_private_hosts ? ' · 含内网' : ' · 禁内网/回环' }}
                </code>
              </div>
            </template>
            <div class="rt-row rt-col">
              <span>脚本目录</span>
              <code class="path" :title="runtime.storage?.dir">{{ runtime.storage?.dir || '-' }}</code>
            </div>
            <n-alert v-if="runtime.healthcheck && runtime.success === false" type="error" size="small"
              style="margin-top: 6px">
              {{ runtime.healthcheck.error || '自检失败：Lua 运行时不可用' }}
            </n-alert>
          </div>
        </n-card>
      </div>

      <!-- 右栏：编辑器 / 运行 / 流水 / 说明 -->
      <div class="col-right">
        <n-card size="small" :bordered="false">
          <template #header>
            <div class="panel-head">
              <span class="panel-title">{{ currentId || '（新脚本，未保存）' }}</span>
              <n-tag v-if="dirty" size="tiny" :bordered="false" type="warning">未保存</n-tag>
              <span v-if="currentId && currentVersion" class="panel-sub">v{{ currentVersion }}</span>
            </div>
          </template>
          <template #header-extra>
            <div class="tools">
              <n-button size="small" :loading="checking" @click="checkCode">语法检查</n-button>
              <n-button size="small" type="primary" :loading="saving" @click="saveScript">保存</n-button>
              <n-button size="small" type="info" :loading="running" @click="runNow">运行</n-button>
              <n-button v-if="currentId" size="small" type="error" ghost @click="confirmDelete(currentId)">
                删除
              </n-button>
            </div>
          </template>

          <n-tabs v-model:value="tab" type="line" size="small" animated>
            <!-- ── 编辑 ── -->
            <n-tab-pane name="edit" tab="编辑">
              <div class="form-grid">
                <label class="fld">
                  <span class="fld-label">脚本 ID</span>
                  <n-input v-model:value="form.script_id" size="small" :disabled="!!currentId"
                    placeholder="字母数字与 _ . -" />
                </label>
                <label class="fld">
                  <span class="fld-label">名称</span>
                  <n-input v-model:value="form.name" size="small" placeholder="可选，显示用" />
                </label>
                <label class="fld">
                  <span class="fld-label">启用</span>
                  <n-switch v-model:value="form.enabled" size="small" />
                </label>
                <label class="fld span-2">
                  <span class="fld-label">说明</span>
                  <n-input v-model:value="form.description" size="small" placeholder="可选，一句话说明这个脚本干什么" />
                </label>
              </div>

              <LuaEditor v-model="form.code" height="52vh" placeholder="-- 在这里写 Lua" @run="runNow"
                @save="saveScript" />

              <div class="editor-foot">
                <n-text depth="3" class="hint">
                  输入时自动提示 · 鼠标悬停看 API 文档 · Ctrl+空格 手动唤起 ·
                  Ctrl+F 查找 · Ctrl+/ 注释 · Ctrl+Enter 运行 · Ctrl+S 保存 · 正文同时保存在
                  <code>lua_script/{{ form.script_id || '<id>' }}.lua</code>，直接用外部编辑器改也生效
                </n-text>
                <n-dropdown trigger="click" :options="exampleOptions" @select="fillExample">
                  <n-button size="tiny" quaternary>插入示例</n-button>
                </n-dropdown>
              </div>

              <n-alert v-if="checkResult" :type="checkResult.success ? 'success' : 'error'" size="small"
                class="check-alert" closable @close="checkResult = null">
                <template v-if="checkResult.success">
                  语法检查通过（{{ checkResult.duration_ms }}ms）
                </template>
                <template v-else>
                  语法检查未通过：{{ checkResult.error }}
                </template>
              </n-alert>
            </n-tab-pane>

            <!-- ── 运行 ── -->
            <n-tab-pane name="run" tab="运行">
              <div class="run-grid">
                <div class="run-left">
                  <div class="block-head">
                    <span>请求数据（JSON）</span>
                    <n-space size="small">
                      <n-button size="tiny" quaternary @click="fillPayloadSample">示例数据</n-button>
                      <n-button size="tiny" quaternary @click="payloadText = '{}'">清空</n-button>
                    </n-space>
                  </div>
                  <n-input v-model:value="payloadText" type="textarea" :rows="8" size="small"
                    placeholder='{"car": "AGV-07", "step": 12}' />
                  <div class="run-actions">
                    <n-checkbox v-model:checked="adhoc" size="small"
                      :disabled="!currentId"
                      title="不落库，直接执行编辑器里的代码；脚本级失败也不记入流水">
                      临时执行（不保存）
                    </n-checkbox>
                    <n-checkbox v-model:checked="saveBeforeRun" size="small" :disabled="!dirty || adhoc || !currentId">
                      先保存再运行
                    </n-checkbox>
                    <n-button size="small" type="primary" :loading="running" @click="runNow">运行</n-button>
                  </div>
                  <n-text depth="3" class="hint">
                    {{ effectiveAdhoc
                      ? '临时执行：代码不落库、不记流水，用于调试。'
                      : '执行已保存的脚本，结果与耗时记入流水。' }}
                  </n-text>
                </div>

                <div class="run-right">
                  <div class="block-head">
                    <span>执行结果</span>
                    <n-space size="small" align="center">
                      <n-tag v-if="runResult" size="tiny" :bordered="false"
                        :type="runResult.ok ? 'success' : 'error'">
                        {{ runResult.ok ? 'ok' : (runResult.error_type || 'error') }}
                      </n-tag>
                      <n-tag v-if="runResult?.http_status" size="tiny" :bordered="false" type="info">
                        HTTP {{ runResult.http_status }}
                      </n-tag>
                      <n-tag v-if="runResult" size="tiny" :bordered="false">
                        {{ runResult.duration_ms }}ms（worker {{ runResult.worker_ms ?? '-' }}ms）
                      </n-tag>
                    </n-space>
                  </div>

                  <n-empty v-if="!runResult" size="small" description="还没有执行结果" style="margin: 24px 0" />
                  <div v-else class="result-box">
                    <div v-if="runResult.ok" class="result-block">
                      <div class="block-label">返回值</div>
                      <pre class="json">{{ pretty(runResult.result) }}</pre>
                    </div>
                    <div v-else class="result-block">
                      <div class="block-label">错误</div>
                      <pre class="json error">{{ runResult.error }}</pre>
                      <details v-if="runResult.traceback" class="tb">
                        <summary>Lua 堆栈</summary>
                        <pre class="json">{{ runResult.traceback }}</pre>
                      </details>
                    </div>
                    <div class="result-block">
                      <div class="block-label">
                        日志
                        <span class="muted">{{ (runResult.logs || []).length }} 行</span>
                      </div>
                      <pre v-if="runResult.logs?.length" class="json log">{{ runResult.logs.join('\n') }}</pre>
                      <div v-else class="muted">脚本没有输出日志（print / log / console.log 都可）</div>
                    </div>
                  </div>
                </div>
              </div>
            </n-tab-pane>

            <!-- ── 流水 ── -->
            <n-tab-pane name="runs" tab="执行流水">
              <div class="block-head">
                <span>{{ currentId ? `${currentId} 的最近执行` : '选择左侧脚本查看流水' }}</span>
                <n-button size="tiny" :disabled="!currentId" :loading="loadingRuns" @click="loadRuns(currentId)">
                  刷新
                </n-button>
              </div>
              <n-empty v-if="!runs.length" size="small" description="暂无执行记录" style="margin: 24px 0" />
              <div v-else class="runs">
                <div v-for="r in runs" :key="r.id" class="run-row">
                  <span class="run-ts">{{ r.timestamp }}</span>
                  <n-tag size="tiny" :bordered="false" :type="r.ok ? 'success' : 'error'">{{ r.status }}</n-tag>
                  <span class="run-dur">{{ r.duration_ms }}ms</span>
                  <span class="run-bytes">↑{{ fmtBytes(r.payload_bytes) }} ↓{{ fmtBytes(r.result_bytes) }}</span>
                  <span class="run-src" :title="r.source">{{ r.source }}</span>
                  <span v-if="r.error" class="run-err" :title="r.error">{{ firstLine(r.error) }}</span>
                </div>
              </div>
            </n-tab-pane>

            <!-- ── 说明 ── -->
            <n-tab-pane name="help" tab="脚本约定">
              <div class="help">
                <n-alert type="info" size="small" class="help-link" :bordered="false">
                  这里只是速查要点，完整版编写指南（运行模型、JSON 坑、HTTP 策略、反模式等）见
                  <router-link to="/lua-help">Lua 帮助</router-link>。
                </n-alert>
                <p>
                  脚本被执行时拿到一个 <code>ctx</code> 参数（同时 <code>input</code> /
                  <code>output</code> 也在全局），返回值就是响应内容：
                </p>
                <pre class="json">{{ contractSample }}</pre>
                <p class="mt">沙箱里可用的东西（除此之外都是 <code>nil</code>，包括
                  <code>io</code> / <code>os.execute</code> / <code>require</code> /
                  <code>load</code> / <code>debug</code>）：</p>
                <div class="chips">
                  <n-tag v-for="name in SANDBOX_NAMES" :key="name" size="tiny" :bordered="false">{{ name }}</n-tag>
                </div>
                <p class="mt">调用外部 API（<code>http</code>，可在
                  <code>config.toml</code> 的 <code>[user_script.http]</code> 里关掉或加白名单）：</p>
                <pre class="json">{{ httpSample }}</pre>
                <ul class="pits">
                  <li>返回值是 table：<code>ok</code> / <code>status</code> / <code>headers</code> /
                    <code>body</code> / <code>json</code>（响应是 JSON 时自动解码）/ <code>error</code>。</li>
                  <li><b>传输层失败不抛错</b>：DNS 解析不了、超时、被策略拦下都是
                    <code>ok = false</code>，读 <code>error</code> 就行；HTTP 4xx/5xx 属于
                    <code>ok = true</code>，看 <code>status</code> 自己判断。</li>
                  <li><code>http.post(url, table)</code> 会自动 JSON 序列化并带
                    <code>Content-Type: application/json</code>，直接用就行。</li>
                  <li>每轮的请求次数、单次超时、响应体积都有上限；整脚本还受
                    <code>[user_script] timeout_ms</code>（当前
                    {{ runtime?.config?.timeout_ms ?? 1000 }}ms）约束，联网脚本建议把它调大。</li>
                </ul>
                <p class="mt">几个容易踩的坑：</p>
                <ul class="pits">
                  <li><b>JSON null</b> 是 <code>json.null</code> 哨兵，判断用
                    <code>v == json.null</code>；只有字段缺失才是 <code>nil</code>。</li>
                  <li>Lua 5.5 起字符串字面量里 <code>\uXXXX</code> 是语法错误，要写
                    <code>\u{4e2d}</code>；嵌 JSON 建议用长括号 <code>[==[ ]==]</code>。</li>
                  <li>死循环会被硬超时直接杀进程（当前
                    {{ runtime?.config?.timeout_ms ?? 1000 }}ms），脚本里别写无退出条件的
                    <code>while</code>。</li>
                  <li>内存超限由 Lua 分配器在 C 层强制（默认 64MB），无限递归会先撞它。</li>
                  <li>想照抄一个联网脚本，点左下角「插入示例」→
                    <b>调用外部 API → 处理 → 中转</b>，跟着注释改地址即可。</li>
                </ul>
                <div class="block-head mt">
                  <span>调用示例（curl）</span>
                  <n-button size="tiny" @click="copyCurl">复制</n-button>
                </div>
                <pre class="json">{{ curlSample }}</pre>

                <p class="mt"><b>脚本即 API 端点</b>：脚本保存后就是一个 HTTP 接口，其他服务直接调
                  <code>{{ BASE }}/&lt;脚本ID&gt;/run</code> 即可（<code>POST .../&lt;脚本ID&gt;</code> 是等价别名）。
                  三种传参姿势都支持：直接 POST 业务 JSON、只用 query（<code>?car=AGV-07</code>）、
                  以及带 <code>payload</code> 包装体的老写法。脚本侧对应拿到
                  <code>ctx.input</code>（合并后的入参）、<code>ctx.query</code>（值都是字符串）、
                  <code>ctx.body</code>（原始请求体）、<code>ctx.request</code>（method / path / ip / headers）。</p>
                <ul class="pits">
                  <li>返回值就是响应体；脚本可以用 <code>__status</code> 指定 HTTP 状态码（比如参数不对返回
                    <code>400</code>、上游挂了返回 <code>502</code>），用 <code>__headers</code> 追加响应头。
                    这两个键不会出现在响应体里。</li>
                  <li>跨机/跨服务调用需要放开闸门：<code>[user_script] allow_remote = true</code> +
                    <code>api_key</code>，调用方带请求头 <code>X-API-Key</code>（脚本看不到这个头）。</li>
                </ul>
                <div class="block-head mt">
                  <span>跨机调用示例</span>
                  <n-button size="tiny" @click="copyRemoteCurl">复制</n-button>
                </div>
                <pre class="json">{{ remoteCurlSample }}</pre>
              </div>
            </n-tab-pane>
          </n-tabs>
        </n-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
  NDropdown,
  NEmpty,
  NInput,
  NSpace,
  NSwitch,
  NTabPane,
  NTabs,
  NTag,
  NText,
  useDialog,
  useMessage,
} from 'naive-ui'
import { computed, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import LuaEditor from '../components/LuaEditor.vue'
import { DEFAULT_TEMPLATE, EXAMPLES } from '../composables/luaExamples.js'
import { completionNames } from '../composables/luaLanguage.js'

const message = useMessage()
const dialog = useDialog()

const SCRIPT_ID_RE = /^[A-Za-z0-9_.-]{1,64}$/
const BASE = '/api/user-script'

const TEMPLATE = DEFAULT_TEMPLATE

const PAYLOAD_SAMPLE = `{
  "car": "AGV-07",
  "step": 12,
  "pos": { "x": 1024, "y": 2048, "theta": 90 }
}`

// 沙箱里能用的名字（含 ctx / handle），与后端白名单同源
const SANDBOX_NAMES = completionNames()

// 插入示例的下拉项
const exampleOptions = EXAMPLES.map((e, index) => ({ label: e.name, key: String(index) }))

// ── 状态 ──
const scripts = ref([])
const runs = ref([])
const runtime = ref(null)
const search = ref('')
const tab = ref('edit')
const blocked = ref('')
const loading = ref(false)
const saving = ref(false)
const checking = ref(false)
const running = ref(false)
const loadingRuns = ref(false)
const currentId = ref('')
const currentVersion = ref(0)
const checkResult = ref(null)
const runResult = ref(null)
const payloadText = ref(PAYLOAD_SAMPLE)
const adhoc = ref(false)
const saveBeforeRun = ref(true)
const savedSnapshot = ref('')

const form = reactive({
  script_id: '',
  name: '',
  description: '',
  enabled: true,
  code: TEMPLATE,
})

const snapshot = () =>
  JSON.stringify([form.script_id, form.name, form.description, form.enabled, form.code])

const dirty = computed(() => snapshot() !== savedSnapshot.value)

const filtered = computed(() => {
  const key = search.value.trim().toLowerCase()
  if (!key) return scripts.value
  return scripts.value.filter((s) =>
    [s.script_id, s.name, s.description].some((v) => (v || '').toLowerCase().includes(key)),
  )
})

const healthTag = computed(() => {
  if (blocked.value) return { label: '接口不可用', type: 'warning' }
  if (!runtime.value) return { label: '运行中未获取', type: 'default' }
  if (!runtime.value.success) return { label: '自检失败', type: 'error' }
  return { label: `Lua 就绪 · ${runtime.value.healthcheck?.runtime?.lua || ''}`, type: 'success' }
})

const contractSample = `function handle(ctx)
  local data = ctx.input        -- 请求体
  if data.step > 10 then
    log("步数偏大:", data.step)
  end
  ctx.output.tag = "big"        -- 也可以直接写 output
  return { ok = true, car = data.car }
end`

const httpSample = `-- 取数据 → 处理 → POST 给下游（完整可跑的例子见「插入示例」）
local r = http.get("http://10.0.0.5:8080/api/task/1001")
if not r.ok then
  return { ok = false, error = r.error }          -- 上游没通，如实返回
end

local task = r.json or {}                         -- JSON 响应自动解码
local out = { id = task.id, car = ctx.input.car, ts = os.time() }

local sent = http.post("http://10.0.0.9:9000/hook", out)   -- 中转给下游
return { ok = true, upstream = r.status, relayed = sent.ok, data = out }`

const curlSample = computed(() => {
  const id = currentId.value || form.script_id || 'demo.echo'
  return [
    `# 直接 POST 业务 JSON —— 其他服务把脚本当接口调就用这种`,
    `curl -X POST http://127.0.0.1:8000${BASE}/${id}/run \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '${payloadText.value.replace(/\s*\n\s*/g, ' ').trim() || '{}'}'`,
    ``,
    `# 只带 query 也行（脚本里读 ctx.query，值都是字符串）`,
    `curl "http://127.0.0.1:8000${BASE}/${id}/run?car=AGV-07&step=12"`,
  ].join('\n')
})

const remoteCurlSample = computed(() => {
  const id = currentId.value || form.script_id || 'demo.echo'
  const header = runtime.value?.config?.api_key_set
    ? [`  -H "X-API-Key: <config.toml 里的 api_key>" \\`]
    : []
  return [
    `# 跨机/跨服务调用：config.toml 里 [user_script] allow_remote = true 且配好 api_key`,
    `curl -X POST http://<本机IP>:8000${BASE}/${id}/run \\`,
    `  -H "Content-Type: application/json" \\`,
    ...header,
    `  -d '${payloadText.value.replace(/\s*\n\s*/g, ' ').trim() || '{}'}'`,
  ].join('\n')
})

// ── 工具 ──
function fmtBytes(n) {
  if (!n && n !== 0) return '-'
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`
  return `${(n / 1024 / 1024).toFixed(2)}MB`
}

function pretty(value) {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function firstLine(text) {
  return (text || '').split('\n')[0]
}

async function api(path, options = {}) {
  const res = await fetch(BASE + path, {
    method: 'GET',
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  const text = await res.text()
  let body = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = null
  }
  if (!res.ok) {
    const detail = body?.detail ?? text ?? `HTTP ${res.status}`
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail)
    const err = new Error(msg)
    err.status = res.status
    err.body = body // 脚本用 __status 指定状态码时，body 里其实是正常的执行信封
    throw err
  }
  return body
}

/** 403/401 只在"闸门"场景提示：脚本被禁用之类的 403 是业务结果，不是接口不可用 */
function markBlocked(err) {
  if (err.status === 401 || err.status === 403) {
    blocked.value = err.message
  }
}

// ── 数据加载 ──
async function loadRuntime() {
  try {
    runtime.value = await api('/runtime')
    blocked.value = ''
  } catch (err) {
    runtime.value = null
    blocked.value = err.message
  }
}

async function loadScripts() {
  try {
    const data = await api('/')
    scripts.value = data?.scripts || []
  } catch (err) {
    scripts.value = []
    markBlocked(err)
    if (err.status !== 401 && err.status !== 403) message.error(`加载脚本列表失败：${err.message}`)
  }
}

async function refreshAll() {
  loading.value = true
  try {
    await Promise.all([loadRuntime(), loadScripts()])
  } finally {
    loading.value = false
  }
}

async function loadRuns(id) {
  if (!id) {
    runs.value = []
    return
  }
  loadingRuns.value = true
  try {
    const data = await api(`/${encodeURIComponent(id)}/runs?limit=50`)
    runs.value = data?.runs || []
  } catch (err) {
    runs.value = []
    message.error(`加载流水失败：${err.message}`)
  } finally {
    loadingRuns.value = false
  }
}

// ── 编辑状态切换 ──
function applyScript(script) {
  form.script_id = script.script_id
  form.name = script.name || ''
  form.description = script.description || ''
  form.enabled = !!script.enabled
  form.code = script.code ?? ''
  currentId.value = script.script_id
  currentVersion.value = script.version
  savedSnapshot.value = snapshot()
}

function resetForm() {
  form.script_id = ''
  form.name = ''
  form.description = ''
  form.enabled = true
  form.code = TEMPLATE
  currentId.value = ''
  currentVersion.value = 0
  checkResult.value = null
  runResult.value = null
  runs.value = []
  savedSnapshot.value = snapshot()
}

async function guardUnsaved(action) {
  if (!dirty.value) return true
  return new Promise((resolve) => {
    dialog.warning({
      title: '有未保存的修改',
      content: currentId.value
        ? `脚本 ${currentId.value} 的修改还没保存，继续将丢弃这些修改。`
        : '新脚本还没保存，继续将丢弃已写的内容。',
      positiveText: '丢弃修改',
      negativeText: '继续编辑',
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
      onMaskClick: () => resolve(false),
    })
  })
}

async function openScript(id) {
  if (id === currentId.value) return
  if (!(await guardUnsaved())) return
  try {
    const data = await api(`/${encodeURIComponent(id)}`)
    applyScript(data.script)
    checkResult.value = null
    runResult.value = null
    await loadRuns(id)
  } catch (err) {
    message.error(`读取脚本失败：${err.message}`)
  }
}

async function newScript() {
  if (!(await guardUnsaved())) return
  resetForm()
  tab.value = 'edit'
}

// ── 保存 / 检查 ──
function validateForm() {
  if (!SCRIPT_ID_RE.test(form.script_id)) {
    message.error('脚本 ID 只能包含字母、数字、下划线、点和短横线，长度 1-64')
    return false
  }
  if (!form.code.trim()) {
    message.error('脚本内容不能为空')
    return false
  }
  return true
}

async function saveScript() {
  if (saving.value || !validateForm()) return false
  saving.value = true
  try {
    const payload = {
      code: form.code,
      name: form.name,
      description: form.description,
      enabled: form.enabled,
      validate_code: true,
    }
    const data = currentId.value
      ? await api(`/${encodeURIComponent(currentId.value)}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      : await api('/', { method: 'POST', body: JSON.stringify({ ...payload, script_id: form.script_id }) })

    applyScript(data.script)
    currentVersion.value = data.script.version
    message.success(`已保存 ${data.script.script_id} v${data.script.version}`)
    await loadScripts()
    return true
  } catch (err) {
    message.error(err.message)
    return false
  } finally {
    saving.value = false
  }
}

async function checkCode() {
  if (checking.value) return
  if (!form.code.trim()) {
    message.error('脚本内容不能为空')
    return
  }
  checking.value = true
  tab.value = 'edit'
  const pathId = SCRIPT_ID_RE.test(form.script_id) ? form.script_id : 'adhoc'
  try {
    checkResult.value = await api(`/${encodeURIComponent(pathId)}/check`, {
      method: 'POST',
      body: JSON.stringify({ code: form.code }),
    })
    if (checkResult.value.success) message.success('语法检查通过')
  } catch (err) {
    checkResult.value = { success: false, error: err.message }
    message.error(err.message)
  } finally {
    checking.value = false
  }
}

// ── 运行 ──
/** 没保存过的新脚本 / 勾了临时执行：走 /run 不落库 */
const effectiveAdhoc = computed(() => adhoc.value || !currentId.value)

async function runNow() {
  tab.value = 'run'
  await runScript()
}

async function runScript() {
  if (running.value) return
  let payload
  try {
    payload = payloadText.value.trim() ? JSON.parse(payloadText.value) : {}
  } catch (err) {
    message.error(`请求数据不是合法 JSON：${err.message}`)
    tab.value = 'run'
    return
  }

  const useAdhoc = effectiveAdhoc.value
  if (!useAdhoc && dirty.value && saveBeforeRun.value) {
    const ok = await saveScript()
    if (!ok) return
  }

  running.value = true
  try {
    const data = useAdhoc
      ? await api('/run', {
        method: 'POST',
        body: JSON.stringify({ code: form.code, payload, script_id: form.script_id || 'adhoc' }),
      })
      : await api(`/${encodeURIComponent(currentId.value)}/run`, {
        method: 'POST',
        body: JSON.stringify({ payload }),
      })
    runResult.value = data
    if (data.ok) message.success(`执行成功（${data.duration_ms}ms）`)
    else message.error(firstLine(data.error) || '执行失败')
    if (!useAdhoc) {
      await Promise.all([loadRuns(currentId.value), loadScripts()])
    }
  } catch (err) {
    // 脚本可以用 __status 指定 HTTP 状态码（400/502 之类），那不是"接口挂了"，
    // 而是脚本的业务表态 —— 这种响应体就是正常的执行信封，照常展示结果。
    const envelope = err.body && typeof err.body === 'object' && 'script_id' in err.body && 'ok' in err.body
    if (envelope) {
      runResult.value = err.body
      message.warning(`脚本返回 HTTP ${err.status}`)
      if (!useAdhoc) await loadRuns(currentId.value)
    } else {
      runResult.value = { ok: false, error: err.message, error_type: 'request', logs: [] }
      message.error(err.message)
    }
  } finally {
    running.value = false
  }
}

// ── 删除 ──
function confirmDelete(id) {
  dialog.warning({
    title: '删除脚本',
    content: `确定删除 ${id} 吗？正文会先留一份到 lua_script/.backup/ 再删除。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api(`/${encodeURIComponent(id)}`, { method: 'DELETE' })
        message.success(`已删除 ${id}`)
        if (currentId.value === id) resetForm()
        await loadScripts()
      } catch (err) {
        message.error(err.message)
      }
    },
  })
}

// ── 小工具 ──
function fillExample(key) {
  const example = EXAMPLES[Number(key)]
  if (!example) return
  const apply = () => {
    form.code = example.code
    message.success(`已插入示例：${example.name}`)
  }
  if (form.code.trim() && form.code !== example.code) {
    dialog.warning({
      title: '插入示例',
      content: `会覆盖当前编辑器内容，确定插入「${example.name}」吗？`,
      positiveText: '覆盖',
      negativeText: '取消',
      onPositiveClick: apply,
    })
    return
  }
  apply()
}

function fillPayloadSample() {
  payloadText.value = PAYLOAD_SAMPLE
}

async function copyCurl() {
  try {
    await navigator.clipboard.writeText(curlSample.value)
    message.success('已复制 curl 示例')
  } catch {
    message.warning('浏览器不允许复制，请手动选中文本')
  }
}

async function copyRemoteCurl() {
  try {
    await navigator.clipboard.writeText(remoteCurlSample.value)
    message.success('已复制跨机调用示例')
  } catch {
    message.warning('浏览器不允许复制，请手动选中文本')
  }
}

onBeforeRouteLeave(async () => {
  if (!dirty.value) return true
  return guardUnsaved()
})

onMounted(async () => {
  resetForm()
  await refreshAll()
  if (scripts.value.length) {
    await openScript(scripts.value[0].script_id)
  }
})
</script>

<style scoped>
.user-script-page {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.head-card {
  margin-bottom: 2px;
}

.head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.title {
  margin: 0 0 4px;
  font-size: 18px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.desc {
  margin: 0;
  font-size: 13px;
  color: #8a8a8a;
  line-height: 1.6;
  max-width: 900px;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e0e0e0;
  font-size: 12px;
  color: #8a8a8a;
}

.meta .dir {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.blocked {
  margin-bottom: 4px;
}

.layout {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.col-left,
.col-right {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

/* 列表项 */
.item {
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.15s ease;
}

.item:hover {
  background: rgba(128, 128, 128, 0.1);
}

.item-active {
  background: rgba(24, 144, 255, 0.12);
  border-color: rgba(24, 144, 255, 0.35);
}

.item-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.item-sub {
  justify-content: space-between;
  font-size: 12px;
  color: #8a8a8a;
  margin-top: 2px;
}

.item-id {
  font-weight: 600;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-ver {
  margin-left: auto;
  font-size: 11px;
  color: #a0a0a0;
}

.item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ok {
  color: #18a058;
}

.bad {
  color: #d03050;
}

/* 运行时卡片 */
.runtime-box {
  font-size: 12px;
}

.rt-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 0;
  color: #8a8a8a;
}

.rt-row span:last-child {
  color: #333;
}

[data-theme='dark'] .rt-row span:last-child {
  color: #ddd;
}

.rt-col {
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.path {
  display: block;
  width: 100%;
  word-break: break-all;
  font-size: 11px;
  font-family: ui-monospace, Consolas, monospace;
}

/* 表单 */
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 90px;
  gap: 6px 10px;
  align-items: start;
  margin-bottom: 8px;
}

.fld {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.fld-label {
  font-size: 12px;
  color: #8a8a8a;
}

.span-2 {
  grid-column: span 3;
}

.editor-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.check-alert {
  margin-top: 8px;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.panel-title {
  font-weight: 600;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-sub {
  font-size: 12px;
  color: #a0a0a0;
}

.tools {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.hint {
  font-size: 12px;
}

/* 运行面板 */
.run-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
}

.block-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
}

.block-label {
  font-size: 12px;
  color: #8a8a8a;
  margin-bottom: 4px;
  display: flex;
  gap: 6px;
  align-items: center;
}

.run-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 8px 0 4px;
}

.muted {
  color: #a0a0a0;
  font-weight: 400;
  font-size: 12px;
}

.result-box {
  max-height: 52vh;
  overflow: auto;
}

.result-block {
  margin-bottom: 8px;
}

.json {
  margin: 0;
  padding: 8px;
  border-radius: 4px;
  background: rgba(128, 128, 128, 0.12);
  font: 12px/1.6 ui-monospace, SFMono-Regular, Consolas, 'Cascadia Mono', monospace;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow: auto;
}

.json.error {
  color: #d03050;
}

.json.log {
  color: #18a058;
}

.tb summary {
  cursor: pointer;
  font-size: 12px;
  color: #8a8a8a;
  margin-bottom: 4px;
}

/* 流水 */
.runs {
  display: flex;
  flex-direction: column;
}

.run-row {
  display: grid;
  grid-template-columns: 150px 72px 70px 130px minmax(0, 1fr) minmax(0, 1.4fr);
  gap: 8px;
  align-items: center;
  padding: 4px 2px;
  border-bottom: 1px solid rgba(128, 128, 128, 0.16);
  font-size: 12px;
}

.run-ts,
.run-dur,
.run-bytes,
.run-src {
  color: #8a8a8a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-err {
  color: #d03050;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 说明 */
.help {
  font-size: 13px;
  line-height: 1.7;
}

.help-link {
  margin-bottom: 8px;
}

.help p {
  margin: 0 0 6px;
}

.help .mt {
  margin-top: 12px;
}

.help code {
  padding: 0 4px;
  border-radius: 3px;
  background: rgba(128, 128, 128, 0.16);
  font-family: ui-monospace, Consolas, monospace;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.pits {
  margin: 0;
  padding-left: 20px;
}

.pits li {
  margin-bottom: 4px;
}

@media (max-width: 992px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .run-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .form-grid {
    grid-template-columns: 1fr 1fr;
  }

  .span-2 {
    grid-column: span 2;
  }

  .run-row {
    grid-template-columns: 120px 64px 60px minmax(0, 1fr);
  }

  .run-bytes,
  .run-src {
    display: none;
  }
}
</style>
