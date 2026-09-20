"""TCP 客户端（调试工具）—— 面向前端的 REST + WebSocket 接口。

页面位置：管理 → TCP 客户端（``/tcp-client``）。

REST（统一挂在 ``/api/tcp`` 前缀下）::

    GET    /api/tcp/sessions                # 会话列表
    POST   /api/tcp/sessions                # 新建会话（可选立即连接）
    GET    /api/tcp/sessions/{sid}          # 会话详情
    DELETE /api/tcp/sessions/{sid}          # 删除会话（同时断开）
    POST   /api/tcp/sessions/{sid}/connect  # 建立连接
    POST   /api/tcp/sessions/{sid}/disconnect
    POST   /api/tcp/sessions/{sid}/send     # 发送文本 / HEX
    GET    /api/tcp/sessions/{sid}/log      # 增量拉取收发记录
    DELETE /api/tcp/sessions/{sid}/log      # 清空收发记录

WebSocket::

    /ws/tcp-client/{sid}

    服务端推送：``snapshot`` / ``log`` / ``state`` / ``cleared`` / ``heartbeat``
    客户端可发：``{"type":"send","data":"...","mode":"text|hex","newline":""}``、
                ``{"type":"clear"}``、``{"type":"snapshot"}``、``{"type":"ping"}``
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from util.logger import logger
from util.tcp_client import TcpClientError, tcp_clients

tcp_client_router = APIRouter(
    prefix="/tcp",
    tags=["tcp"],
)


# ----------------------------------------------------------------------
# 请求模型
# ----------------------------------------------------------------------
class CreateSessionRequest(BaseModel):
    host: str = Field(..., description="目标主机，例如 172.27.6.43")
    port: int = Field(..., ge=1, le=65535, description="目标端口")
    name: str | None = Field(None, description="显示名称，缺省为 host:port")
    encoding: str = Field("utf-8", description="文本编码，如 utf-8 / gbk")
    auto_reconnect: bool = Field(False, description="断线后是否自动重连")
    connect: bool = Field(True, description="创建后是否立即连接")


class SendRequest(BaseModel):
    data: str = Field(..., description="待发送内容；mode=hex 时为十六进制串")
    mode: Literal["text", "hex"] = Field("text", description="发送模式")
    newline: Literal["", "lf", "crlf", "cr"] = Field("", description="自动追加的换行")
    encoding: str | None = Field(None, description="覆盖会话默认编码（发送文本时）")


def _error(message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


# ----------------------------------------------------------------------
# REST 接口
# ----------------------------------------------------------------------
@tcp_client_router.get("/sessions")
async def list_sessions():
    """列出全部 TCP 会话。"""
    return {"success": True, "sessions": tcp_clients.list()}


@tcp_client_router.post("/sessions")
async def create_session(payload: CreateSessionRequest):
    """新建会话，默认立即连接。"""
    try:
        session = tcp_clients.create(
            payload.host,
            payload.port,
            name=payload.name,
            encoding=payload.encoding,
            auto_reconnect=payload.auto_reconnect,
        )
    except TcpClientError as exc:
        raise _error(str(exc)) from exc

    error = ""
    if payload.connect:
        try:
            await session.connect()
        except TcpClientError as exc:
            error = str(exc)

    return {
        "success": not error,
        "error": error,
        "session": session.snapshot(),
        "log": session.log_entries(),
    }


@tcp_client_router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """会话详情。"""
    try:
        session = tcp_clients.require(session_id)
    except TcpClientError as exc:
        raise _error(str(exc), 404) from exc
    return {"success": True, "session": session.snapshot()}


@tcp_client_router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话（会先断开连接）。"""
    removed = await tcp_clients.remove(session_id)
    if not removed:
        raise _error(f"会话不存在: {session_id}", 404)
    return {"success": True, "message": "会话已删除"}


@tcp_client_router.post("/sessions/{session_id}/connect")
async def connect_session(session_id: str):
    """建立连接。"""
    try:
        session = tcp_clients.require(session_id)
        await session.connect()
    except TcpClientError as exc:
        raise _error(str(exc)) from exc
    return {"success": True, "session": session.snapshot()}


@tcp_client_router.post("/sessions/{session_id}/disconnect")
async def disconnect_session(session_id: str):
    """主动断开连接（不触发自动重连）。"""
    try:
        session = tcp_clients.require(session_id)
    except TcpClientError as exc:
        raise _error(str(exc), 404) from exc
    await session.disconnect()
    return {"success": True, "session": session.snapshot()}


