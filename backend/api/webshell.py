"""
Web Shell 终端 — xterm.js (canvas) + FastAPI WebSocket + Windows ConPTY

使用 pywinpty 伪终端 (ConPTY)，支持多会话管理:
- 每个终端会话 = 独立 PTY 进程
- 左侧会话列表，新建/切换/关闭
- 方向键历史、光标移动、Ctrl+C、Tab补全 全部原生支持
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from winpty import PtyProcess

from util.config import cfg

# ---------------------------------------------------------------------------
# PTY 读写线程池 — 避免占用 FastAPI 默认线程池
# ---------------------------------------------------------------------------

_pty_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="pty-")

# ---------------------------------------------------------------------------
# 全局开关 + 本机访问检查（config.toml → webshell）
# ---------------------------------------------------------------------------


def is_webshell_enabled() -> bool:
    """全局启用/禁用，默认禁用"""
    v = cfg.get("webshell.enabled")
    return v if v is not None else False


def _get_allowed_hosts() -> set[str]:
    hosts = cfg.get("webshell.allowed_hosts")
    if hosts and isinstance(hosts, list):
        return set(hosts)
    return {"127.0.0.1", "::1", "localhost"}


def is_localhost(request: Request | WebSocket) -> bool:
    client = request.client
    if client is None:
        return False
    return client.host in _get_allowed_hosts()


# ---------------------------------------------------------------------------
# 会话管理
# ---------------------------------------------------------------------------

_sessions: dict[str, PtyProcess] = {}
_sessions_lock = asyncio.Lock()

# 输出缓冲区 — deque 分块存储，按字节总量限制
# 每块: (timestamp, bytes)，重连回放时按序拼接
_sessions_buf: dict[str, deque[tuple[float, bytes]]] = {}
# 已清理过的字节数（避免每次重连都跑正则）
_buf_cleaned_len: dict[str, int] = {}

# 断开连接延迟清理定时器（超时则杀进程防僵尸）
_disconnect_timers: dict[str, asyncio.Task] = {}

# 每会话只允许一个活跃 WebSocket，新连接踢旧连接
_active_ws: dict[str, WebSocket] = {}
_active_client: dict[str, str] = {}  # session_id → "IP:port"

# 监控频道 — 向前端推送会话列表变更
_monitors: list[WebSocket] = []
_monitors_lock = asyncio.Lock()


async def _broadcast_sessions() -> None:
    """会话状态变更时向所有监控客户端推送完整列表"""
    data = await list_sessions()
    payload = {"type": "sessions", "sessions": data}
    async with _monitors_lock:
        dead = []
        for ws in _monitors:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _monitors.remove(ws)


def _cfg_max_sessions() -> int:
    v = cfg.get("webshell.max_sessions")
    return v if isinstance(v, int) and v > 0 else 8


def _cfg_buffer_size() -> int:
    v = cfg.get("webshell.buffer_size_kb")
    return (v if isinstance(v, int) and v > 0 else 256) * 1024


# ---------------------------------------------------------------------------
# 环形缓冲区 — deque 分块存储，按需拼接
# ---------------------------------------------------------------------------

_CLEAN_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(rb'\x1b\[[\d;]*[chlm]'), 5),       # CSI 协商序列
    (re.compile(rb'\x1b\][^\x07\x1b]*(\x07|\x1b\\)'), 3),  # OSC 序列
]


async def _append_buf(sid: str, data: bytes) -> None:
    """追加数据到环形缓冲区，自动淘汰旧数据"""
    max_size = _cfg_buffer_size()
    async with _sessions_lock:
        dq = _sessions_buf.get(sid)
        if dq is None:
            return
        dq.append((time.monotonic(), data))
        # 淘汰旧块直到总量 <= max_size
        total = sum(len(chunk) for _, chunk in dq)
        while total > max_size and len(dq) > 1:
            _, old = dq.popleft()
            total -= len(old)
            # 调整已清理偏移
            cleaned = _buf_cleaned_len.get(sid, 0)
            if cleaned > 0:
                _buf_cleaned_len[sid] = max(0, cleaned - len(old))


async def _get_buf_bytes(sid: str) -> bytes:
    """获取缓冲区的连续字节（用于重连回放）"""
    async with _sessions_lock:
        dq = _sessions_buf.get(sid)
        if not dq:
            return b''
        return b''.join(chunk for _, chunk in dq)


async def _get_buf_clean(sid: str) -> bytes:
    """获取清理后的缓冲区内容（去除终端协商序列），增量清理"""
    raw = await _get_buf_bytes(sid)
    if not raw:
        return b''
    # 只清理新增部分
    prev_cleaned = _buf_cleaned_len.get(sid, 0)
    if prev_cleaned >= len(raw):
        return raw  # 全部已清理
    new_data = raw[prev_cleaned:]
    for pattern, max_count in _CLEAN_PATTERNS:
        new_data = pattern.sub(b'', new_data, count=max_count)
    _buf_cleaned_len[sid] = len(raw)
    # 返回完整清理内容
    if prev_cleaned == 0:
        return new_data
    return raw[:prev_cleaned] + new_data


def _cfg_disconnect_timeout() -> int:
    v = cfg.get("webshell.disconnect_timeout")
    return v if isinstance(v, int) and v > 0 else 10


def _cfg_cols() -> int:
    v = cfg.get("webshell.cols")
    return v if isinstance(v, int) and v > 0 else 120


def _cfg_rows() -> int:
    v = cfg.get("webshell.rows")
    return v if isinstance(v, int) and v > 0 else 40


def _new_sid() -> str:
    """UUID 短编号，不可预测"""
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# PTY 操作
# ---------------------------------------------------------------------------


def _spawn_shell() -> PtyProcess:
    """创建带伪终端的 PowerShell 进程"""
    if sys.platform == "win32":
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        cmd = (
            'powershell.exe -NoLogo -NoProfile -NoExit -Command '
            '"$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8"'
        )
        return PtyProcess.spawn(cmd, dimensions=(_cfg_rows(), _cfg_cols()), env=env)
    else:
        raise NotImplementedError("Unix PTY 暂未实现")


async def _cleanup_proc(proc: PtyProcess) -> None:
    """确保 PTY 进程终止、句柄释放，防止僵尸进程/句柄泄漏"""
    if proc is None:
        return
    try:
        if proc.isalive():
            proc.terminate()
            await asyncio.sleep(0.3)
        proc.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 会话 CRUD
# ---------------------------------------------------------------------------


async def create_session() -> str:
    """创建新 PTY 会话，返回 session_id"""
    async with _sessions_lock:
        # 清理死进程再计数
        dead = [s for s, p in _sessions.items() if not p.isalive()]
        for s in dead:
            _sessions.pop(s, None)
            _sessions_buf.pop(s, None)
            _buf_cleaned_len.pop(s, None)
        if len(_sessions) >= _cfg_max_sessions():
            raise HTTPException(status_code=429, detail=f"终端会话数已达上限 ({_cfg_max_sessions()})")
    sid = _new_sid()
    proc = _spawn_shell()
    async with _sessions_lock:
        _sessions[sid] = proc
        _sessions_buf[sid] = deque()
        _buf_cleaned_len[sid] = 0
    asyncio.create_task(_broadcast_sessions())
    return sid


async def _get_proc(sid: str) -> PtyProcess | None:
    async with _sessions_lock:
        return _sessions.get(sid)


async def list_sessions() -> list[dict]:
    """列出所有会话，同时清理已死进程"""
    result: list[dict] = []
    async with _sessions_lock:
        dead: list[str] = []
        for sid, proc in _sessions.items():
            alive = proc.isalive()
            connected = sid in _active_ws
            result.append({
                "session_id": sid,
                "alive": alive,
                "connected": connected,
                "client": _active_client.get(sid, ""),
            })
            if not alive:
                dead.append(sid)
        for sid in dead:
            try:
                _sessions.pop(sid).close()
            except Exception:
                pass
            _sessions_buf.pop(sid, None)
            _buf_cleaned_len.pop(sid, None)
    return result


async def delete_session(sid: str) -> bool:
    """删除会话并终止 PTY 进程"""
    _cancel_cleanup_timer(sid)
    async with _sessions_lock:
        proc = _sessions.pop(sid, None)
        _sessions_buf.pop(sid, None)
        _buf_cleaned_len.pop(sid, None)
    if proc is None:
        return False
    await _cleanup_proc(proc)
    asyncio.create_task(_broadcast_sessions())
    return True


# ---------------------------------------------------------------------------
# 重连窗口：断开后 10s 内重连则复用 PTY，超时则自动清理防僵尸
# ---------------------------------------------------------------------------

async def _cleanup_after_disconnect(sid: str) -> None:
    """断开连接后等待重连窗口，超时则清理 PTY"""
    await asyncio.sleep(_cfg_disconnect_timeout())
    # 检查是否已被取消（重连成功）或已被手动删除
    async with _sessions_lock:
        if sid in _disconnect_timers:
            del _disconnect_timers[sid]
        else:
            return  # 已取消
    # 超时，清理 PTY
    await delete_session(sid)


def _cancel_cleanup_timer(sid: str) -> None:
    """重连成功时取消延迟清理"""
    timer = _disconnect_timers.pop(sid, None)
    if timer and not timer.done():
        timer.cancel()


# ---------------------------------------------------------------------------
# REST API Router
# ---------------------------------------------------------------------------

shell_router = APIRouter(prefix="/api/shell", tags=["shell"])


def _require_enabled() -> None:
    if not is_webshell_enabled():
        raise HTTPException(status_code=403, detail="WebShell 功能已禁用")


@shell_router.get("/status")
async def api_status():
    """前端查询是否启用"""
    return {"enabled": is_webshell_enabled()}


@shell_router.post("/sessions")
async def api_create_session():
    _require_enabled()
    """创建新终端会话"""
    sid = await create_session()
    return {"session_id": sid}


@shell_router.get("/sessions")
async def api_list_sessions():
    """列出所有终端会话"""
    _require_enabled()
    return {"sessions": await list_sessions()}


@shell_router.delete("/sessions/{session_id}")
async def api_delete_session(session_id: str):
    """删除终端会话"""
    _require_enabled()
    ok = await delete_session(session_id)
    return {"ok": ok}


# ---------------------------------------------------------------------------
# WebSocket 端点 — 每会话一个 PTY
# ---------------------------------------------------------------------------


async def websocket_shell_endpoint(websocket: WebSocket, session_id: str) -> None:
    """WebSocket shell 端点 — 接入已有 PTY 会话"""

    # ---------- 全局禁用检查 ----------
    if not is_webshell_enabled():
        await websocket.accept()
        await websocket.send_json({"type": "forbidden", "message": "WebShell 功能已禁用"})
        await websocket.close(code=4403, reason="WebShell 已禁用")
        return

    # ---------- 访问控制 ----------
    if not is_localhost(websocket):
        await websocket.accept()
        await websocket.send_json({"type": "forbidden", "message": "仅允许本机访问"})
        await websocket.close(code=4403, reason="仅允许本机访问")
        return

    # ---------- 查找会话 ----------
    proc = await _get_proc(session_id)
    if proc is None:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": f"会话 {session_id} 不存在"})
        await websocket.close()
        return

    await websocket.accept()

    # ---------- 同会话只允许一个客户端：已断则直接接管，活跃则提示确认 ----------
    old_ws = _active_ws.get(session_id)
    # 旧连接已断开 → 清掉，当新连接处理
    if old_ws is not None:
        try:
            # 尝试发送 ping 检测是否仍连通
            await asyncio.wait_for(old_ws.send_json({"type": "ping"}), timeout=0.5)
        except Exception:
            # 旧连接已死，清理
            _active_ws.pop(session_id, None)
            _active_client.pop(session_id, None)
            old_ws = None
    if old_ws is not None:
        await websocket.send_json({
            "type": "session_busy",
            "message": "此终端正在另一个界面使用中，是否抢占？",
            "client": _active_client.get(session_id, ""),
        })
        # 等待用户选择 "supplant"，忽略 onopen 抢先发送的 resize/input
        choice = None
        try:
            while choice is None:
                msg = await websocket.receive_json()
                if msg.get("type") == "supplant":
                    choice = "supplant"
                # 其他消息 (resize/input) 忽略，继续等
        except (WebSocketDisconnect, RuntimeError):
            pass

        if choice != "supplant":
            await websocket.close(code=4000, reason="用户取消")
            return

        # 用户确认抢占 → 踢旧连接
        _active_ws.pop(session_id, None)
        _active_client.pop(session_id, None)
        try:
            await old_ws.send_json({"type": "supplanted", "message": "会话已被其他客户端接管"})
        except Exception:
            pass
        try:
            await old_ws.close(code=4001, reason="会话已被接管")
        except Exception:
            pass

    _active_ws[session_id] = websocket
    _active_client[session_id] = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "?"
    asyncio.create_task(_broadcast_sessions())

    # ---------- 检查进程是否还活着 ----------
    if not proc.isalive():
        try:
            await websocket.send_json({"type": "disconnected", "message": "终端进程已退出"})
            await websocket.close()
        except Exception:
            pass
        _active_ws.pop(session_id, None)
        _active_client.pop(session_id, None)
        return

    # ---------- 取消延迟清理（重连成功） ----------
    _cancel_cleanup_timer(session_id)

    # ---------- 回放历史缓冲（增量清理终端协商序列） ----------
    clean = await _get_buf_clean(session_id)
    if clean:
        try:
            await websocket.send_bytes(clean)
        except Exception:
            pass

    # ---------- 后台任务：PTY stdout → WebSocket ----------
    _stop_read = asyncio.Event()

    async def read_pty() -> None:
        """从 PTY 读取输出，推送到 WebSocket + 环形缓冲区"""
        loop = asyncio.get_running_loop()
        try:
            while not _stop_read.is_set() and proc.isalive():
                try:
                    data = await loop.run_in_executor(_pty_executor, proc.read, 4096)
                except Exception:
                    break
                if not data:
                    await asyncio.sleep(0.05)
                    continue
                if isinstance(data, str):
                    data = data.encode("utf-8", errors="replace")
                await _append_buf(session_id, data)
                try:
                    await websocket.send_bytes(data)
                except Exception:
                    break
        except Exception:
            pass
        finally:
            try:
                await websocket.send_json({"type": "disconnected"})
            except Exception:
                pass

    # ---------- 客户端心跳检测：超时无消息则主动断开 ----------
    _last_msg_time = time.monotonic()
    _heartbeat_stop = asyncio.Event()

    async def heartbeat_check() -> None:
        """每 10s 检查一次客户端心跳，45s 无消息则断开"""
        while not _heartbeat_stop.is_set():
            await asyncio.sleep(10)
            if time.monotonic() - _last_msg_time > 45:
                try:
                    await websocket.close(code=4002, reason="客户端心跳超时")
                except Exception:
                    pass
                _stop_read.set()
                break

    read_task = asyncio.create_task(read_pty())
    heartbeat_task = asyncio.create_task(heartbeat_check())

    # ---------- 主循环：接收前端输入 ----------
    loop = asyncio.get_running_loop()
    try:
        while True:
            msg = await websocket.receive_json()
            _last_msg_time = time.monotonic()
            msg_type = msg.get("type", "")

            if msg_type == "input":
                data = msg.get("data", "")
                if proc.isalive() and data:
                    await loop.run_in_executor(_pty_executor, proc.write, data)

            elif msg_type == "resize":
                rows = msg.get("rows", 40)
                cols = msg.get("cols", 120)
                if proc.isalive():
                    proc.setwinsize(rows, cols)

            elif msg_type == "ping":
                try:
                    await websocket.send_json({"type": "pong"})
                except Exception:
                    break

    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        pass
    finally:
        _stop_read.set()
        _heartbeat_stop.set()
        read_task.cancel()
        heartbeat_task.cancel()
        try:
            await read_task
        except asyncio.CancelledError:
            pass
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        # 清理活跃连接记录（仅当未被替换时）
        if _active_ws.get(session_id) is websocket:
            _active_ws.pop(session_id, None)
            _active_client.pop(session_id, None)
            asyncio.create_task(_broadcast_sessions())

            # 正常断开 → 启动延迟清理
            _disconnect_timers[session_id] = asyncio.create_task(
                _cleanup_after_disconnect(session_id)
            )


# ---------------------------------------------------------------------------
# 监控端点 — 实时推送会话列表
# ---------------------------------------------------------------------------


async def websocket_shell_monitor(websocket: WebSocket) -> None:
    """推送会话列表变更，前端不轮询不缓存"""
    if not is_localhost(websocket):
        await websocket.accept()
        await websocket.send_json({"type": "forbidden", "message": "仅允许本机访问"})
        await websocket.close(code=4403)
        return

    await websocket.accept()

    # 立即发送当前列表
    await websocket.send_json({"type": "sessions", "sessions": await list_sessions()})

    async with _monitors_lock:
        _monitors.append(websocket)

    try:
        while True:
            try:
                await websocket.receive_text()  # 保持连接
            except Exception:
                break
    finally:
        async with _monitors_lock:
            try:
                _monitors.remove(websocket)
            except ValueError:
                pass
