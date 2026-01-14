import asyncio
import json
import os
import time

import redis
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocketDisconnect

from util.config import cfg

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

# 配置静态文件服务 - 挂载assets文件夹
frontend_dist_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist")
assets_dir = os.path.join(frontend_dist_dir, "assets")

# 挂载assets目录
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# 初始化Redis连接
r = redis.Redis(**cfg.get("redis"))

# 从配置中获取rdstag
rdstag = cfg.get("rcms.host").split("://")[1].replace(":", "-")

# 存储所有活跃的WebSocket连接
active_connections = set()

async def broadcast_robot_status():
    """广播机器人状态数据到所有连接的客户端"""
    while True:
        try:
            # 从Redis获取所有机器人状态
            robot_status = r.hgetall(f"{rdstag}:ROBOT_STATUS")
            
            # 构建消息数据
            robots = {}
            for robot_id, status_json in robot_status.items():
                robot_id_str = robot_id.decode("utf-8")
                try:
                    status = json.loads(status_json.decode("utf-8"))
                    robots[robot_id_str] = status
                except json.JSONDecodeError:
                    continue
            
            # 发送数据到所有连接的客户端
            if robots:
                message = json.dumps({
                    "timestamp": time.time(),
                    "data": robots
                })
                
                # 使用异步任务发送消息，避免阻塞
                for connection in list(active_connections):
                    try:
                        await connection.send_text(message)
                    except WebSocketDisconnect:
                        # 移除无效连接
                        active_connections.discard(connection)
            
            # 控制广播频率
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"广播机器人状态时出错: {e}")
            await asyncio.sleep(1)  # 出错时暂停一段时间

@app.websocket("/ws/robot-status")
async def websocket_robot_status(websocket: WebSocket):
    """机器人状态WebSocket接口"""
    # 接受WebSocket连接
    await websocket.accept()
    
    # 将连接添加到活跃连接集合
    active_connections.add(websocket)
    
    try:
        # 发送初始机器人状态数据
        robot_status = r.hgetall(f"{rdstag}:ROBOT_STATUS")
        robots = {}
        for robot_id, status_json in robot_status.items():
            robot_id_str = robot_id.decode("utf-8")
            try:
                status = json.loads(status_json.decode("utf-8"))
                robots[robot_id_str] = status
            except json.JSONDecodeError:
                continue
        
        await websocket.send_text(json.dumps({
            "timestamp": time.time(),
            "data": robots
        }))
        
        # 保持连接，接收心跳或其他消息
        while True:
            try:
                # 接收客户端消息（用于心跳检测）
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # 发送心跳响应
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
            except WebSocketDisconnect:
                raise
            except Exception:
                # 忽略其他错误
                continue
                
    except WebSocketDisconnect:
        # 客户端断开连接
        active_connections.discard(websocket)
    except Exception as e:
        print(f"WebSocket连接出错: {e}")
        active_connections.discard(websocket)
        await websocket.close()

@app.on_event("startup")
async def startup_event():
    """应用启动时的事件处理"""
    # 启动广播任务
    asyncio.create_task(broadcast_robot_status())

# 根路径路由，提供SPA入口文件
@app.get("/")
async def root():
    """提供SPA入口文件"""
    index_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "AGV Monitor API", "websocket_endpoint": "/ws/robot-status"}

# 添加404错误处理，返回index.html以支持SPA路由
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """处理404错误，返回index.html以支持SPA路由"""
    index_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Not found"}

def run_api_server():
    """运行FastAPI WebSocket服务器"""
    import uvicorn
    uvicorn.run("backend.app:app", **cfg.get("web"))
