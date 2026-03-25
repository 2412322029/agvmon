import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta

import orjson
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from backend.api import rcmsapi
from util.config import cfg, r

logger = logging.getLogger(__name__)

WEBSOCKET_CONNECTIONS_KEY = "websocket_connections"

redis_client = None
local_connections: dict[WebSocket, str] = {}


def ws_add_connection(ws: WebSocket) -> str:
    conn_id = str(uuid.uuid4())
    conn_data = {
        "id": conn_id,
        "connect_time": datetime.now().isoformat(),
        "client_host": ws.client.host if ws.client else "",
        "client_port": ws.client.port if ws.client else 0,
        "user_agent": ws.headers.get("user-agent", ""),
    }
    r.hset(WEBSOCKET_CONNECTIONS_KEY, conn_id, orjson.dumps(conn_data))
    r.expire(WEBSOCKET_CONNECTIONS_KEY, 60)
    local_connections[ws] = conn_id
    return conn_id


def ws_remove_connection(conn_id: str):
    r.hdel(WEBSOCKET_CONNECTIONS_KEY, conn_id)


def ws_get_connection_count() -> int:
    return r.hlen(WEBSOCKET_CONNECTIONS_KEY)


def ws_get_all_connections() -> dict:
    connections = r.hgetall(WEBSOCKET_CONNECTIONS_KEY)
    result = {}
    for conn_id, data in connections.items():
        conn_id_str = conn_id.decode("utf-8")
        try:
            data_dict = orjson.loads(data.decode("utf-8"))
            data_dict["connect_time"] = datetime.fromisoformat(
                data_dict["connect_time"]
            )
            result[conn_id_str] = data_dict
        except (orjson.JSONDecodeError, ValueError):
            continue
    return result


def ws_detail_gen():
    connections = ws_get_all_connections()
    ret = []
    for conn_id, data in connections.items():
        connect_time = data.get("connect_time", "")
        if isinstance(connect_time, datetime):
            connect_time = connect_time.strftime("%Y-%m-%d %H:%M:%S")
        ret.append(
            {
                "conn_id": conn_id[:8],
                "client_state": "CONNECTED",
                "host:port": f"{data.get('client_host', '')}:{data.get('client_port', '')}",
                "ua": data.get("user_agent", ""),
                "connect_time": connect_time,
            }
        )
    return ret


def ws_safe_remove(ws: WebSocket, conn_id: str):
    try:
        ws_remove_connection(conn_id)
    except Exception:
        pass


def ws_refresh_connection(conn_id: str):
    r.expire(WEBSOCKET_CONNECTIONS_KEY, 60)


def del_without_error(websocket):
    try:
        del local_connections[websocket]
    except Exception:
        pass


last_websocket_activity = datetime.now()

# 跟踪ZeroMQ进程是否已经因为超时而停止
zeromq_stopped_due_to_timeout = False


async def start_zeromq_management_task():
    """启动ZeroMQ进程管理定时任务"""
    global last_websocket_activity, zeromq_stopped_due_to_timeout
    timeout = cfg.get("zmq_auto_kill_timedelta")
    while True:
        try:
            await asyncio.sleep(10)

            idle_time = datetime.now() - last_websocket_activity
            has_active_websocket = ws_get_connection_count() > 0

            should_stop_due_to_idle = (
                idle_time > timedelta(minutes=timeout) and not has_active_websocket
            )

            try:
                rcmsapi.check_and_manage_zeromq_process(
                    has_active_websocket, timeout=idle_time > timedelta(minutes=timeout)
                )
                if should_stop_due_to_idle:
                    if not zeromq_stopped_due_to_timeout:
                        print(
                            f"系统已空闲 {idle_time.total_seconds() / 60:.1f} 分钟且无活跃连接，停止ZeroMQ进程"
                        )
                        zeromq_stopped_due_to_timeout = True
                else:
                    if zeromq_stopped_due_to_timeout:
                        zeromq_stopped_due_to_timeout = False
            except Exception as e:
                print(f"定时检查管理ZeroMQ进程时出错: {e}")

        except Exception as e:
            print(f"ZeroMQ管理任务出错: {e}")
            await asyncio.sleep(10)


