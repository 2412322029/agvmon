"""用户 Lua 脚本的执行宿主（父进程侧）。

职责
====
* 把脚本 + 请求体打包成作业，交给 ``python main.py run lua-worker`` 子进程执行；
* 用**墙钟超时 + 强杀进程**兜住死循环 —— lupa 没有暴露 ``lua_sethook``，脚本一旦
  在 Lua/C 层死循环，进程内是没法中断的，只能杀进程；
* 限制并发、限制 payload/脚本/结果体积。

本模块**不导入 lupa**：宿主进程不需要原生 Lua VM，只有 worker 子进程需要。

进程模型：每执行一次脚本拉起一个 worker 进程（进程池不做，保持实现简单、
天然隔离）。实测冷启动开销见 ``test_user_script.py`` 的耗时打印。
"""

from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from util.lua import lua_http
from util.core.config import APP_ROOT, cfg
from util.core.paths import PROJECT_ROOT

RESULT_MARKER = "__AGVMON_LUA_RESULT__"
MAX_STDERR_CHARS = 2000

# 配置默认值：config.toml 缺 [user_script] 段时也能工作
DEFAULT_CONFIG: dict[str, Any] = {
    # 总开关；默认开启但只允许本机调用，见 allow_remote
    "enabled": True,
    # 是否允许非本机来源调用（开启时必须设置 api_key）
    "allow_remote": False,
    # 远程调用所需的 X-API-Key；留空表示不允许远程
    "api_key": "",
    # 单次执行的墙钟超时，超时直接杀进程。
    # 8s 而不是 1s：脚本要调外部接口的话，1s 连一次握手都不够；示例脚本要调两次
    # （默认站点的 config.toml 是 30000，以那份为准）。
    "timeout_ms": 8000,
    # Lua 分配器硬上限（由 lupa 的 max_memory 在 C 层强制）
    "max_memory_mb": 64,
    # 请求体 / 脚本 / 结果 的体积上限
    "max_payload_kb": 256,
    "max_script_kb": 128,
    "max_result_kb": 256,
    # 单次执行最多保留多少行 print/console 日志
    "max_log_lines": 200,
    # 同时执行的脚本数上限
    "max_concurrency": 4,
    # 结果 JSON 的嵌套深度与节点数上限（防爆栈/防巨表）
    "max_depth": 64,
    "max_nodes": 50000,
    # 外部 HTTP 策略（[user_script.http]），由 util/lua/lua_http.py 解释
    "http": dict(lua_http.DEFAULT_POLICY),
}

_CLAMPS = {
    "timeout_ms": (50, 60_000),
    "max_memory_mb": (8, 1024),
    "max_payload_kb": (1, 8192),
    "max_script_kb": (1, 2048),
    "max_result_kb": (1, 8192),
    "max_log_lines": (1, 2000),
    "max_concurrency": (1, 32),
    "max_depth": (4, 256),
    "max_nodes": (100, 2_000_000),
}


class ScriptRuntimeError(RuntimeError):
    """宿主机（非用户脚本）层面的执行失败。"""


def script_config() -> dict[str, Any]:
    """读取 [user_script] 配置（每次读文件，改配置无需重启）。"""
    raw = cfg.get_with_reload("user_script") or {}
    merged = dict(DEFAULT_CONFIG)
    if isinstance(raw, dict):
        for key in DEFAULT_CONFIG:
            value = raw.get(key)
            if value is not None:
                merged[key] = value

    for key, (low, high) in _CLAMPS.items():
        try:
            merged[key] = max(low, min(high, int(merged[key])))
        except (TypeError, ValueError):
            merged[key] = DEFAULT_CONFIG[key]

    merged["enabled"] = bool(merged["enabled"])
    merged["allow_remote"] = bool(merged["allow_remote"])
    merged["api_key"] = str(merged["api_key"] or "")
    # 嵌套的 HTTP 策略交给 lua_http 归一化（默认值/夹取/主机名单清洗都在一起）
    merged["http"] = lua_http.HttpPolicy.from_config(
        raw.get("http") if isinstance(raw, dict) else None
    ).to_dict()
    return merged


def worker_limits(config: dict[str, Any]) -> dict[str, Any]:
    """透传给 worker 的那部分限制。"""
    keys = (
        "timeout_ms", "max_memory_mb", "max_result_kb", "max_script_kb",
        "max_log_lines", "max_depth", "max_nodes",
    )
    return {k: config[k] for k in keys}


