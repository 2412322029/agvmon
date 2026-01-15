import asyncio
import json
import time
from typing import Set

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from util.logger import logger

# 存储所有活跃的WebSocket连接
active_connections: Set[WebSocket] = set()

async def broadcast_robot_status(redis_client, rdstag):
    """广播机器人状态数据到所有连接的客户端"""
    while True:
        try:
            # 从Redis获取所有机器人状态
            robot_status = redis_client.hgetall(f"{rdstag}:ROBOT_STATUS")
            
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

async def websocket_robot_status_endpoint(websocket: WebSocket, redis_client, rdstag):
    """机器人状态WebSocket接口"""
    # 接受WebSocket连接
    await websocket.accept()
    
    # 将连接添加到活跃连接集合
    active_connections.add(websocket)
    # 有新连接时，更新活动时间并启动ZeroMQ进程
    print(f"新的WebSocket连接，当前连接数: {len(active_connections)}")
    
    try:
        # 发送初始机器人状态数据
        robot_status = redis_client.hgetall(f"{rdstag}:ROBOT_STATUS")
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
                # 收到消息时更新活动时间
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
        print(f"WebSocket连接断开，当前连接数: {len(active_connections)}")
        # 当没有连接时，设置最后活动时间
        if not active_connections:
            print("所有WebSocket连接已断开，启动空闲超时计时器")
    except Exception as e:
        print(f"WebSocket连接出错: {e}")
        active_connections.discard(websocket)
        print(f"WebSocket连接异常断开，当前连接数: {len(active_connections)}")
        # 当没有连接时，设置最后活动时间
        if not active_connections:
            print("所有WebSocket连接已断开，启动空闲超时计时器")
        await websocket.close()