from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.agvssh import agv_web_router
from backend.api.other import util_web_router, websocket_chat_endpoint
from backend.api.rcmsapi import rcms_router
from backend.api.rcswebapi import rcs_web_router
from backend.api.startup import setup_startup_event
from backend.api.static_routes import (
    setup_404_handler,
    setup_root_route,
    setup_static_files,
)
from backend.api.wcsapi import wcs_web_router
from backend.api.websocket import websocket_robot_status_endpoint
from util.config import cfg

# 创建FastAPI应用
app = FastAPI(
    title="AGV Monitor API",
    description="AGV机器人状态监控接口, RCS2000 web接口, WCS web接口, RCMS API, AGV SSH接口, 其他工具接口",
    docs_url=None,
    redoc_url=None,
)
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
# 自托管docs静态文件, 即使在离线、没有开放的互联网访问或在本地网络中也能继续工作
app.mount("/static", StaticFiles(directory=static_dir), name="static")
# 启用 Gzip 压缩，minimum_size 指定响应体超过多少字节才压缩
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    # 调用下一个中间件或路由处理函数
    response = await call_next(request)
    # 添加安全头
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
    response.headers["Content-Security-Policy"] = (
        "script-src 'self' https: 'unsafe-inline'; "
        "style-src 'self' https: 'unsafe-inline'; "
    )
    content_type = response.headers.get("content-type", "")
    if "javascript" in content_type or "css" in content_type or "image" in content_type:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"

    return response


# 添加CORS中间件支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源!
    allow_methods=["*"],  # 允许所有HTTP方法
)


# 自定义Swagger UI路由
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
    )


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


# 自定义ReDoc路由
@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="/static/redoc.standalone.js",
    )


@app.get("/favicon.ico")
async def root():
    return FileResponse(Path(__file__).parent.parent / "web" / "dist" / "favicon.ico")


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

# 包含UtilWebApi路由
app.include_router(util_web_router, prefix="/api")

# 包含WcsApi路由
app.include_router(wcs_web_router, prefix="/api")


# 设置WebSocket路由
@app.websocket("/ws/robot-status")
async def websocket_robot_status(websocket: WebSocket):
    """机器人状态WebSocket接口"""
    rdstag = cfg.get_with_reload("rcms.host").split("://")[1].replace(":", "-")
    await websocket_robot_status_endpoint(websocket, rdstag)


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """公共聊天WebSocket接口"""
    await websocket_chat_endpoint(websocket)


def run_api_server():
    """运行FastAPI WebSocket服务器"""
    uvicorn.run(
        "backend.app:app",
        **cfg.get("web"),
        timeout_keep_alive=10,  # 连接保持时间
        timeout_graceful_shutdown=5.0,  # 关闭超时
        # 性能限制
        limit_concurrency=1000,  # 最大并发连接数
        # limit_max_requests=10000,  # 防内存泄漏
        backlog=2048,  # TCP积压队列
        # 安全相关
        server_header=False,  # 隐藏服务器头
        date_header=True,  # 保留日期头
        # WebSocket配置
        ws_ping_interval=15.0,  # WebSocket ping间隔
        ws_ping_timeout=30.0,  # WebSocket ping超时
    )