# ----------------------------------------------------------------------
# worker 进程
# ----------------------------------------------------------------------
def worker_command() -> list[str]:
    """构造 worker 子进程命令行。

    Nuitka 打包后 ``sys.executable`` 就是 agvmon.exe，直接复用自身加一个隐藏
    子命令，避免依赖源码树 / 依赖 multiprocessing 的 freeze 支持。
    """
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return [sys.executable, "run", "lua-worker"]
    main_py = Path(PROJECT_ROOT) / "main.py"
    return [sys.executable, str(main_py), "run", "lua-worker"]


def _popen_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "cwd": str(APP_ROOT),
        "env": {
            **os.environ,
            # 固定 UTF-8，避免 Windows 控制台代码页（cp936）污染协议
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        },
    }
    if sys.platform == "win32":
        # 不弹出控制台窗口（服务器为 --windows-console-mode=attach）
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return kwargs


def _decode(raw: bytes | None) -> str:
    if not raw:
        return ""
    return raw.decode("utf-8", errors="replace")


def _parse_worker_result(stdout: str) -> dict[str, Any] | None:
    """取最后一个标记行（前面的日志噪声一律忽略）。"""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith(RESULT_MARKER):
            try:
                return json.loads(line[len(RESULT_MARKER):].strip())
            except json.JSONDecodeError:
                return None
    return None


# ----------------------------------------------------------------------
# 执行结果
# ----------------------------------------------------------------------
@dataclass
class ScriptExecution:
    ok: bool
    result: Any = None
    logs: list[str] = field(default_factory=list)
    error: str = ""
    error_type: str = ""
    traceback: str = ""
    duration_ms: int = 0      # 含 fork/exec 的总耗时
    worker_ms: int = 0        # worker 内部耗时
    runtime: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def failure(cls, error_type: str, message: str, duration_ms: int = 0, **kw) -> "ScriptExecution":
        return cls(ok=False, error=message, error_type=error_type, duration_ms=duration_ms, **kw)

    def to_dict(self, script_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "success": self.ok,
            "ok": self.ok,
            "duration_ms": self.duration_ms,
            "worker_ms": self.worker_ms,
        }
        if script_id is not None:
            payload["script_id"] = script_id
        if self.ok:
            payload["result"] = self.result
        else:
            payload["error"] = self.error
            payload["error_type"] = self.error_type
            if self.traceback:
                payload["traceback"] = self.traceback
        if self.logs:
            payload["logs"] = self.logs
        if self.runtime:
            payload["runtime"] = self.runtime
        return payload

    @property
    def status(self) -> str:
        return "ok" if self.ok else (self.error_type or "error")


