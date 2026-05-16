"""
局域网节点信息互享 — 基于 UDP 广播的简单 gossip 协议。

每个节点定期广播自己的 WiFi BSSID、SSID 和版本信息，
同时监听其他节点的广播，维护在线节点列表。
"""

import json
import logging
import platform
import re
import socket
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from util.__version__ import build_time, git_hash, version
from util.config import cfg

logger = logging.getLogger("gossip")

GOSSIP_PORT = 27777
BROADCAST_INTERVAL = 3  # 广播间隔（秒）
PEER_TTL = 15  # 对等节点超时（秒），超过此时间未收到广播则认为离线
MAX_PACKET = 2048

# ============================================================
# 本机信息采集
# ============================================================


_wifi_cache: dict = {}  # {"value": dict|None, "expires": float}


def get_wifi_info() -> dict | None:
    """获取当前连接的 WiFi SSID 和 BSSID，未连接返回 None。结果缓存 10 秒。"""
    now = time.monotonic()
    if _wifi_cache and now < _wifi_cache.get("expires", 0):
        return _wifi_cache["value"]

    system = platform.system()
    result = None
    for attempt in range(2):
        try:
            if system == "Windows":
                result = _get_wifi_windows()
            elif system == "Linux":
                result = _get_wifi_linux()
            elif system == "Darwin":
                result = _get_wifi_macos()
            break
        except subprocess.CalledProcessError:
            if attempt == 0:
                time.sleep(0.3)
            else:
                logger.debug("获取 WiFi 信息失败 (重试后)", exc_info=True)
        except Exception:
            logger.debug("获取 WiFi 信息失败", exc_info=True)
            break

    if result is not None:
        # 成功 — 缓存 10 秒
        _wifi_cache["value"] = result
        _wifi_cache["expires"] = now + 10
    elif _wifi_cache:
        # 失败但有过期缓存 — 续命 5 秒，继续用旧值
        _wifi_cache["expires"] = now + 5
        result = _wifi_cache["value"]
    # 完全无缓存且失败 → 返回 None
    return result


def _get_wifi_windows() -> dict | None:
    output = subprocess.check_output(
        ["netsh", "wlan", "show", "interfaces"],
        encoding="utf-8", errors="replace",
    )
    ssid = _re_first(r"SSID\s*:\s*(.+)", output)
    bssid = _re_first(r"BSSID\s*:\s*([0-9A-Fa-f:]{17})", output)
    if not ssid or not bssid:
        return None
    info: dict = {"ssid": ssid.strip(), "bssid": bssid.strip().upper()}
    rx_rate = _re_first(r"接收速率.*?:\s*(\d+)", output)
    tx_rate = _re_first(r"传输速率.*?:\s*(\d+)", output)
    signal_pct = _re_first(r"信号\s*:\s*(\d+)%", output)
    rssi = _re_first(r"Rssi\s*:\s*(-?\d+)", output)
    if rx_rate:
        info["rx_rate"] = int(rx_rate)
    if tx_rate:
        info["tx_rate"] = int(tx_rate)
    if signal_pct:
        info["signal"] = int(signal_pct)
    if rssi:
        info["rssi"] = int(rssi)
    return info


