import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from util.gossip import get_local_info, get_node

gossip_router = APIRouter(prefix="/gossip", tags=["gossip"])


@gossip_router.get("/local")
def get_local():
    """返回本节点信息。"""
    node = get_node()
    return get_local_info(node._hostname, node._node_id)


@gossip_router.get("/peers")
def get_peers():
    """返回在线节点列表。"""
    node = get_node()
    return {
        "peers": [
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
    }


# ---- 通知广播 ----

class NotifyRequest(BaseModel):
    message: str
    sender: str = ""


@gossip_router.post("/notify")
def send_notification(req: NotifyRequest):
    """发送通知广播到所有节点。"""
    node = get_node()
    sender = req.sender or node._hostname
    notif_id = node.broadcast_notification(req.message, sender)
    # 同时入队到本地 WebSocket 桥接队列，让本机客户端立即收到
    notif = {
        "id": notif_id,
        "message": req.message,
        "sender": sender,
        "timestamp": time.time(),
        "origin_node": node._node_id,
    }
    try:
        from backend.api.startup import gossip_notification_queue
        gossip_notification_queue.put_nowait(
            {"type": "gossip_notification", "data": notif}
        )
    except (asyncio.QueueFull, Exception):
        pass
    return {"status": "ok", "notification_id": notif_id}


# ---- BSSID 位置映射 ----

class BssidMapEntry(BaseModel):
    bssid: str
    location: str = ""
    notes: str = ""


@gossip_router.get("/bssid-map")
def get_bssid_map():
    node = get_node()
    return {"entries": node.get_bssid_map()}


@gossip_router.post("/bssid-map")
def add_or_update_bssid_map(entry: BssidMapEntry):
    node = get_node()
    node.update_bssid_map(
        bssid=entry.bssid,
        location=entry.location,
        notes=entry.notes,
        updated_by=node._hostname,
    )
    return {"status": "ok"}


@gossip_router.delete("/bssid-map/{bssid}")
def delete_bssid_map_entry(bssid: str):
    node = get_node()
    ok = node.delete_bssid_map_entry(bssid)
    return {"status": "ok" if ok else "not_found"}


# ---- WebSocket ----

def _make_client_entry(websocket: WebSocket) -> dict:
    """从 WebSocket 连接提取客户端信息。"""
    return {
        "ip": websocket.client.host if websocket.client else "",
        "ua": websocket.headers.get("user-agent", ""),
        "connected_at": time.time(),
    }


class GossipConnectionManager:
    def __init__(self):
        self.active_connections: list[dict] = []  # {ws, ip, ua, connected_at}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        entry = {
            "ws": websocket,
            **_make_client_entry(websocket),
        }
        self.active_connections.append(entry)
        self._sync_to_gossip()

    def disconnect(self, websocket: WebSocket):
        self.active_connections = [c for c in self.active_connections if c["ws"] != websocket]
        self._sync_to_gossip()

    def _sync_to_gossip(self):
        """将当前客户端列表同步到 gossip 节点。"""
        try:
            node = get_node()
            clients = [
                {"ip": c["ip"], "ua": c["ua"], "connected_at": c["connected_at"]}
                for c in self.active_connections
            ]
            node.set_connected_clients(clients)
        except Exception:
            pass

    async def broadcast_to_all(self, message: str):
        for conn in self.active_connections[:]:
            try:
                await conn["ws"].send_text(message)
            except Exception:
                self.disconnect(conn["ws"])


gossip_manager = GossipConnectionManager()


async def websocket_gossip_endpoint(websocket: WebSocket):
    """Gossip 通知 WebSocket 端点。"""
    await gossip_manager.connect(websocket)
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=25)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_text(json.dumps({"type": "heartbeat"}))
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        gossip_manager.disconnect(websocket)
