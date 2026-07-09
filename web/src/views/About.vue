<template>
  <div class="about-page">
    <div class="hero">
      <h2 class="title">AGVmon</h2>
      <span class="subtitle">AGV 实时监控与运维管理平台</span>
      <span class="desc">
        覆盖机器人状态监控、地图可视化、任务调度、SSH 远程诊断、日志分析、
        协议解析、DataMatrix 编解码等运维需求的集成工具集。
      </span>
      <span v-if="backendVersion.version" class="ver">
        v{{ backendVersion.version }} · {{ backendVersion.build_time }} · {{ backendVersion.git_hash }}
      </span>
    </div>

    <n-tabs type="line" size="large" default-value="changelog" class="tabs">

      <!-- ═══════════════ 版本历史 ═══════════════ -->
      <n-tab-pane name="changelog" tab="版本历史">
        <n-card size="small" title="Git 提交历史">
          <div class="git-desktop">
            <n-dataTable
              :columns="gitColumns"
              :data="gitHistory"
              size="small"
              :bordered="false"
              :row-key="(row) => row.hash"
            />
          </div>
          <div class="git-mobile">
            <div v-for="row in gitHistory" :key="row.hash" class="git-card">
              <div class="git-card-head">
                <a :href="`https://github.com/2412322029/agvmon/commit/${row.hash}`" target="_blank" class="git-hash">{{ row.short_hash }}</a>
                <span class="git-time">{{ row.time }}</span>
              </div>
              <pre class="git-msg">{{ row.message }}</pre>
            </div>
          </div>
        </n-card>
      </n-tab-pane>

      <!-- ═══════════════ 功能模块 ═══════════════ -->
      <n-tab-pane name="features" tab="功能">
        <div class="feature-grid">
          <n-card v-for="f in features" :key="f.name" size="small" class="feature-card">
            <div class="feature-name">{{ f.name }}</div>
            <div class="feature-desc">{{ f.desc }}</div>
          </n-card>
        </div>
      </n-tab-pane>

      <!-- ═══════════════ 页面导航 ═══════════════ -->
      <n-tab-pane name="pages" tab="页面">
        <n-card size="small" title="全部页面">
          <n-dataTable
            :columns="pageColumns"
            :data="pageList"
            size="small"
            :bordered="false"
            :row-key="(r) => r.path"
          />
        </n-card>
      </n-tab-pane>

      <!-- ═══════════════ 技术栈 ═══════════════ -->
      <n-tab-pane name="stack" tab="技术栈">
        <n-card size="small" title="核心依赖">
          <n-dataTable
            :columns="[{ title: '组件', key: 'name', width: 140 }, { title: '技术', key: 'tech' }]"
            :data="[
              { name: '后端框架', tech: 'Python 3.12+ / FastAPI' },
              { name: 'ASGI 服务器', tech: 'uvicorn' },
              { name: '前端', tech: 'Vue 3 + Vite + Naive UI' },
              { name: '实时推送', tech: 'ZeroMQ + WebSocket' },
              { name: '消息队列', tech: 'RabbitMQ' },
              { name: '缓存 / 存储', tech: 'Redis / SQLite' },
              { name: '数据解析', tech: 'lxml (XML) / orjson (JSON)' },
              { name: 'SSH', tech: 'asyncssh' },
              { name: '图像处理', tech: 'Pillow / pylibdmtx' },
              { name: '打包发布', tech: 'Nuitka → exe' },
            ]"
            size="small"
            :bordered="false"
          />
        </n-card>
      </n-tab-pane>

      <!-- ═══════════════ CLI ═══════════════ -->
      <n-tab-pane name="cli" tab="CLI">
        <n-card size="small" title="命令总览">
          <pre class="cli-block">
agvmon [--test] {build,run,tools} ...

<strong>build</strong>
  raw       从 RCMS API 拉取原始数据并构建缓存
  cache     从本地缓存重建数据模型
  genmap    生成地图图片（PNG + SVG）
  saveport  保存端口数据到缓存
  transport 转换端口数据格式

<strong>run</strong>
  web       启动 FastAPI Web 服务
  zeromq    启动 ZeroMQ 实时地图更新
  rabbitmq  启动 RabbitMQ 消息消费

<strong>tools</strong>
  show-robot  显示机器人实时状态
  rk          删除 Redis key
  clean       清理日志文件
  wcslog      解析 WCS 日志
  agvlog      下载并分析 AGV 日志</pre>
        </n-card>

        <n-divider />

        <n-card size="small" title="使用示例">
          <pre class="cli-block">
# 安装依赖
uv sync

# 构建缓存
uv run python main.py build raw
uv run python main.py build cache
uv run python main.py build genmap

# 启动服务
uv run python main.py run web        # → http://localhost:8000
uv run python main.py run zeromq     # 实时地图推送
uv run python main.py run rabbitmq   # 消息队列消费

