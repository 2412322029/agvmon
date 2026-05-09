<script setup>
import { NCard, NDataTable, NDivider, NTabPane, NTabs, NText } from 'naive-ui';
</script>

<template>
  <div class="about-container">
    <div class="hero">
      <h2>AGVmon</h2>
      <n-text depth="2" class="subtitle">AGV 实时监控与运维管理平台</n-text>
      <n-text depth="3" class="desc">
        AGV 运维工具集，覆盖机器人状态监控、地图可视化、任务调度、SSH 远程诊断、
        日志分析、协议解析、DataMatrix 编解码等运维需求。
      </n-text>
    </div>

    <n-divider />

    <n-tabs type="line" size="large" default-value="overview">
      <!-- ═══════════════ 概览 ═══════════════ -->
      <n-tab-pane name="overview" tab="概览">
        <n-card size="small" title="技术栈">
          <n-dataTable
            :columns="[
              { title: '组件', key: 'name', width: 140 },
              { title: '技术', key: 'tech' },
            ]"
            :data="[
              { name: '后端框架', tech: 'Python 3.12+ / FastAPI' },
              { name: 'ASGI 服务器', tech: 'uvicorn' },
              { name: '前端', tech: 'Vue 3 + Vite + Naive UI' },
              { name: '消息队列', tech: 'ZeroMQ（实时状态）、RabbitMQ（任务队列）' },
              { name: '缓存/存储', tech: 'Redis / SQLite' },
              { name: '数据解析', tech: 'lxml (XML)、orjson (JSON)' },
              { name: 'SSH', tech: 'asyncssh' },
              { name: '图像处理', tech: 'Pillow、pylibdmtx' },
              { name: '打包发布', tech: 'Nuitka → 独立 exe' },
            ]"
            size="small" :bordered="false" />
        </n-card>

        <n-divider />

        <n-card size="small" title="功能模块">
          <n-dataTable
            :columns="[
              { title: '模块', key: 'name', width: 160 },
              { title: '说明', key: 'desc' },
            ]"
            :data="[
              { name: '实时监控仪表盘', desc: '机器人状态概览（位置、电量、速度、载货、告警），路径可视化，WebSocket 实时推送' },
              { name: '地图系统', desc: 'RCMS 共享地图生成 PNG/SVG，实时机器人位置叠加，区域标签与设备标记' },
              { name: '任务管理', desc: '任务查询与详情（含子任务），暂停/恢复/取消/强制取消/释放，滚动状态检测' },
              { name: 'WCS 设备状态', desc: '按设备类型（Buffer/Machine/CMS）查询实时状态与仓储位置信息' },
              { name: 'SSH 远程诊断', desc: '异步 SSH 连接 AGV，文件浏览/上传/下载/预览，YUV 转 PNG，命令注入防护' },
              { name: '日志分析', desc: 'AGV 日志下载（SSE 进度）+ PIO 位对比分析；WCS 日志按短码/TrayID 过滤 + hover 协议解析' },
              { name: 'AGV/EQ 协议解析', desc: '十六进制协议数据解析，支持 AGV 控制指令 + EQ 设备状态双向解析' },
              { name: 'DataMatrix 编解码', desc: '条码编码（SVG 输出）、解码识别，适配 AGV 路径物理标记' },
              { name: '文件上传管理', desc: '文件上传至 Redis（TTL 自动过期），集中管理查看' },
              { name: '异常日志记录', desc: 'SQLite 持久化存储异常事件，支持查询追溯' },
              { name: '公共聊天室', desc: 'WebSocket 多人实时通信，支持 Markdown 渲染与代码语法高亮' },
              { name: '暗色模式', desc: '全局暗色主题，跟随系统或手动切换' },
              { name: '离线文档', desc: '自托管 Swagger UI / ReDoc，离线可用' },
            ]"
            size="small" :bordered="false" />
        </n-card>
      </n-tab-pane>

      <!-- ═══════════════ 界面功能 ═══════════════ -->
      <n-tab-pane name="pages" tab="界面功能">
        <n-card size="small" title="页面导航">
          <n-dataTable
            :columns="[
              { title: '页面', key: 'name', width: 150 },
              { title: '路由', key: 'path', width: 160 },
              { title: '功能说明', key: 'desc' },
            ]"
            :data="[
              { name: '首页', path: '/', desc: '机器人实时状态仪表盘，卡片式布局展示在线/离线/告警数量，快速跳转各功能' },
              { name: '服务管理', path: '/service', desc: '系统服务状态总览，管理缓存构建任务' },
              { name: '从缓存构建', path: '/service/build_from_cache', desc: '从本地缓存重建数据模型与地图' },
              { name: '从原始数据构建', path: '/service/build_from_raw', desc: '从 RCMS API 拉取原始数据并构建缓存' },
              { name: '地图', path: '/map', desc: 'SVG/PNG 地图交互查看，支持缩放拖拽，实时机器人位置叠加' },
              { name: '任务查询', path: '/task-query', desc: '多条件任务查询，子任务详情展开，任务控制操作' },
              { name: 'RCS Web 登录', path: '/rcs-web-login', desc: 'RCS2000 Web 管理后台内嵌登录' },
              { name: '异常记录', path: '/exception-records', desc: '异常事件列表查询，按时间/类型筛选' },
              { name: '日志分析', path: '/log-parser', desc: 'AGV 日志下载与 PIO 分析 + WCS 日志解析（短码/trayid 过滤、协议拆解）' },
              { name: 'AGV-EQ 协议解析', path: '/agv-eq-protocol-parser', desc: '十六进制协议解析，AGV/EQ 字段级翻译，支持示例数据' },
              { name: 'SSH 文件管理', path: '/ssh', desc: 'AGV 远程文件浏览、文本预览、YUV 图片转换预览' },
              { name: 'SSH 连接管理', path: '/ssh-mgr', desc: '已连接 AGV 列表，批量管理 SSH 会话' },
              { name: '文件上传管理', path: '/file-upload', desc: '上传文件至 Redis，TTL 管理，文件列表查看' },
              { name: 'DM 编解码', path: '/dmdtx-decode', desc: 'DataMatrix 条码编码生成（SVG）与解码识别' },
              { name: '聊天室', path: '/chat', desc: 'WebSocket 多人实时聊天，支持 Markdown 与代码高亮' },
              { name: 'WCS 设备状态', path: '/wcs-status', desc: '按设备类型查询设备状态与 CMS 仓储位置信息' },
              { name: '设置', path: '/setting', desc: '全局偏好设置（主题等）' },
              { name: '关于', path: '/about', desc: '本页面' },
            ]"
            size="small" :bordered="false" />
        </n-card>
      </n-tab-pane>

      <!-- ═══════════════ CLI 命令 ═══════════════ -->
      <n-tab-pane name="cli" tab="CLI 命令">
        <n-card size="small" title="命令总览">
          <pre class="cli-block">
