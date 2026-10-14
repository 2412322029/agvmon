"""TCP 调试客户端 —— 供「管理 → TCP 客户端」页面使用的后台连接管理。

浏览器通过 REST + WebSocket 操作后端维护的原始 TCP 连接：
连接任意 ``host:port``、以文本或 HEX 方式收发、查看收发记录。

设计要点：

- 每个连接是一个 :class:`TcpSession`（asyncio 流），由 :data:`tcp_clients`
  全局注册表持有，按 ``id`` 索引；
- 每个会话维护一份环形收发记录（默认 500 条），并通过 ``asyncio.Queue``
  向 WebSocket 订阅者实时推送事件；
- 所有读写都在同一事件循环内完成，无需额外加锁。

配置项（``config.toml``，缺省时使用内置默认值）::

    [tcp_client]
    max_sessions = 8          # 最多同时保持的会话数
    max_log_entries = 500     # 每会话收发记录条数上限
    max_preview_bytes = 2048  # 单条记录最多展示的字节数
    connect_timeout = 8.0     # 连接超时（秒）
    reconnect_delay = 3.0     # 自动重连间隔（秒）
    allow_hosts = []          # 非空时只允许连接列表内的主机
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import uuid
from collections import deque
from datetime import datetime

from util.core.config import cfg
from util.core.logger import logger

# ---- 默认参数 ----
DEFAULT_MAX_SESSIONS = 8
DEFAULT_MAX_LOG_ENTRIES = 500
DEFAULT_MAX_PREVIEW_BYTES = 2048
DEFAULT_CONNECT_TIMEOUT = 8.0
DEFAULT_RECONNECT_DELAY = 3.0
RECV_CHUNK = 4096

# 会话状态
STATE_IDLE = "idle"
STATE_CONNECTING = "connecting"
STATE_CONNECTED = "connected"
STATE_CLOSED = "closed"
STATE_ERROR = "error"

# 记录方向
DIR_TX = "tx"
DIR_RX = "rx"
DIR_SYS = "sys"

_HEX_SEPARATORS = re.compile(r"0[xX]|[\s,;:_\-]+")


class TcpClientError(Exception):
    """TCP 客户端操作异常（用于向前端返回可读错误）。"""


def _cfg_number(key: str, default, cast=float):
    """从配置读取数值，缺失或非法时回退默认值。"""
    try:
        value = cfg.get(key)
        return cast(value) if value is not None else default
    except Exception:
        return default


def _cfg_allow_hosts() -> list[str]:
    hosts = cfg.get("tcp_client.allow_hosts")
    if not hosts:
        return []
    return [str(h) for h in hosts]


def now_ts() -> str:
    """毫秒精度时间戳，用于前端日志行。"""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def to_hex(data: bytes) -> str:
    """字节转带空格的大写 HEX 字符串。"""
    return data.hex(" ").upper()


def parse_hex_payload(text: str) -> bytes:
    """解析 HEX 文本为字节。

    兼容 ``01 02 FF`` / ``0102ff`` / ``0x01,0x02`` 等写法。
    """
    cleaned = _HEX_SEPARATORS.sub("", text or "")
    if not cleaned:
        raise TcpClientError("HEX 数据为空")
    if len(cleaned) % 2:
        raise TcpClientError("HEX 字符个数必须为偶数")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise TcpClientError(f"非法的 HEX 数据: {exc}") from exc


def build_payload(
    data: str,
    mode: str = "text",
    encoding: str = "utf-8",
    newline: str = "",
) -> bytes:
    """把前端提交的内容转换成待发送的字节。"""
    if mode == "hex":
        payload = parse_hex_payload(data)
    else:
        try:
            payload = (data or "").encode(encoding or "utf-8")
        except LookupError as exc:
            raise TcpClientError(f"未知的编码: {encoding}") from exc
        except UnicodeEncodeError as exc:
            raise TcpClientError(f"内容无法用 {encoding} 编码: {exc}") from exc

    if newline == "crlf":
        payload += b"\r\n"
    elif newline == "lf":
        payload += b"\n"
    elif newline == "cr":
        payload += b"\r"
    return payload


class TcpSession:
    """一条 TCP 连接的会话。

    连接、收发与记录都在 asyncio 事件循环内完成；``_subscribers`` 中的队列
    由 WebSocket 端点消费，用于把收发记录实时推送给前端。
    """

    def __init__(
        self,
        host: str,
        port: int,
        name: str | None = None,
        encoding: str = "utf-8",
        auto_reconnect: bool = False,
        max_log_entries: int | None = None,
        max_preview_bytes: int | None = None,
        connect_timeout: float | None = None,
        reconnect_delay: float | None = None,
    ):
        self.id = uuid.uuid4().hex[:12]
        self.host = host
        self.port = int(port)
        self.name = (name or "").strip() or f"{host}:{port}"
        self.encoding = encoding or "utf-8"
        self.auto_reconnect = bool(auto_reconnect)

        self.max_log_entries = int(
            max_log_entries or _cfg_number("tcp_client.max_log_entries", DEFAULT_MAX_LOG_ENTRIES, int)
        )
        self.max_preview_bytes = int(
            max_preview_bytes
            or _cfg_number("tcp_client.max_preview_bytes", DEFAULT_MAX_PREVIEW_BYTES, int)
        )
        self.connect_timeout = float(
            connect_timeout
            if connect_timeout is not None
            else _cfg_number("tcp_client.connect_timeout", DEFAULT_CONNECT_TIMEOUT, float)
        )
        self.reconnect_delay = float(
            reconnect_delay
            if reconnect_delay is not None
            else _cfg_number("tcp_client.reconnect_delay", DEFAULT_RECONNECT_DELAY, float)
        )

        self.state = STATE_IDLE
        self.last_error = ""
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.connected_at: str | None = None
        self.last_activity: str | None = None
        self.bytes_sent = 0
        self.bytes_recv = 0
        self.tx_count = 0
        self.rx_count = 0
        self._peer = ""

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._recv_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._intentional_close = False

        self._log: deque[dict] = deque(maxlen=self.max_log_entries)
        self._seq = 0
        self._subscribers: list[asyncio.Queue] = []

    # ------------------------------------------------------------------
    # 状态与记录
    # ------------------------------------------------------------------
    def _set_state(self, state: str, note: str | None = None) -> None:
        self.state = state
        if state == STATE_CONNECTED:
            self.connected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.last_error = ""
        elif state == STATE_ERROR and note:
            self.last_error = note
        self._publish(
            {
                "type": "state",
                "state": self.state,
                "note": note or "",
                "stats": self.stats(),
            }
        )

    def _append(
        self,
        direction: str,
        data: bytes | None = None,
        note: str = "",
    ) -> dict:
        """写入一条收发记录（有界缓冲）并推送给订阅者。"""
        entry = {
            "seq": self._next_seq(),
            "ts": now_ts(),
            "direction": direction,
            "size": len(data) if data is not None else 0,
            "hex": "",
            "text": "",
            "note": note,
        }
        if data is not None:
            preview = data[: self.max_preview_bytes]
            entry["hex"] = to_hex(preview)
            entry["text"] = preview.decode(self.encoding, errors="replace")
            if len(preview) < len(data):
                entry["note"] = f"（仅显示前 {len(preview)} 字节，共 {len(data)} 字节）"
        self._log.append(entry)
        self.last_activity = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._publish({"type": "log", "entry": entry})
        return entry

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _publish(self, event: dict) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # 订阅者来不及消费：丢弃最旧事件，保证连接不被阻塞
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)

    # ---- 订阅（WebSocket）----
    def subscribe(self, maxsize: int = 500) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    # ------------------------------------------------------------------
    # 连接生命周期
    # ------------------------------------------------------------------
    async def connect(self) -> None:
        """建立连接；失败时抛出 :class:`TcpClientError`。"""
        if self.state == STATE_CONNECTED:
            raise TcpClientError("该会话已处于连接状态")
        if self.state == STATE_CONNECTING:
            raise TcpClientError("该会话正在连接中")

        await self._stop_reconnect_loop()
        self._intentional_close = False
        self._set_state(STATE_CONNECTING, f"正在连接 {self.host}:{self.port} …")
        self._append(DIR_SYS, None, f"正在连接 {self.host}:{self.port} …")

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.connect_timeout,
            )
        except asyncio.TimeoutError as exc:
            message = f"连接超时（{self.connect_timeout:.1f}s）"
            self._append(DIR_SYS, None, message)
            self._set_state(STATE_ERROR, message)
            raise TcpClientError(message) from exc
        except Exception as exc:
            message = f"连接失败: {exc}"
            self._append(DIR_SYS, None, message)
            self._set_state(STATE_ERROR, message)
            raise TcpClientError(message) from exc

        self._reader = reader
        self._writer = writer
        sock = writer.get_extra_info("socket")
        try:
            local = sock.getsockname() if sock else None
        except Exception:
            local = None
        self._peer = f"{local[0]}:{local[1]}" if local else ""

        self._set_state(STATE_CONNECTED, f"已连接 {self.host}:{self.port}")
        self._append(DIR_SYS, None, f"已连接 {self.host}:{self.port}")
        self._recv_task = asyncio.create_task(self._recv_loop())
        self._recv_task.set_name(f"tcp-recv-{self.id}")

    async def disconnect(self, note: str = "已主动断开连接") -> None:
        """主动断开（不会触发自动重连）。"""
        self._intentional_close = True
        await self._stop_reconnect_loop()

        task = self._recv_task
        self._recv_task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

        await self._close_streams()

        was_open = self.state in (STATE_CONNECTED, STATE_CONNECTING)
        self._set_state(STATE_CLOSED, note)
        if was_open:
            self._append(DIR_SYS, None, note)
        self._intentional_close = False

    async def _recv_loop(self) -> None:
        reason = "对端已关闭连接"
        try:
            while True:
                chunk = await self._reader.read(RECV_CHUNK)
                if not chunk:
                    break
                self.bytes_recv += len(chunk)
                self.rx_count += 1
                self._append(DIR_RX, chunk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            reason = f"接收异常: {exc}"

        # 走到这里说明连接已结束（读返回空或出错）
        if self._recv_task is asyncio.current_task():
            self._recv_task = None
        await self._close_streams()
        if self._intentional_close:
            return

        self._append(DIR_SYS, None, f"连接已断开：{reason}")
        if self.auto_reconnect:
            self._set_state(STATE_CLOSED, f"连接已断开：{reason}，将自动重连")
            self._schedule_reconnect()
        else:
            self._set_state(STATE_CLOSED, f"连接已断开：{reason}")

    async def _close_streams(self) -> None:
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is None:
            return
        with contextlib.suppress(Exception):
            writer.close()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(writer.wait_closed(), timeout=3)

    # ---- 自动重连 ----
    def _schedule_reconnect(self) -> None:
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())
        self._reconnect_task.set_name(f"tcp-reconnect-{self.id}")

    async def _reconnect_loop(self) -> None:
        try:
            while self.auto_reconnect and self.state != STATE_CONNECTED:
                await asyncio.sleep(self.reconnect_delay)
                if not self.auto_reconnect or self.state == STATE_CONNECTED:
                    return
                self._append(
                    DIR_SYS, None, f"{self.reconnect_delay:.1f}s 后自动重连 …"
                )
                # 先置空：否则 connect() 内部会把这个（当前）任务取消掉
                self._reconnect_task = None
                try:
                    await self.connect()
                    return
                except TcpClientError:
                    self._reconnect_task = asyncio.current_task()
                    continue
        except asyncio.CancelledError:
            raise
        finally:
            if self._reconnect_task is asyncio.current_task():
                self._reconnect_task = None

    async def _stop_reconnect_loop(self) -> None:
        task = self._reconnect_task
        self._reconnect_task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------
    async def send(self, payload: bytes) -> int:
        """把字节写入连接，返回发送字节数。"""
        if self.state != STATE_CONNECTED or self._writer is None:
            raise TcpClientError("连接未建立，请先连接")
        if not payload:
            raise TcpClientError("发送内容为空")

        try:
            self._writer.write(payload)
            await self._writer.drain()
        except Exception as exc:
            message = f"发送失败: {exc}"
            self._append(DIR_SYS, None, message)
            self._set_state(STATE_ERROR, message)
            raise TcpClientError(message) from exc

        self.bytes_sent += len(payload)
        self.tx_count += 1
        self._append(DIR_TX, payload)
        return len(payload)

    async def send_text(
        self,
        data: str,
        mode: str = "text",
        newline: str = "",
        encoding: str | None = None,
    ) -> int:
        """按前端的文本/HEX 参数组装并发送。"""
        payload = build_payload(
            data,
            mode=mode,
            encoding=encoding or self.encoding,
            newline=newline,
        )
        return await self.send(payload)

    # ------------------------------------------------------------------
    # 记录查询 / 快照
    # ------------------------------------------------------------------
    def log_entries(self, after_seq: int = 0, limit: int | None = None) -> list[dict]:
        entries = [e for e in self._log if e["seq"] > after_seq]
        if limit:
            entries = entries[-limit:]
        return entries

    def clear_log(self) -> None:
        self._log.clear()
        self._publish({"type": "cleared"})

    def stats(self) -> dict:
        return {
            "bytes_sent": self.bytes_sent,
            "bytes_recv": self.bytes_recv,
            "tx_count": self.tx_count,
            "rx_count": self.rx_count,
        }

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "state": self.state,
            "encoding": self.encoding,
            "auto_reconnect": self.auto_reconnect,
            "created_at": self.created_at,
            "connected_at": self.connected_at,
            "last_activity": self.last_activity,
            "last_error": self.last_error,
            "local": self._peer,
            "log_count": len(self._log),
            "last_seq": self._seq,
            "subscribers": self.subscriber_count,
            **self.stats(),
        }

    async def close(self) -> None:
        """从注册表移除前的彻底清理。"""
        self.auto_reconnect = False
        with contextlib.suppress(Exception):
            await self.disconnect("会话已删除")
        self._subscribers.clear()


class TcpClientManager:
    """全局会话注册表。"""

    def __init__(self) -> None:
        self._sessions: dict[str, TcpSession] = {}

    @property
    def max_sessions(self) -> int:
        return _cfg_number("tcp_client.max_sessions", DEFAULT_MAX_SESSIONS, int)

    def create(
        self,
        host: str,
        port: int,
        name: str | None = None,
        encoding: str = "utf-8",
        auto_reconnect: bool = False,
    ) -> TcpSession:
        host = (host or "").strip()
        if not host:
            raise TcpClientError("主机地址不能为空")
        try:
            port = int(port)
        except (TypeError, ValueError) as exc:
            raise TcpClientError("端口必须是数字") from exc
        if not 0 < port < 65536:
            raise TcpClientError("端口范围应为 1-65535")

        allow_hosts = _cfg_allow_hosts()
        if allow_hosts and host not in allow_hosts:
            raise TcpClientError(f"主机 {host} 不在 tcp_client.allow_hosts 白名单内")

        if len(self._sessions) >= self.max_sessions:
            raise TcpClientError(f"会话数已达上限（{self.max_sessions}），请先删除不用的会话")

        session = TcpSession(
            host,
            port,
            name=name,
            encoding=encoding,
            auto_reconnect=auto_reconnect,
        )
        self._sessions[session.id] = session
        logger.info(f"TCP 客户端新建会话 {session.name} ({session.id})")
        return session

    def get(self, session_id: str) -> TcpSession | None:
        return self._sessions.get(session_id)

    def require(self, session_id: str) -> TcpSession:
        session = self.get(session_id)
        if session is None:
            raise TcpClientError(f"会话不存在: {session_id}")
        return session

    def list(self) -> list[dict]:
        return [s.snapshot() for s in self._sessions.values()]

    async def remove(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        await session.close()
        logger.info(f"TCP 客户端删除会话 {session.name} ({session_id})")
        return True

    async def close_all(self) -> None:
        for session_id in list(self._sessions):
            with contextlib.suppress(Exception):
                await self.remove(session_id)


# 全局注册表：REST 与 WebSocket 端点共用
tcp_clients = TcpClientManager()