# ----------------------------------------------------------------------
# 执行
# ----------------------------------------------------------------------
def execute_script(
    code: str,
    payload: Any = None,
    *,
    script_id: str = "anonymous",
    mode: str = "run",
    config: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
) -> ScriptExecution:
    """同步执行一次脚本（会阻塞；异步接口请用 ``execute_script_async``）。

    :param request: 触发这次执行的 HTTP 请求元信息，脚本里是 ``ctx.request`` /
        ``ctx.body`` / ``ctx.query``。让脚本能直接当 API 端点给别的服务调用。
    """
    config = config or script_config()
    started = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - started) * 1000)

    if not isinstance(code, str) or not code.strip():
        return ScriptExecution.failure("script", "脚本内容为空", elapsed())

    code_bytes = len(code.encode("utf-8", errors="replace"))
    if code_bytes > config["max_script_kb"] * 1024:
        return ScriptExecution.failure(
            "script",
            f"脚本体积 {code_bytes // 1024}KB 超过上限 {config['max_script_kb']}KB",
            elapsed(),
        )

    try:
        payload_json = json.dumps(payload if payload is not None else {}, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        return ScriptExecution.failure("payload", f"请求体无法序列化为 JSON: {exc}", elapsed())

    payload_bytes = len(payload_json.encode("utf-8", errors="replace"))
    if payload_bytes > config["max_payload_kb"] * 1024:
        return ScriptExecution.failure(
            "payload",
            f"请求体 {payload_bytes // 1024}KB 超过上限 {config['max_payload_kb']}KB",
            elapsed(),
        )

    job = {
        "mode": mode,
        "script_id": script_id,
        "code": code,
        "payload_json": payload_json,
        "limits": worker_limits(config),
        # 外部 HTTP 策略单独一份：worker 用它建桥，脚本能不能联网就看这里
        "http": config.get("http") or {},
        # 这次 HTTP 请求本身（method/query/headers/body），脚本当 API 端点用
        "request": request or {},
    }
    job_bytes = json.dumps(job, ensure_ascii=False).encode("utf-8")

    timeout_s = config["timeout_ms"] / 1000.0
    try:
        proc = subprocess.Popen(worker_command(), **_popen_kwargs())
    except OSError as exc:
        return ScriptExecution.failure(
            "spawn",
            f"无法启动脚本 worker（{exc}）。检查 python 可执行文件与 main.py 是否可用。",
            elapsed(),
        )

    try:
        stdout_raw, stderr_raw = proc.communicate(input=job_bytes, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _terminate(proc)
        stdout_raw, stderr_raw = b"", b""
        try:
            stdout_raw, stderr_raw = proc.communicate(timeout=5)
        except Exception:
            pass
        return ScriptExecution.failure(
            "timeout",
            f"脚本执行超时（{config['timeout_ms']}ms），已强制终止。"
            "常见原因是 while 循环没有退出条件。",
            elapsed(),
            logs=[],
        )

    stdout = _decode(stdout_raw)
    parsed = _parse_worker_result(stdout)

    if parsed is None:
        stderr_tail = _decode(stderr_raw)[-MAX_STDERR_CHARS:].strip()
        return ScriptExecution.failure(
            "crash",
            f"脚本 worker 异常退出（退出码 {proc.returncode}，无有效结果）。"
            + (f" stderr: {stderr_tail}" if stderr_tail else " 且 stderr 为空。"),
            elapsed(),
            traceback=stderr_tail,
        )

    if not parsed.get("ok"):
        return ScriptExecution(
            ok=False,
            logs=list(parsed.get("logs") or []),
            error=str(parsed.get("error") or "未知错误"),
            error_type=str(parsed.get("error_type") or "error"),
            traceback=str(parsed.get("traceback") or ""),
            duration_ms=elapsed(),
            worker_ms=int(parsed.get("elapsed_ms") or 0),
            runtime=parsed.get("runtime") or {},
        )

    return ScriptExecution(
        ok=True,
        result=parsed.get("result"),
        logs=list(parsed.get("logs") or []),
        duration_ms=elapsed(),
        worker_ms=int(parsed.get("elapsed_ms") or 0),
        runtime=parsed.get("runtime") or {},
    )


def _terminate(proc: subprocess.Popen) -> None:
    """强杀 worker（Windows 上是 TerminateProcess，Lua 死循环也能带走）。"""
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


# ----------------------------------------------------------------------
# 并发闸门
# ----------------------------------------------------------------------
_sem_lock = threading.Lock()
_semaphores: dict[int, threading.BoundedSemaphore] = {}


def _semaphore(limit: int) -> threading.BoundedSemaphore:
    with _sem_lock:
        sem = _semaphores.get(limit)
        if sem is None:
            sem = threading.BoundedSemaphore(max(1, limit))
            _semaphores[limit] = sem
        return sem


def execute_script_guarded(
    code: str,
    payload: Any = None,
    *,
    script_id: str = "anonymous",
    mode: str = "run",
    config: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
) -> ScriptExecution:
    """带并发上限的执行；排队过久直接返回 busy，避免线程池被拖满。"""
    config = config or script_config()
    sem = _semaphore(config["max_concurrency"])
    wait_s = config["timeout_ms"] / 1000.0 + 5.0
    if not sem.acquire(timeout=wait_s):
        return ScriptExecution.failure(
            "busy",
            f"并发执行数已达上限 {config['max_concurrency']}，请稍后重试",
        )
    try:
        return execute_script(
            code, payload, script_id=script_id, mode=mode, config=config, request=request
        )
    finally:
        sem.release()


async def execute_script_async(
    code: str,
    payload: Any = None,
    *,
    script_id: str = "anonymous",
    mode: str = "run",
    config: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
) -> ScriptExecution:
    """异步入口：把阻塞的进程等待丢到 anyio 线程池，绝不阻塞事件循环。"""
    import anyio

    return await anyio.to_thread.run_sync(
        functools.partial(
            execute_script_guarded,
            code,
            payload,
            script_id=script_id,
            mode=mode,
            config=config,
            request=request,
        )
    )


def runtime_healthcheck() -> ScriptExecution:
    """端到端自检：走完整 worker 链路执行一个最小脚本。

    用途：验证 lupa 是否可用、以及 Nuitka 打包产物里原生模块是否齐全。
    顺带确认外部 HTTP 桥装上了（``type(http)`` 应该是 ``table``）。
    """
    return execute_script(
        "return {ok = true, lua = _VERSION, os_date = type(os.date), http = type(http)}",
        {"selfcheck": True},
        script_id="__healthcheck__",
        config=script_config(),
    )
