import os
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# 配置静态文件服务 - 挂载assets文件夹
def setup_static_files(app: FastAPI):
    """配置静态文件服务"""
    frontend_dist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web", "dist")
    assets_dir = os.path.join(frontend_dist_dir, "assets")

    # 挂载assets目录
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# 根路径路由，提供SPA入口文件
def setup_root_route(app: FastAPI):
    """设置根路径路由"""
    @app.get("/")
    async def root():
        """提供SPA入口文件"""
        frontend_dist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web", "dist")
        index_path = os.path.join(frontend_dist_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "AGV Monitor API", "websocket_endpoint": "/ws/robot-status"}

# 添加404错误处理，返回index.html以支持SPA路由
def setup_404_handler(app: FastAPI):
    """设置404错误处理"""
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        """处理404错误，返回index.html以支持SPA路由"""
        frontend_dist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web", "dist")
        index_path = os.path.join(frontend_dist_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Not found"}