# 工具
uv run python main.py tools show-robot
uv run python main.py tools agvlog
uv run python main.py tools wcslog
uv run python main.py tools clean

# 测试模式
uv run python main.py --test run web</pre>
        </n-card>
      </n-tab-pane>

      <!-- ═══════════════ 开发 ═══════════════ -->
      <n-tab-pane name="dev" tab="开发">
        <n-card size="small" title="环境要求">
          <n-dataTable
            :columns="[{ title: '依赖', key: 'item', width: 160 }, { title: '要求', key: 'ver' }]"
            :data="[
              { item: 'Python', ver: '≥ 3.12' },
              { item: 'Node.js', ver: '≥ 20（前端构建）' },
              { item: 'Redis', ver: '运行中' },
              { item: 'uv', ver: 'Python 包管理器' },
            ]"
            size="small"
            :bordered="false"
          />
        </n-card>

        <n-divider />

        <n-card size="small" title="安装 & 启动">
          <pre class="cli-block">
# 安装 Python 依赖
uv sync

# 前端构建
cd web && npm install && npm run build && cd ..

# 编辑配置
util/config.toml  →  [rcms] host / [redis] host:port / [web] host:port

# 构建缓存
uv run python main.py build raw
uv run python main.py build cache

# 启动
uv run python main.py run web
# → http://localhost:8000</pre>
        </n-card>

        <n-divider />

        <n-card size="small" title="构建发布">
          <pre class="cli-block">
# 编译为独立 Windows exe
uv run python build_nuitka.py
# → dist/</pre>
        </n-card>
      </n-tab-pane>
    </n-tabs>

    <n-divider />
    <span class="footer">
      © 2026 Lolik ·
      <a href="https://github.com/2412322029/agvmon" target="_blank">github.com/2412322029/agvmon</a>
    </span>
  </div>
</template>

<script setup>
import { NCard, NDataTable, NDivider, NTabPane, NTabs } from 'naive-ui'
import { h, onMounted, ref } from 'vue'
import router from '../router'

const backendVersion = ref({ version: '', build_time: '', git_hash: '' })
const gitHistory = ref([])

onMounted(async () => {
  try {
    const [v, h] = await Promise.all([
      fetch('/api/util/version'),
      fetch('/api/util/changelog'),
    ])
    if (v.ok) backendVersion.value = await v.json()
    if (h.ok) gitHistory.value = await h.json()
  } catch { /* 离线静默 */ }
})

// ── Git 列 ──
const gitColumns = [
  {
    title: 'Hash', key: 'short_hash', width: 90,
    render(row) {
      return h('a', {
        href: `https://github.com/2412322029/agvmon/commit/${row.hash}`,
        target: '_blank',
        style: { fontFamily: 'monospace', color: 'green' },
      }, row.short_hash)
    },
  },
  { title: '时间', key: 'time', width: 180 },
  {
    title: '提交信息', key: 'message',
    render(row) {
      return h('pre', {
        style: { margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontFamily: 'inherit' },
      }, row.message)
    },
  },
]

// ── 功能模块 ──
const features = [
  { name: '实时监控仪表盘', desc: '机器人状态概览（位置/电量/速度/载货/告警），WebSocket 实时推送，路径可视化' },
  { name: '地图系统', desc: 'RCMS 共享地图 PNG/SVG 渲染，机器人位置叠加，区域标签与设备标记' },
  { name: '任务管理', desc: '多条件任务查询、子任务详情展开，暂停/恢复/取消/强制取消/释放，滚动状态检测' },
  { name: 'WCS 设备状态', desc: '按设备类型查询实时状态与仓储位置（Buffer / Machine / CMS）' },
  { name: 'SSH 远程诊断', desc: '异步 SSH 连接 AGV，文件浏览/上传/下载/预览，YUV 转 PNG，命令注入防护' },
  { name: '日志分析', desc: 'AGV 日志下载（SSE 进度）+ PIO 位对比分析；WCS 日志按短码/TrayID 过滤' },
  { name: '协议解析', desc: '十六进制协议字段级翻译，AGV 控制指令 + EQ 设备状态双向解析' },
  { name: 'DM 编解码', desc: 'DataMatrix 条码编码（SVG 输出）与解码识别' },
  { name: 'Web Shell', desc: '浏览器内 SSH 终端，IP 白名单，会话保持，缓冲区回放' },
  { name: '异常日志', desc: 'SQLite 持久化存储异常事件，支持多条件查询追溯' },
  { name: '系统设置', desc: '在线编辑所有配置项（RCMS/Redis/Web/SSH…），自动类型识别，非本机只读保护' },
  { name: '聊天室', desc: 'WebSocket 多人实时通信，Markdown 渲染 + 代码语法高亮' },
  { name: '暗色模式', desc: '全局暗色主题，跟随系统偏好自动切换' },
  { name: '离线文档', desc: '自托管 Swagger UI / ReDoc，离线可用' },
  { name: '局域网服务', desc: 'Gossip 协议节点发现，局域网内服务状态互查' },
]