def _get_wifi_linux() -> dict | None:
    try:
        ssid = subprocess.check_output(
            ["iwgetid", "-r"], encoding="utf-8", errors="replace"
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        ssid = None
    try:
        result = subprocess.check_output(
            ["iw", "dev", "link"], encoding="utf-8", errors="replace"
        )
        bssid = _re_first(r"Connected to ([0-9a-f:]{17})", result)
    except (FileNotFoundError, subprocess.CalledProcessError):
        bssid = None
    if ssid or bssid:
        info: dict = {
            "ssid": ssid or "",
            "bssid": bssid.upper() if bssid else "",
        }
        try:
            rx_rate = _re_first(r"rx bitrate:\s*(\d+\.?\d*)", result)
            tx_rate = _re_first(r"tx bitrate:\s*(\d+\.?\d*)", result)
            signal_raw = _re_first(r"signal:\s*(-?\d+)", result)
            if rx_rate:
                info["rx_rate"] = int(float(rx_rate))
            if tx_rate:
                info["tx_rate"] = int(float(tx_rate))
            if signal_raw:
                info["rssi"] = int(signal_raw)
        except Exception:
            pass
        return info
    return None


def _get_wifi_macos() -> dict | None:
    try:
        output = subprocess.check_output(
            ["/System/Library/PrivateFrameworks/Apple80211.framework"
             "/Versions/Current/Resources/airport", "-I"],
            encoding="utf-8", errors="replace",
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    ssid = _re_first(r"\bSSID:\s*(.+)", output)
    bssid = _re_first(r"\bBSSID:\s*([0-9a-f:]{17})", output)
    if ssid or bssid:
        info: dict = {
            "ssid": ssid.strip() if ssid else "",
            "bssid": bssid.strip().upper() if bssid else "",
        }
        rx_rate = _re_first(r"lastTxRate:\s*(\d+)", output)
        rssi = _re_first(r"agrCtlRSSI:\s*(-?\d+)", output)
        if rx_rate:
            info["rx_rate"] = int(rx_rate)
            info["tx_rate"] = int(rx_rate)
        if rssi:
            info["rssi"] = int(rssi)
        return info
    return None


def _re_first(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text)
    return m.group(1) if m else None


def get_local_info(hostname: str | None = None, node_id: str = "") -> dict:
    """组装本节点信息，供广播使用。"""
    wifi = get_wifi_info() or {}
    web_cfg = cfg.get("web")
    return {
        "node_id": node_id,
        "hostname": hostname or socket.gethostname(),
        "ip": _primary_ip(),
        "ssid": wifi.get("ssid", ""),
        "bssid": wifi.get("bssid", ""),
        "rx_rate": wifi.get("rx_rate", 0),
        "tx_rate": wifi.get("tx_rate", 0),
        "signal": wifi.get("signal", 0),
        "rssi": wifi.get("rssi", 0),
        "web_port": web_cfg.get("port", 8000),
        "version": version,
        "build_time": build_time,
        "git_hash": git_hash,
        "extra": {},
    }


def _primary_ip() -> str:
    """获取本机首选局域网 IP。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


# ============================================================
# 对等节点记录
# ============================================================


@dataclass
class Peer:
    node_id: str
    hostname: str
    ip: str
    ssid: str = ""
    bssid: str = ""
    rx_rate: int = 0
    tx_rate: int = 0
    signal: int = 0
    rssi: int = 0
    web_port: int = 0
    version: str = ""
    build_time: str = ""
    git_hash: str = ""
    extra: dict = field(default_factory=dict)
    last_seen: float = field(default_factory=time.monotonic)

    @property
    def age(self) -> float:
        return time.monotonic() - self.last_seen

    @property
    def online(self) -> bool:
        return self.age < PEER_TTL

    def update(self, info: dict):
        self.node_id = info.get("node_id", self.node_id)
        self.hostname = info.get("hostname", self.hostname)
        self.ip = info.get("ip", self.ip)
        self.ssid = info.get("ssid", self.ssid)
        self.bssid = info.get("bssid", self.bssid)
        self.rx_rate = info.get("rx_rate", self.rx_rate)
        self.tx_rate = info.get("tx_rate", self.tx_rate)
        self.signal = info.get("signal", self.signal)
        self.rssi = info.get("rssi", self.rssi)
        self.web_port = info.get("web_port", self.web_port)
        self.version = info.get("version", self.version)
        self.build_time = info.get("build_time", self.build_time)
        self.git_hash = info.get("git_hash", self.git_hash)
        self.extra = info.get("extra", self.extra)
        self.last_seen = time.monotonic()


# ============================================================
# Gossip 节点
# ============================================================


class GossipNode:
    """UDP 广播 gossip 节点。

    使用方式::

        node = GossipNode()
        node.on_peer_update = lambda peer: print(f"发现: {peer}")
        node.start()
        ...
        node.stop()
    """

    def __init__(
        self,
        port: int = GOSSIP_PORT,
        interval: float = BROADCAST_INTERVAL,
        hostname: str | None = None,
    ):
        self._port = port
        self._interval = interval
        self._hostname = hostname
        self._node_id = uuid.uuid4().hex[:8]
        self._sock: socket.socket | None = None
        self._running = False
        self._threads: list[threading.Thread] = []
        self._peers: dict[str, Peer] = {}  # node_id -> Peer
        self._lock = threading.Lock()

        # 回调
        self.on_peer_join = None   # (peer: Peer) -> None
        self.on_peer_leave = None  # (peer: Peer) -> None
        self.on_peer_update = None  # (peer: Peer) -> None  收到任何广播都触发
        self.on_notification = None  # (notif: dict) -> None
        self.on_bssid_map_changed = None  # (entries: list[dict]) -> None

        # 通知广播
        self._notification_queue: list[dict] = []
        self._notification_lock = threading.Lock()
        self._sent_notification_ids: set[str] = set()

        # 本机 WebSocket 客户端列表
        self._connected_clients: list[dict] = []
        self._clients_lock = threading.Lock()

        # BSSID 位置映射
        self._bssid_map: dict[str, dict] = {}
        self._bssid_map_lock = threading.Lock()
        self._bssid_map_path = Path(__file__).parent / "data" / "bssid_map.json"
        self._load_bssid_map()

    # ---- 生命周期 ----

    def start(self):
        if self._running:
            return
        self._running = True
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.bind(("", self._port))
        self._sock.settimeout(1)

        rx = threading.Thread(target=self._recv_loop, daemon=True, name="gossip-rx")
        tx = threading.Thread(target=self._send_loop, daemon=True, name="gossip-tx")
        gc = threading.Thread(target=self._gc_loop, daemon=True, name="gossip-gc")
        self._threads = [rx, tx, gc]
        for t in self._threads:
            t.start()
        logger.info("gossip 已启动 port=%s", self._port)

    def stop(self):
        self._running = False
        for t in self._threads:
            t.join(timeout=3)
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._threads.clear()
        logger.info("gossip 已停止")

    # ---- 查询 ----

    @property
    def peers(self) -> list[Peer]:
        """返回当前在线的节点列表（不含本机）。"""
        with self._lock:
            return [p for p in self._peers.values() if p.online]

    def get_peers_by_bssid(self, bssid: str) -> list[Peer]:
        """返回连接到指定 BSSID 的节点。"""
        bssid = bssid.upper()
        with self._lock:
            return [
                p for p in self._peers.values()
                if p.online and p.bssid.upper() == bssid
            ]

    @property
    def same_wifi_peers(self) -> list[Peer]:
        """返回与本机连接到同一 AP (BSSID) 的节点。"""
        my_info = get_local_info(self._hostname)
        if not my_info["bssid"]:
            return []
        return self.get_peers_by_bssid(my_info["bssid"])

    # ---- 通知广播 ----

    def broadcast_notification(self, message: str, sender: str = "") -> str:
        """入队一条通知消息，返回通知 ID。"""
        notif_id = uuid.uuid4().hex[:12]
        notif = {
            "id": notif_id,
            "message": message,
            "sender": sender or self._hostname or socket.gethostname(),
            "timestamp": time.time(),
            "origin_node": self._node_id,
        }
        with self._notification_lock:
            self._notification_queue.append(notif)
        return notif_id

    def _drain_notifications(self, max_count: int = 3, max_age: float = 9.0) -> list[dict]:
        """排空过期通知，返回本轮应发送的通知列表。"""
        now = time.time()
        with self._notification_lock:
            to_send = []
            remaining = []
            for notif in self._notification_queue:
                if len(to_send) < max_count and (now - notif.get("timestamp", 0)) < max_age:
                    to_send.append(notif)
                else:
                    remaining.append(notif)
            self._notification_queue = remaining
            return to_send

    # ---- WebSocket 客户端 ----

    def set_connected_clients(self, clients: list[dict]):
        """更新本机当前连接的 WebSocket 客户端列表。每个客户端应包含 ip, ua, connected_at。"""
        with self._clients_lock:
            self._connected_clients = clients

    # ---- BSSID 位置映射 ----

    def _load_bssid_map(self):
        try:
            if self._bssid_map_path.exists():
                data = json.loads(self._bssid_map_path.read_text(encoding="utf-8"))
                self._bssid_map = {e["bssid"].upper(): e for e in data.get("entries", [])}
        except Exception:
            logger.debug("加载 BSSID 地图失败", exc_info=True)

    def _save_bssid_map(self):
        try:
            self._bssid_map_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"entries": list(self._bssid_map.values())}
            self._bssid_map_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            logger.debug("保存 BSSID 地图失败", exc_info=True)

    def _merge_bssid_map(self, entries: list[dict]):
        """合并远程 BSSID 映射条目，按 updated_at 时间戳 last-write-wins。"""
        with self._bssid_map_lock:
            changed = False
            for entry in entries:
                bssid = entry.get("bssid", "").upper()
                if not bssid:
                    continue
                existing = self._bssid_map.get(bssid)
                if existing is None or entry.get("updated_at", 0) > existing.get("updated_at", 0):
                    self._bssid_map[bssid] = entry
                    changed = True
            if changed:
                self._save_bssid_map()
                self._notify_bssid_map_changed()

    def _notify_bssid_map_changed(self):
        if self.on_bssid_map_changed:
            entries = list(self._bssid_map.values())
            try:
                self.on_bssid_map_changed(entries)
            except Exception:
                logger.debug("on_bssid_map_changed 回调异常", exc_info=True)

    def get_bssid_map(self) -> list[dict]:
        with self._bssid_map_lock:
            return list(self._bssid_map.values())

    def update_bssid_map(self, bssid: str, location: str, notes: str, updated_by: str):
        bssid = bssid.upper()
        with self._bssid_map_lock:
            self._bssid_map[bssid] = {
                "bssid": bssid,
                "location": location,
                "notes": notes,
                "updated_by": updated_by,
                "updated_at": time.time(),
            }
            self._save_bssid_map()
        self._notify_bssid_map_changed()

    def delete_bssid_map_entry(self, bssid: str) -> bool:
        bssid = bssid.upper()
        with self._bssid_map_lock:
            if bssid in self._bssid_map:
                del self._bssid_map[bssid]
                self._save_bssid_map()
                result = True
            else:
                result = False
        if result:
            self._notify_bssid_map_changed()
        return result

    # ---- 内部 ----

    def _send_loop(self):
        local_info = get_local_info(self._hostname, self._node_id)
        cycle = 0
        while self._running:
            try:
                # 每轮排空待发送通知（最多 3 条，过期 9s）
                local_info["extra"]["notifications"] = self._drain_notifications(3, 9.0)

                # 附带本机 WebSocket 客户端列表
                with self._clients_lock:
                    local_info["extra"]["clients"] = list(self._connected_clients)

                # 每 3 轮（9s）附带一次 BSSID 映射全量
                cycle += 1
                if cycle % 3 == 0:
                    with self._bssid_map_lock:
                        local_info["extra"]["bssid_map"] = list(self._bssid_map.values())
                else:
                    local_info["extra"]["bssid_map"] = []

                data = json.dumps(local_info).encode()
                if len(data) > MAX_PACKET:
                    logger.warning("gossip 数据包过大 (%d bytes)，已截断", len(data))
                    local_info["extra"]["notifications"] = []
                    local_info["extra"]["clients"] = []
                    local_info["extra"]["bssid_map"] = []
                    data = json.dumps(local_info).encode()
                self._sock.sendto(data, ("255.255.255.255", self._port))
                # 每轮重新读取本机信息（WiFi 可能切换）
                local_info = get_local_info(self._hostname, self._node_id)
            except OSError:
                logger.debug("广播发送失败", exc_info=True)
            time.sleep(self._interval)

    def _recv_loop(self):
        while self._running:
            try:
                data, addr = self._sock.recvfrom(MAX_PACKET)
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    logger.debug("接收异常", exc_info=True)
                continue

            try:
                info = json.loads(data)
            except json.JSONDecodeError:
                continue

            peer_node_id = info.get("node_id", "")
            peer_ip = info.get("ip", addr[0])

            # 忽略自己（同 node_id）
            if peer_node_id == self._node_id:
                continue

            with self._lock:
                is_new = peer_node_id not in self._peers
                if is_new:
                    str_keys = {"node_id", "hostname", "ip", "ssid", "bssid", "version", "build_time", "git_hash"}
                    int_keys = {"rx_rate", "tx_rate", "signal", "rssi", "web_port"}
                    peer_kwargs = {}
                    for k in [*str_keys, *int_keys, "extra"]:
                        if k in int_keys:
                            peer_kwargs[k] = info.get(k, 0)
                        elif k == "extra":
                            peer_kwargs[k] = info.get(k, {})
                        else:
                            peer_kwargs[k] = info.get(k, "")
                    peer = Peer(**peer_kwargs)
                    self._peers[peer_node_id] = peer
                else:
                    peer = self._peers[peer_node_id]
                    peer.update(info)

            if self.on_peer_update:
                try:
                    self.on_peer_update(peer)
                except Exception:
                    logger.debug("on_peer_update 回调异常", exc_info=True)
            if is_new and self.on_peer_join:
                try:
                    self.on_peer_join(peer)
                except Exception:
                    logger.debug("on_peer_join 回调异常", exc_info=True)

            # 提取通知
            extra = info.get("extra", {})
            notifications = extra.get("notifications", [])
            for notif in notifications:
                notif_id = notif.get("id", "")
                if notif_id and notif_id not in self._sent_notification_ids:
                    self._sent_notification_ids.add(notif_id)
                    if len(self._sent_notification_ids) > 200:
                        self._sent_notification_ids = set(list(self._sent_notification_ids)[100:])
                    if self.on_notification:
                        try:
                            self.on_notification(notif)
                        except Exception:
                            logger.debug("on_notification 回调异常", exc_info=True)

            # 合并 BSSID 映射
            bssid_map_entries = extra.get("bssid_map", [])
            if bssid_map_entries:
                self._merge_bssid_map(bssid_map_entries)

    def _gc_loop(self):
        """定期清理超时节点。"""
        while self._running:
            time.sleep(PEER_TTL / 2)
            with self._lock:
                offline = [k for k, p in self._peers.items() if not p.online]
                for k in offline:
                    peer = self._peers.pop(k)
                    if self.on_peer_leave:
                        try:
                            self.on_peer_leave(peer)
                        except Exception:
                            logger.debug("on_peer_leave 回调异常", exc_info=True)


# ============================================================
# 便捷函数
# ============================================================


_default_node: GossipNode | None = None


def get_node() -> GossipNode:
    """获取全局单例 gossip 节点（自动启动）。"""
    global _default_node
    if _default_node is None:
        _default_node = GossipNode()
        _default_node.start()
    return _default_node


def stop_default():
    global _default_node
    if _default_node:
        _default_node.stop()
        _default_node = None


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    import sys
    from threading import Event

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    node = GossipNode()

    def on_update(peer):
        print(f"[发现]{peer.node_id} {peer.hostname} ({peer.ip}) SSID={peer.ssid!r} BSSID={peer.bssid!r} "
              f"信号={peer.signal}% RSSI={peer.rssi} "
              f"rx={peer.rx_rate} tx={peer.tx_rate} "
              f"web_port={peer.web_port} v={peer.version}")

    def on_join(peer):
        print(f"[上线] {peer.node_id} {peer.hostname}")

    def on_leave(peer):
        print(f"[离线] {peer.node_id} {peer.hostname}")

    node.on_peer_update = on_update
    node.on_peer_join = on_join
    node.on_peer_leave = on_leave
    node.start()

    local = get_local_info()
    print(f"本机: {local['hostname']} ({local['ip']}) "
          f"SSID={local['ssid']!r} BSSID={local['bssid']!r} "
          f"信号={local['signal']}% RSSI={local['rssi']} "
          f"web_port={local['web_port']} v={local['version']}")

    stop_event = Event()
    try:
        print("监听中，按 Ctrl+C 退出...")
        stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n停止...")
        node.stop()
        sys.exit(0)
