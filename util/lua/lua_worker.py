"""Lua 用户脚本 worker —— 子进程执行入口。

协议
====

stdin  单个 JSON 对象::

    {"mode": "run"|"check", "script_id": "...", "code": "...",
     "payload_json": "<JSON 文本>", "limits": {...}}

stdout 一行标记结果（不是裸 JSON）::

    __AGVMON_LUA_RESULT__ {"ok": true, ...}

为什么用标记行而不是直接输出纯 JSON：``util/core/logger.py`` 把 loguru 的 sink 挂到了
``sys.stdout``，而本进程经由 ``main.py`` 启动时会带上它，任何日志都会混进 stdout。
宿主侧只认最后一个标记行，其余内容忽略。

进程退出码：正常情况（含脚本自身报错）恒为 0，只有连结果都写不出来才非 0。
"""

from __future__ import annotations

import json
import sys
import time
import traceback

# 与 util/lua/lua_runtime.py 保持一致（不 import 对方，避免 worker 拉起多余依赖）
RESULT_MARKER = "__AGVMON_LUA_RESULT__"

# 单条日志最大长度，防止 print(巨长字符串) 把响应撑爆
MAX_LOG_LINE_CHARS = 2000

DEFAULT_LIMITS = {
    "timeout_ms": 1000,
    "max_memory_mb": 64,
    "max_result_kb": 256,
    "max_script_kb": 128,
    "max_log_lines": 200,
    "max_depth": 64,
    "max_nodes": 50000,
}


def _emit(payload: dict) -> None:
    """把结果写到真实 stdout（绕过任何文本包装，固定 UTF-8）。"""
    line = RESULT_MARKER + " " + json.dumps(payload, ensure_ascii=False, default=str)
    data = ("\n" + line + "\n").encode("utf-8", errors="replace")
    try:
        sys.stdout.flush()
    except Exception:
        pass
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    except Exception:
        # 极端情况下退回文本写
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _quit_loguru() -> None:
    """worker 的 stdout 是协议通道，必须干净。

    只在 loguru **已经被导入**时才动手：走 ``main.py`` 快速通道时它根本没被导入，
    为清理而 import 它反而要多花约 100ms 冷启动（每次执行都要重启 worker）。
    """
    mod = sys.modules.get("loguru")
    if mod is None:
        return
    try:
        mod.logger.remove()
    except Exception:
        pass


def _limits(raw) -> dict:
    out = dict(DEFAULT_LIMITS)
    if isinstance(raw, dict):
        for key in DEFAULT_LIMITS:
            value = raw.get(key)
            if value is not None:
                out[key] = value
    return out


def _stub_bridge(reason: str):
    """HTTP 桥初始化失败时的替身：让脚本拿到明确的错误而不是 '桥未就绪'。"""
    payload = json.dumps(
        {"ok": False, "error": reason, "error_type": "http_unavailable"},
        ensure_ascii=False,
    )

    def _stub(_spec_json: str) -> str:
        return payload

    return _stub