agvmon [--test] {build,run,tools} ...

build:
  raw        从 RCMS API 获取原始数据并构建缓存
  cache      从缓存构建模型
  genmap     生成地图图片（PNG + SVG）
  saveport   保存端口数据到缓存
  transport  转换端口数据格式

run:
  web        启动 FastAPI Web 服务
  zeromq     启动 ZeroMQ 实时地图更新订阅
  rabbitmq   启动 RabbitMQ 消息消费

tools:
  show-robot 显示机器人实时状态
  rk         删除 Redis key
  clean      清理日志文件（wcslog / agvlog）
  wcslog     解析 WCS 日志文件
  agvlog     下载并分析 AGV 日志</pre>
        </n-card>

        <n-divider />

        <n-card size="small" title="使用示例">
          <pre class="cli-block">
# 构建缓存
python main.py build raw      # 从 RCMS API 拉取原始数据
python main.py build cache    # 从缓存重建模型
python main.py build genmap   # 生成地图图片

# 启动服务
python main.py run web        # Web 服务 (http://localhost:8000)
python main.py run zeromq     # 实时地图更新
python main.py run rabbitmq   # 消息队列消费

# 工具
python main.py tools show-robot   # 查看机器人状态
python main.py tools agvlog       # 下载分析 AGV 日志
python main.py tools wcslog       # 解析 WCS 日志
python main.py tools clean        # 清理日志文件

# 测试模式（使用本地测试数据，不连接 RCMS）
python main.py --test run web</pre>
        </n-card>
      </n-tab-pane>

      <!-- ═══════════════ 快速开始 ═══════════════ -->
      <n-tab-pane name="start" tab="快速开始">
        <n-card size="small" title="环境要求">
          <n-dataTable
            :columns="[
              { title: '依赖', key: 'item', width: 160 },
              { title: '版本要求', key: 'ver' },
            ]"
            :data="[
              { item: 'Python', ver: '>= 3.12' },
              { item: 'Node.js', ver: '>= 20.19（前端开发/构建）' },
              { item: 'Redis', ver: '运行中（缓存服务）' },
              { item: 'uv（可选）', ver: 'Python 包管理器替代 pip' },
            ]"
            size="small" :bordered="false" />
        </n-card>

        <n-divider />

        <n-card size="small" title="安装 & 启动">
          <pre class="cli-block">
# 1. 安装 Python 依赖
pip install -e .
# 或使用 uv
uv sync

# 2. 前端构建
cd web && npm install && npm run build && cd ..

# 3. 编辑 util/config.toml
# [rcms] host / [redis] host:port / [web] host:port

# 4. 构建数据缓存
python main.py build raw
python main.py build cache

# 5. 启动
python main.py run web
# → http://localhost:8000</pre>
        </n-card>

        <n-divider />

        <n-card size="small" title="构建发布">
          <pre class="cli-block">
# 编译为独立 Windows 可执行文件
python build_nuitka.py
# 产物输出至 dist/ 目录</pre>
        </n-card>
      </n-tab-pane>
    </n-tabs>

    <n-divider />
    <n-text depth="3" class="footer">
      © 2026 Lolik | <a href="https://github.com/2412322029/agvmon" target="_blank">github.com/2412322029/agvmon</a>
    </n-text>
  </div>
</template>

<style scoped>
.about-container {
  padding: 12px;
  max-width: 900px;
}
.hero {
  margin-bottom: 8px;
}
.hero h2 {
  margin-bottom: 4px;
  font-size: 28px;
}
.hero .subtitle {
  display: block;
  font-size: 15px;
  margin-bottom: 8px;
}
.hero .desc {
  display: block;
  font-size: 13px;
  line-height: 1.7;
}
.cli-block {
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.7;
  background: var(--n-color-embedded);
  padding: 12px 16px;
  border-radius: 6px;
  white-space: pre;
  overflow-x: auto;
}
.footer {
  font-size: 12px;
}
</style>
