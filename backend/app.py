from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from backend.api.agvssh import agv_web_router
from backend.api.rcmsapi import rcms_router
from backend.api.rcswebapi import rcs_web_router
from backend.api.redis_client import get_rdstag
from backend.api.startup import setup_startup_event
from backend.api.static_routes import (
    setup_404_handler,
    setup_root_route,
    setup_static_files,
)
from backend.api.websocket import websocket_robot_status_endpoint
from util.config import cfg, r

# 创建FastAPI应用
app = FastAPI(title="AGV Monitor API", description="AGV机器人状态监控WebSocket接口")

# 添加CORS中间件支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境中应限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有HTTP头
)

# 配置静态文件服务
setup_static_files(app)

# 配置根路径路由
setup_root_route(app)

# 配置404错误处理
setup_404_handler(app)

# 配置启动事件
setup_startup_event(app)

# 包含RcsWebApi路由
app.include_router(rcs_web_router, prefix="/api")

# 包含AgvWebApi路由
app.include_router(agv_web_router, prefix="/api")

# 包含RcmsApi路由
app.include_router(rcms_router, prefix="/api")

# 设置WebSocket路由
@app.websocket("/ws/robot-status")
async def websocket_robot_status(websocket: WebSocket):
    """机器人状态WebSocket接口"""
    rdstag = get_rdstag()
    await websocket_robot_status_endpoint(websocket, r, rdstag)


def run_api_server():
    """运行FastAPI WebSocket服务器"""
    import uvicorn
    uvicorn.run("backend.app:app", **cfg.get("web"))
