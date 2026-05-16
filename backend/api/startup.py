import asyncio
import json
import threading

from fastapi import FastAPI

from backend.api.other import cleanup_expired_files
from backend.api.rcmsapi import rapi
from backend.api.websocket import broadcast_robot_status, start_zeromq_management_task
from util.config import cfg
from util.gossip import get_local_info, get_node, stop_default

# 通知桥接：gossip 线程 -> asyncio WebSocket 广播
gossip_notification_queue: asyncio.Queue = asyncio.Queue(maxsize=200)


def _on_gossip_notification(notif: dict):
    """由 gossip 接收线程调用，将通知入队到 asyncio 侧。"""
    try:
        gossip_notification_queue.put_nowait(
            {"type": "gossip_notification", "data": notif}
        )
    except asyncio.QueueFull:
        pass


def _on_bssid_map_changed(entries: list[dict]):
    """由 gossip 线程调用，将 BSSID 地图变更入队到 asyncio 侧。"""
    try:
        gossip_notification_queue.put_nowait(
            {"type": "bssid_map_update", "data": {"entries": entries}}
        )
    except asyncio.QueueFull:
        pass


async def _broadcast_gossip_notifications():
    """asyncio 后台任务：从队列读取消息并广播到所有 WebSocket 客户端。"""
    from backend.api.gossip import gossip_manager
    while True:
        try:
            msg = await gossip_notification_queue.get()
            payload = json.dumps(msg)
            await gossip_manager.broadcast_to_all(payload)
        except asyncio.CancelledError:
            break
        except Exception:
            pass


async def _broadcast_gossip_state():
    """asyncio 后台任务：每 3 秒推送节点列表和本机信息。"""
    from backend.api.gossip import gossip_manager
    while True:
        try:
            await asyncio.sleep(3)
            node = get_node()
            # 本机信息（含客户端列表）
            local = get_local_info(node._hostname, node._node_id)
            with node._clients_lock:
                local["extra"]["clients"] = list(node._connected_clients)
            await gossip_manager.broadcast_to_all(json.dumps({
                "type": "local_info_update",
                "data": local,
            }))
            # BSSID 位置映射
            await gossip_manager.broadcast_to_all(json.dumps({
                "type": "bssid_map_update",
                "data": {"entries": node.get_bssid_map()},
            }))
            # 在线节点
            peers_data = [
                {
                    "node_id": p.node_id,
                    "hostname": p.hostname,
                    "ip": p.ip,
                    "ssid": p.ssid,
                    "bssid": p.bssid,
                    "rx_rate": p.rx_rate,
                    "tx_rate": p.tx_rate,
                    "signal": p.signal,
                    "rssi": p.rssi,
                    "web_port": p.web_port,
                    "version": p.version,
                    "build_time": p.build_time,
                    "git_hash": p.git_hash,
                    "age": round(p.age, 1),
                    "extra": p.extra,
                }
                for p in node.peers
            ]
            await gossip_manager.broadcast_to_all(json.dumps({
                "type": "peer_list_update",
                "data": {"peers": peers_data},
            }))
        except asyncio.CancelledError:
            break
        except Exception:
            pass


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

        # 启动 gossip 节点（独立线程）
        threading.Thread(
            target=lambda: get_node(),
            daemon=True,
            name="gossip-main",
        ).start()

        # 注册通知回调和广播任务
        def _wire_gossip():
            import time as _time
            _time.sleep(0.5)  # 等待 gossip 线程启动
            node = get_node()
            node.on_notification = _on_gossip_notification
            node.on_bssid_map_changed = _on_bssid_map_changed

        threading.Thread(target=_wire_gossip, daemon=True, name="gossip-wire").start()

        notif_task = asyncio.create_task(_broadcast_gossip_notifications())
        notif_task.set_name("gossip-notification-broadcast")

        state_task = asyncio.create_task(_broadcast_gossip_state())
        state_task.set_name("gossip-state-broadcast")

    @app.on_event("shutdown")
    async def shutdown_event():
        stop_default()