def _fail(error_type: str, message: str, *, started: float, tb: str = "") -> dict:
    return {
        "ok": False,
        "error": message,
        "error_type": error_type,
        "traceback": tb,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


def main() -> int:
    _quit_loguru()
    started = time.perf_counter()

    raw_job = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read().encode("utf-8")
    try:
        # utf-8-sig：容忍手工管道/文件输入带 BOM 的情况
        job = json.loads(raw_job.decode("utf-8-sig"))
    except Exception as exc:
        _emit(_fail("internal", f"无法解析 worker 作业参数: {exc}", started=started))
        return 1

    started = time.perf_counter()
    mode = str(job.get("mode") or "run")
    script_id = str(job.get("script_id") or "anonymous")
    code = job.get("code")
    payload_json = job.get("payload_json") or "{}"
    request_json = json.dumps(job.get("request") or {}, ensure_ascii=False)
    limits = _limits(job.get("limits"))

    if not isinstance(code, str):
        _emit(_fail("internal", "作业缺少 code 字段", started=started))
        return 0

    max_script_bytes = int(limits["max_script_kb"]) * 1024
    if len(code.encode("utf-8", errors="replace")) > max_script_bytes:
        _emit(_fail("script", f"脚本超过 {limits['max_script_kb']}KB 上限", started=started))
        return 0

    try:
        from util.lua import lua_sandbox
    except Exception as exc:
        _emit(
            _fail(
                "internal",
                f"Lua 运行时不可用（{type(exc).__name__}: {exc}）。"
                "源码运行请执行 `uv sync` 安装 lupa；"
                "Nuitka 打包产物出现该错误说明 lupa 的原生模块没被打进 main.dist。",
                started=started,
            )
        )
        return 0

    logs: list[str] = []
    try:
        lua = lua_sandbox.build_runtime(int(limits["max_memory_mb"]) * 1024 * 1024)

        # 外部 HTTP 桥：真正的网络动作在这边做，Lua 只能通过它发请求。
        # 单次请求超时会按"脚本剩余时间"再收一道，避免 3 个请求各等 2.5s
        # 结果被父进程的墙钟超时直接杀掉、报错信息还看不懂。
        try:
            from util.lua import lua_http

            policy = lua_http.HttpPolicy.from_config(job.get("http"))
            http_bridge = lua_http.HttpBridge(policy, budget_ms=int(limits["timeout_ms"]))
        except Exception as exc:
            # 桥建不起来不该让整个脚本挂掉：给一个总是返回错误的桩，报错照样看得见
            reason = f"HTTP 桥初始化失败：{type(exc).__name__}: {exc}"
            print(reason, file=sys.stderr)
            http_bridge = _stub_bridge(reason)

        sandbox, logs_table = lua_sandbox.lockdown(
            lua,
            max_log_lines=int(limits["max_log_lines"]),
            max_depth=int(limits["max_depth"]),
            max_nodes=int(limits["max_nodes"]),
            http_bridge=http_bridge,
        )
    except Exception as exc:
        _emit(
            _fail(
                "internal",
                f"沙箱初始化失败: {type(exc).__name__}: {exc}",
                started=started,
                tb=traceback.format_exc(limit=6),
            )
        )
        return 0

    try:
        if mode == "check":
            lua_sandbox.check_syntax(lua, code, script_id)
            _emit(
                {
                    "ok": True,
                    "mode": mode,
                    "result": None,
                    "logs": [],
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "runtime": lua_sandbox.runtime_info(lua),
                }
            )
            return 0

        result_json = lua_sandbox.execute(
            lua, sandbox, code, payload_json, script_id, limits, request_json
        )

        max_result_bytes = int(limits["max_result_kb"]) * 1024
        if len(result_json.encode("utf-8", errors="replace")) > max_result_bytes:
            _emit(
                _fail(
                    "result",
                    f"脚本结果超过 {limits['max_result_kb']}KB 上限"
                    f"（当前 {len(result_json.encode('utf-8', errors='replace')) // 1024}KB）",
                    started=started,
                )
            )
            return 0

        # 回读一遍：既校验纯 Lua 编码器产出的确是合法 JSON，也顺便转成 Python 对象
        try:
            result = json.loads(result_json)
        except Exception as exc:
            _emit(
                _fail(
                    "result",
                    f"脚本结果不是合法 JSON: {exc}（前 200 字符: {result_json[:200]!r}）",
                    started=started,
                )
            )
            return 0

        logs = lua_sandbox.read_logs(logs_table)
        _emit(
            {
                "ok": True,
                "mode": mode,
                "result": result,
                "logs": [line[:MAX_LOG_LINE_CHARS] for line in logs],
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "runtime": lua_sandbox.runtime_info(lua),
            }
        )
        return 0

    except Exception as exc:
        # 脚本报错时把已经产生的日志一并带回，方便排查
        try:
            logs = lua_sandbox.read_logs(logs_table)
        except Exception:
            logs = []

        lupa, _variant = lua_sandbox.import_lupa()
        if isinstance(exc, getattr(lupa, "LuaMemoryError", ())):
            error_type = "memory"
            message = f"Lua 内存超限（上限 {limits['max_memory_mb']}MB）"
        elif isinstance(exc, getattr(lupa, "LuaSyntaxError", ())):
            error_type = "syntax"
            message = str(exc)
        elif isinstance(exc, UnicodeDecodeError):
            error_type = "result"
            message = f"脚本结果包含非 UTF-8 字节：{exc}"
        elif isinstance(exc, getattr(lupa, "LuaError", ())):
            error_type = "lua"
            message = str(exc)
        else:
            error_type = "internal"
            message = f"{type(exc).__name__}: {exc}"

        detail = "" if error_type in ("lua", "syntax", "memory") else traceback.format_exc(limit=6)
        payload = _fail(error_type, message, started=started, tb=detail)
        payload["logs"] = [line[:MAX_LOG_LINE_CHARS] for line in logs]
        _emit(payload)
        return 0


if __name__ == "__main__":
    sys.exit(main())
