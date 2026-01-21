import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Set

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from util.config import cfg

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import api.rcmsapi as rcmsapi

active_connections: Set[WebSocket] = set()

last_websocket_activity = datetime.now()

# 跟踪ZeroMQ进程是否已经因为超时而停止
zeromq_stopped_due_to_timeout = False


async def start_zeromq_management_task():
    """启动ZeroMQ进程管理定时任务"""
    global last_websocket_activity, zeromq_stopped_due_to_timeout
    timeout = cfg.get("zmq_auto_kill_timedelta")
    print(f"ZeroMQ自动关闭超时时间: {timeout} 分钟")
    while True:
        try:
            await asyncio.sleep(10)

            idle_time = datetime.now() - last_websocket_activity
            has_active_websocket = len(active_connections) > 0

            should_stop_due_to_idle = (
                idle_time > timedelta(minutes=timeout)
                and not has_active_websocket
            )

            effective_has_active_websocket = not should_stop_due_to_idle

            try:
                rcmsapi.check_and_manage_zeromq_process(effective_has_active_websocket)
                if should_stop_due_to_idle:
                    if not zeromq_stopped_due_to_timeout:
                        print(
                            f"系统已空闲 {idle_time.total_seconds() / 60:.1f} 分钟且无活跃连接，停止ZeroMQ进程"
                        )
                        zeromq_stopped_due_to_timeout = True
                else:
                    # 如果有活跃连接或连接刚恢复，重置标志
                    if zeromq_stopped_due_to_timeout:
                        zeromq_stopped_due_to_timeout = False
            except Exception as e:
                print(f"定时检查管理ZeroMQ进程时出错: {e}")

        except Exception as e:
            print(f"ZeroMQ管理任务出错: {e}")
            await asyncio.sleep(10)


async def broadcast_robot_status(redis_client, rdstag):
    """广播机器人状态数据到所有连接的客户端"""
    while True:
        try:
            robot_status = redis_client.hgetall(f"{rdstag}:ROBOT_STATUS")

            robots = {}
            for robot_id, status_json in robot_status.items():
                robot_id_str = robot_id.decode("utf-8")
                try:
                    status = json.loads(status_json.decode("utf-8"))
                    robots[robot_id_str] = status
                except json.JSONDecodeError:
                    continue

            if robots:
                message = json.dumps({"timestamp": time.time(), "data": robots})

                for connection in list(active_connections):
                    try:
                        await connection.send_text(message)
                    except WebSocketDisconnect:
                        active_connections.discard(connection)

            await asyncio.sleep(1)

        except Exception as e:
            print(f"广播机器人状态时出错: {e}")
            await asyncio.sleep(1)


async def websocket_robot_status_endpoint(websocket: WebSocket, redis_client, rdstag):
    """机器人状态WebSocket接口"""
    await websocket.accept()

    active_connections.add(websocket)

    global last_websocket_activity
    last_websocket_activity = datetime.now()

    # 检查并确保ZeroMQ进程已启动
    global zeromq_stopped_due_to_timeout
    zeromq_stopped_due_to_timeout = False  # 重置超时标志
    
    try:
        result = rcmsapi.check_and_manage_zeromq_process(True)  # 有活动连接
        print(f"新的WebSocket连接，当前连接数: {len(active_connections)}")
        print(f"ZeroMQ进程状态: {result['message']}")
    except Exception as e:
        print(f"管理ZeroMQ进程时出错: {e}")

    try:
        robot_status = redis_client.hgetall(f"{rdstag}:ROBOT_STATUS")
        robots = {}
        for robot_id, status_json in robot_status.items():
            robot_id_str = robot_id.decode("utf-8")
            try:
                status = json.loads(status_json.decode("utf-8"))
                robots[robot_id_str] = status
            except json.JSONDecodeError:
                continue

        await websocket.send_text(
            json.dumps({"timestamp": time.time(), "data": robots})
        )

        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
                last_websocket_activity = datetime.now()
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
            except WebSocketDisconnect:
                raise
            except Exception:
                continue

    except WebSocketDisconnect:
        active_connections.discard(websocket)
        print(f"WebSocket连接断开，当前连接数: {len(active_connections)}")

        if len(active_connections) > 0:
            last_websocket_activity = datetime.now()
        else:
            # 所有连接都断开了，不需要重置标志，让定时任务处理超时
            pass

    except Exception as e:
        print(f"WebSocket连接出错: {e}")
        active_connections.discard(websocket)
        print(f"WebSocket连接异常断开，当前连接数: {len(active_connections)}")

        if len(active_connections) > 0:
            last_websocket_activity = datetime.now()

        await websocket.close()