async def broadcast_robot_status(rdstag):
    """广播机器人状态数据到所有连接的客户端"""
    while True:
        try:
            robot_status = r.hgetall(f"{rdstag}:ROBOT_STATUS")
            robots = {}
            if robot_status:
                robot_ids = [robot_id.decode("utf-8") for robot_id in robot_status.keys()]
                task_info_keys = [f"{rdstag}:TASK_INFO_REQ:{rid}" for rid in robot_ids]
                robot_path_keys = [f"{rdstag}:ROBOT_PATH:{rid}" for rid in robot_ids]
                block_cell_keys = [f"{rdstag}:TRP_BLOCK_CELL:{rid}" for rid in robot_ids]
                
                task_info_results = r.mget(task_info_keys)
                robot_path_results = r.mget(robot_path_keys)
                block_cell_results = r.mget(block_cell_keys)
                
                for idx, (robot_id, status_json) in enumerate(robot_status.items()):
                    robot_id_str = robot_id.decode("utf-8")
                    try:
                        status = orjson.loads(status_json.decode("utf-8"))
                        robots[robot_id_str] = status
                        robots[robot_id_str].update(
                            {
                                "taskinfo": orjson.loads(
                                    (task_info_results[idx] or b"").decode("utf-8")
                                ),
                                "paths": orjson.loads(
                                    (robot_path_results[idx] or b"").decode("utf-8")
                                ),
                                "block_cell": orjson.loads(
                                    (block_cell_results[idx] or b"").decode("utf-8")
                                ),
                            }
                        )
                    except orjson.JSONDecodeError:
                        continue

            if robots:
                message = orjson.dumps(
                    {
                        "type": "ROBOT_STATUS",
                        "timestamp": time.time(),
                        # "task": taskinfo,
                        "data": robots,
                        "active_connections": ws_get_connection_count(),
                        "active_connections_detail": ws_detail_gen(),
                    }
                ).decode("utf-8")

                for ws in list(local_connections.keys()):
                    try:
                        await ws.send_text(message)
                    except Exception:
                        conn_id = local_connections.get(ws)
                        if conn_id:
                            ws_safe_remove(ws, conn_id)
                            del_without_error(ws)

            await asyncio.sleep(1)

        except Exception as e:
            logger.fatal(f"广播机器人状态时出错: {e}")
            raise e


async def websocket_robot_status_endpoint(websocket: WebSocket, rdstag):
    """机器人状态WebSocket接口"""
    await websocket.accept()

    conn_id = ws_add_connection(websocket)
    global last_websocket_activity
    last_websocket_activity = datetime.now()
    global zeromq_stopped_due_to_timeout
    zeromq_stopped_due_to_timeout = False

    try:
        result = rcmsapi.check_and_manage_zeromq_process(True)
        print(f"新的WebSocket连接，当前连接数: {ws_get_connection_count()}")
        print(f"ZeroMQ进程状态: {result['message']}")
    except Exception as e:
        print(f"管理ZeroMQ进程时出错: {e}")

    try:
        # robot_status = r.hgetall(f"{rdstag}:ROBOT_STATUS")
        # robots = {}
        # for robot_id, status_json in robot_status.items():
        #     robot_id_str = robot_id.decode("utf-8")
        #     try:
        #         status = orjson.loads(status_json.decode("utf-8"))
        #         robots[robot_id_str] = status
        #     except orjson.JSONDecodeError:
        #         continue

        # await websocket.send_text(
        #     orjson.dumps({"timestamp": time.time(), "data": robots}).decode("utf-8")
        # )

        while True:
            try:
                rsv = await asyncio.wait_for(websocket.receive_text(), timeout=20)
                if rsv == "heartbeat":
                    last_websocket_activity = datetime.now()
                    ws_refresh_connection(conn_id)
            except asyncio.TimeoutError:
                await websocket.send_text(
                    orjson.dumps({"type": "heartbeat"}).decode("utf-8")
                )
            except WebSocketDisconnect:
                logger.info(
                    f"WebSocket连接断开，当前连接数: {ws_get_connection_count()}"
                )
                ws_safe_remove(websocket, conn_id)
                if websocket in local_connections:
                    del_without_error(websocket)
                break
            except Exception as e:
                logger.error(f"接收WebSocket消息时出错: {e}")
                ws_safe_remove(websocket, conn_id)
                if websocket in local_connections:
                    del_without_error(websocket)
                break

    except Exception as e:
        print(f"WebSocket连接出错: {e}")
        ws_safe_remove(websocket, conn_id)
        if websocket in local_connections:
            del_without_error(websocket)
        print(f"WebSocket连接异常断开，当前连接数: {ws_get_connection_count()}")

        if ws_get_connection_count() > 0:
            last_websocket_activity = datetime.now()

        try:
            await websocket.close()
        except Exception:
            pass
