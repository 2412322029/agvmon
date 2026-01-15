import asyncio

from fastapi import FastAPI

from backend.api.redis_client import get_rdstag, redis_client
from backend.api.websocket import broadcast_robot_status


# 应用启动时的事件处理
def setup_startup_event(app: FastAPI):
    """设置应用启动事件"""
    @app.on_event("startup")
    async def startup_event():
        """应用启动时的事件处理"""
        # 启动广播任务
        rdstag = get_rdstag()
        asyncio.create_task(broadcast_robot_status(redis_client, rdstag))