// ── 页面列表（从路由自动生成） ──
const PAGE_DESC = {
  'home': '机器人实时状态仪表盘，卡片式布局展示在线/离线/告警数量',
  'service': '系统服务状态总览，管理缓存构建与地图生成任务',
  'build_from_cache': '从本地缓存文件重建数据模型与地图',
  'build_from_raw': '从 RCMS API 拉取原始数据并构建缓存',
  'map': 'SVG / PNG 地图交互查看，支持缩放拖拽，实时机器人位置叠加',
  'task-query': '多条件任务查询，子任务详情展开，任务控制操作',
  'rcs-web-login': 'RCS2000 Web 管理后台内嵌登录（手动输入 或 配置文件凭据）',
  'exception-records': '异常事件列表，按时间 / 状态筛选，支持增删改查',
  'log-parser': 'AGV 日志下载与 PIO 分析 + WCS 日志解析（短码 / TrayID / hover 协议拆解）',
  'agv-eq-protocol-parser': '十六进制协议解析，AGV / EQ 字段级翻译，支持示例数据',
  'ssh': 'AGV 远程文件浏览、文本预览、YUV 图片转换预览',
  'ssh-mgr': '已连接 AGV 列表，批量管理 SSH 会话',
  'file-upload': '上传文件至 Redis（TTL 自动过期），集中管理查看',
  'dmdtx-decode': 'DataMatrix 条码编码生成（SVG）与解码识别',
  'chat': 'WebSocket 多人实时聊天，支持 Markdown 与代码高亮',
  'wcs-status': '按设备类型查询设备状态与 CMS 仓储位置',
  'setting': '在线编辑全部系统配置项，自动类型识别，非本机只读',
  'shell': '浏览器内 SSH 终端，IP 白名单控制',
  'gossip': '局域网节点自动发现，服务状态互查',
}

const pageColumns = [
  { title: '页面', key: 'name', width: 150 },
  { title: '路由', key: 'path', width: 180 },
  { title: '说明', key: 'desc', ellipsis: { tooltip: true } },
]

const pageList = router.getRoutes()
  .filter(r => r.path !== '/:pathMatch(.*)*' && r.name !== 'test' && r.name !== 'about')
  .map(r => ({
    name: r.meta?.disc || r.name,
    path: r.path,
    desc: PAGE_DESC[r.name] || '',
  }))
</script>

<style scoped>
.about-page {
  max-width: 900px;
  margin: 24px auto;
  padding: 0 16px;
}
.hero {
  text-align: center;
  margin-bottom: 20px;
}
.title {
  margin: 0 0 4px;
  font-size: 28px;
}
.subtitle {
  display: block;
  font-size: 15px;
  color: var(--n-text-color-2);
  margin-bottom: 8px;
}
.desc {
  display: block;
  font-size: 13px;
  color: var(--n-text-color-3);
  line-height: 1.7;
  max-width: 640px;
  margin: 0 auto;
}
.ver {
  display: block;
  margin-top: 8px;
  font-size: 12px;
  font-family: monospace;
  color: var(--n-text-color-3);
}
.tabs {
  margin-top: 8px;
}
/* ── 功能网格 ── */
.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.feature-card {
  border-left: 3px solid green;
}
.feature-name {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 4px;
}
.feature-desc {
  font-size: 12px;
  color: var(--n-text-color-3);
  line-height: 1.6;
}
/* ── CLI ── */
.cli-block {
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.7;
  background: var(--n-color-embedded);
  padding: 14px 18px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0;
}
/* ── Git ── */
.git-desktop { display: block; }
.git-mobile { display: none; }
.git-card {
  border: 1px solid var(--n-border-color);
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 10px;
}
.git-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  gap: 8px;
}
.git-hash {
  font-family: monospace;
  font-size: 12px;
  font-weight: 600;
  color: green;
  text-decoration: none;
}
.git-hash:hover { text-decoration: underline; }
.git-time { font-size: 12px; color: var(--n-text-color-2); flex-shrink: 0; }
.git-msg {
  margin: 0;
  font-family: monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--n-color-embedded);
  padding: 8px;
  border-radius: 4px;
}
/* ── Footer ── */
.footer {
  font-size: 12px;
  color: var(--n-text-color-3);
}
.footer a { color: green; }

@media (max-width: 768px) {
  .git-desktop { display: none; }
  .git-mobile { display: block; }
  .feature-grid { grid-template-columns: 1fr; }
}
</style>