@tcp_client_router.post("/sessions/{session_id}/send")
async def send_data(session_id: str, payload: SendRequest):
    """发送数据（文本或 HEX）。"""
    try:
        session = tcp_clients.require(session_id)
        size = await session.send_text(
            payload.data,
            mode=payload.mode,
            newline=payload.newline,
            encoding=payload.encoding,
        )
    except TcpClientError as exc:
        raise _error(str(exc)) from exc
    return {"success": True, "size": size, "session": session.snapshot()}


@tcp_client_router.get("/sessions/{session_id}/log")
async def get_log(
    session_id: str,
    after_seq: int = Query(0, ge=0, description="只返回序号大于该值的记录"),
    limit: int = Query(200, ge=1, le=2000, description="最多返回条数"),
):
    """增量拉取收发记录（WebSocket 断开时的兜底）。"""
    try:
        session = tcp_clients.require(session_id)
    except TcpClientError as exc:
        raise _error(str(exc), 404) from exc
    entries = session.log_entries(after_seq=after_seq, limit=limit)
    return {
        "success": True,
        "session": session.snapshot(),
        "log": entries,
        "last_seq": session.snapshot()["last_seq"],
    }


@tcp_client_router.delete("/sessions/{session_id}/log")
async def clear_log(session_id: str):
    """清空收发记录。"""
    try:
        session = tcp_clients.require(session_id)
    except TcpClientError as exc:
        raise _error(str(exc), 404) from exc
    session.clear_log()
    return {"success": True, "message": "记录已清空"}


# ----------------------------------------------------------------------
# WebSocket 端点
# ----------------------------------------------------------------------
async def _handle_client_message(
    websocket: WebSocket, session, message: dict
) -> None:
    """处理浏览器通过 WebSocket 发来的指令。"""
    msg_type = str(message.get("type") or "").lower()

    if msg_type in ("ping", ""):
        await websocket.send_json({"type": "pong"})
        return

    if msg_type == "snapshot":
        await websocket.send_json(
            {
                "type": "snapshot",
                "data": session.snapshot(),
                "log": session.log_entries(),
            }
        )
        return

    if msg_type == "clear":
        session.clear_log()
        return

    if msg_type == "send":
        try:
            size = await session.send_text(
                str(message.get("data") or ""),
                mode=str(message.get("mode") or "text"),
                newline=str(message.get("newline") or ""),
                encoding=message.get("encoding") or None,
            )
        except TcpClientError as exc:
            await websocket.send_json({"type": "error", "message": str(exc)})
            return
        await websocket.send_json(
            {"type": "sent", "size": size, "stats": session.stats()}
        )
        return

    await websocket.send_json(
        {"type": "error", "message": f"不支持的消息类型: {msg_type}"}
    )


async def websocket_tcp_client_endpoint(websocket: WebSocket, session_id: str) -> None:
    """TCP 会话的实时通道：推送收发记录与状态，并接收发送指令。"""
    session = tcp_clients.get(session_id)
    if session is None:
        await websocket.accept()
        await websocket.send_json(
            {"type": "error", "message": f"会话不存在: {session_id}"}
        )
        await websocket.close(code=4404)
        return

    await websocket.accept()
    queue = session.subscribe()

    await websocket.send_json(
        {
            "type": "snapshot",
            "data": session.snapshot(),
            "log": session.log_entries(),
        }
    )

    async def _pump() -> None:
        """会话事件 → 浏览器。"""
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=25)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
                continue
            await websocket.send_json(event)

    async def _reader() -> None:
        """浏览器指令 → 会话。"""
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                await websocket.send_json(
                    {"type": "error", "message": "消息必须是 JSON 对象"}
                )
                continue
            await _handle_client_message(websocket, session, message)

    pump_task = asyncio.create_task(_pump())
    pump_task.set_name(f"tcp-ws-pump-{session_id}")
    reader_task = asyncio.create_task(_reader())
    reader_task.set_name(f"tcp-ws-reader-{session_id}")

    try:
        done, pending = await asyncio.wait(
            {pump_task, reader_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                logger.debug(f"TCP WebSocket 会话 {session_id} 结束: {exc}")
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # 客户端异常断开等
        logger.debug(f"TCP WebSocket 处理异常 ({session_id}): {exc}")
    finally:
        for task in (pump_task, reader_task):
            if not task.done():
                task.cancel()
        session.unsubscribe(queue)
        with contextlib.suppress(Exception):
            await websocket.close()
