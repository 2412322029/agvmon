# AGVMON - AGV 机器人监控管理

AGV 实时监控与运维管理平台，提供机器人状态监控、任务调度、地图可视化、远程 SSH 诊断、DataMatrix 编解码及日志分析等功能。

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | Python 3.12+ / FastAPI |
| ASGI 服务器 | uvicorn |
| 前端 | Vue 3 + Vite 8 + Naive UI |
| 消息队列 | ZeroMQ（实时状态）、RabbitMQ（任务队列） |
| 缓存/存储 | Redis / SQLite |
| 数据解析 | lxml (XML)、orjson (JSON) |
| SSH | asyncssh |
| 图像处理 | Pillow、pylibdmtx |

## 项目结构

```
├── backend/                # FastAPI 后端
│   ├── app.py              # 应用入口，路由注册，中间件
│   └── api/                # API 模块
│       ├── rcmsapi.py      # RCMS REST API 代理
│       ├── rcswebapi.py    # RCS2000 Web 接口
│       ├── wcsapi.py       # WCS 设备状态接口
│       ├── agvssh.py       # AGV SSH 远程连接
│       ├── log_parser.py   # 日志分析 API（AGV/WCS/Clean）
│       ├── websocket.py    # WebSocket 实时推送
│       ├── startup.py      # 启动事件
│       └── ...
├── util/                   # 核心工具库
│   ├── config.py           # 配置管理器（TOML）
│   ├── config.toml         # 配置文件
│   ├── rabbitmq.py         # RabbitMQ 客户端
│   ├── zeromq_sub.py       # ZeroMQ 订阅
│   ├── ssh_manager.py      # SSH 连接管理
│   ├── yuv2png.py          # YUV 图像转换
│   └── data/               # 缓存/模拟数据/图像资源
├── web/                    # Vue 3 前端
│   ├── src/
│   │   ├── views/          # 页面视图
│   │   ├── components/     # 通用组件
│   │   └── router/         # 路由配置
│   └── dist/               # 编译产物
├── static/                 # 自托管 API 文档静态文件
├── main.py                 # CLI 入口
├── build_nuitka.py         # Nuitka 打包脚本
└── pyproject.toml
```

## 快速开始

### 环境要求

- Python >= 3.12
- Node.js >= 20.19（前端开发）
- Redis 服务
- 可选：uv（Python 包管理器）

### 安装

```bash
# 安装 Python 依赖
pip install -e .
# 或使用 uv
uv sync

# 安装前端依赖并构建
cd web
npm install
npm run build
cd ..
```

### 配置

编辑 `util/config.toml` 配置 RCMS 服务器地址、Redis 连接、AGV SSH 凭据等：

```toml
[rcms]
host = "192.168.1.100"
rcms_url = "http://192.168.1.100:8080"
mapcode = "your_map_code"

[redis]
host = "127.0.0.1"
port = 6379
db = 0

[web]
host = "0.0.0.0"
port = 8000
```

### 运行

```bash
# 启动 Web 服务
agvmon run web

# 或直接使用
python main.py run web

# 启动实时地图更新（ZeroMQ）
agvmon run zeromq

# 构建地图缓存
agvmon build raw
agvmon build genmap

# 查看所有命令
agvmon --help
```

启动后访问 `http://localhost:8000` 查看监控面板。

## 功能模块

### 实时监控
- 机器人状态仪表盘（位置、电量、速度、载货状态、告警）
- 机器人路径实时可视化
- WebSocket 自动推送更新

### 地图系统
- 从 RCMS 共享地图数据生成 PNG/SVG 地图
- 实时机器人位置叠加
- 区域标签和设备标记

### 任务管理
- 任务查询与详情查看（含子任务）
- 任务控制：暂停/恢复、取消、强制取消、释放
- 滚动状态实时检测

### SSH 远程诊断
- 异步 SSH 连接单个 AGV
- 远程文件浏览、上传、下载、预览
- YUV 摄像头图像转 PNG
- 命令注入防护

### DataMatrix 编解码
- DataMatrix 条码编码（SVG 输出）
- 解码识别
- 适用于 AGV 路径物理标记识别

### 日志分析
- **AGV 日志**：远程下载（SSE 实时进度）、本地管理、PIO 信号位对比分析
- **WCS 日志**：按探测器短码 / TrayID 过滤，hover 协议解析（AGV 控制指令 + EQ 状态），TrayID 高亮
- **日志清理**：AGV / WCS 日志目录批量管理

### 其他工具
- AGV 日志下载与 PIO 分析
- AGV / EQ 协议十六进制解析
- RabbitMQ 消息消费
- 文件上传管理（Redis + TTL）
- 异常日志记录（SQLite）
- 公共聊天室（WebSocket）
- 暗色模式 UI
- 自托管 Swagger/ReDoc 文档（离线可用）

## CLI 命令参考

```
agvmon [--test] {build,run,tools} ...

build:
  raw        从 RCMS API 获取原始数据并构建缓存
  cache      从缓存构建模型
  genmap     生成地图图片
  saveport   保存端口数据到缓存
  transport  转换端口数据

run:
  web        启动 FastAPI Web 服务
  zeromq     启动 ZeroMQ 实时地图更新
  rabbitmq   启动 RabbitMQ 消息消费

tools:
  show-robot 显示机器人实时状态
  rk         删除 Redis key
  agvlog     下载并分析 AGV 日志
```

## 构建发布

使用 Nuitka 将项目编译为独立 Windows 可执行文件：

```bash
python build_nuitka.py
```

产物将输出到 `dist/` 目录，可选 7-Zip 压缩打包。

## 界面截图

![AGVMon 监控界面](./README.assets/image-20260318223446582.png)

## License

Internal use.
