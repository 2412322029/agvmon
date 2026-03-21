import asyncio

from fastapi import FastAPI

from backend.api.other import cleanup_expired_files
from backend.api.rcmsapi import rapi
from backend.api.websocket import broadcast_robot_status, start_zeromq_management_task
from util.config import cfg


# 应用启动时的事件处理
def setup_startup_event(app: FastAPI):
    """设置应用启动事件"""
    @app.on_event("startup")
    async def startup_event():
        """应用启动时的事件处理"""
        # Clean up expired files on startup
        cleanup_expired_files()
        
        # 启动广播任务
        rdstag = cfg.get_with_reload("rcms.host").split("://")[1].replace(":", "-")
        task = asyncio.create_task(broadcast_robot_status(rdstag))
        task.set_name("broadcast_robot_status")
        # t/ask.result
        # 启动ZeroMQ管理任务
        # print(f"cfg.get('zmq_auto'): {cfg.get('zmq_auto')}")``
        if cfg.get("zmq_auto"):
            asyncio.create_task(start_zeromq_management_task())
        rapi.build_from_cache()
