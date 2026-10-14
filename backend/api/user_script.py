"""用户自定义 Lua 脚本 API。

定位与 Cloudflare Workers / OpenResty 类似：用户上传一段 Lua，平台负责在沙箱里
用它处理请求数据。区别在于这里跑在 AGV 内网运维终端上，所以默认**只允许本机调用**。

接口一览（挂载前缀 ``/api``）::

    GET    /api/user-script                脚本列表
    POST   /api/user-script                新建脚本
    POST   /api/user-script/run            临时执行一段代码（不落库，便于调脚本）
    GET    /api/user-script/runtime        运行时信息 + 端到端自检
    GET    /api/user-script/{id}           读取脚本（含正文）
    PUT    /api/user-script/{id}           更新脚本
    DELETE /api/user-script/{id}           删除脚本
    POST   /api/user-script/{id}/check     仅语法检查
    GET    /api/user-script/{id}/run       执行脚本（脚本即 API 端点，query 传参）
    POST   /api/user-script/{id}/run       执行脚本（JSON body 传参）
    POST   /api/user-script/{id}           执行脚本（同上，等价别名）
    GET    /api/user-script/{id}/runs      执行流水

访问控制见 ``evaluate_access``：总开关 + 仅本机 + 远程需 API Key 三道闸。
要让**其他服务**调用脚本当接口用，需要在 config.toml 里开 ``allow_remote`` 并配 ``api_key``。

脚本入参怎么来见 ``_script_input``；脚本可以用结果里的 ``__status`` / ``__headers``
指定 HTTP 状态码与响应头（见 ``_extract_response_meta``）。
"""

from __future__ import annotations

import ipaddress
import json
import secrets
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from util.lua import lua_runtime
from util.core.logger import logger
from util.lua.user_script_store import (
    ScriptIdInvalid,
    ScriptNotFound,
    get_store,
)

user_script_router = APIRouter(prefix="/user-script", tags=["user-script"])

# 审计/返回里记录的来源标识
_LOCAL_NAMES = {"localhost", "127.0.0.1", "::1"}


# ----------------------------------------------------------------------
# 请求模型
# ----------------------------------------------------------------------
class ScriptCreate(BaseModel):
    script_id: str = Field(..., description="脚本 ID，字母数字与 _ . - ，1-64 字符")
    code: str = Field(..., description="Lua 脚本正文")
    name: str = Field("", description="显示名称")
    description: str = Field("", description="说明")
    enabled: bool = Field(True, description="是否启用")
    # 不能叫 validate：会遮蔽 BaseModel.validate 并触发 Pydantic 警告
    validate_code: bool = Field(True, description="保存前是否做语法检查")


class ScriptUpdate(BaseModel):
    code: str | None = Field(None, description="新脚本正文（会递增版本号）")
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    validate_code: bool = Field(True, description="更新正文时是否做语法检查")


class AdhocRun(BaseModel):
    code: str = Field(..., description="要执行的 Lua 代码（不落库）")
    payload: Any = Field(default_factory=dict, description="传给脚本的请求数据")
    script_id: str = Field("adhoc", description="执行时使用的脚本名，仅用于报错定位")


class CheckRequest(BaseModel):
    code: str | None = Field(None, description="要检查的代码，缺省检查已保存的正文")


# ----------------------------------------------------------------------
# 访问控制
# ----------------------------------------------------------------------
def _is_loopback(host: str) -> bool:
    if not host:
        return False
    if host in _LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def evaluate_access(host: str, headers: Mapping[str, str], config: dict) -> tuple[bool, str, int]:
    """纯函数版访问判定，便于单测。返回 ``(allowed, reason, status_code)``。

    三道闸：
    1. ``enabled`` 总开关；
    2. 非本机来源默认拒绝（``allow_remote`` 才放行）；
    3. 远程放行时必须有 ``api_key``，且请求头 ``X-API-Key`` 必须匹配。

    注意：带 ``X-Forwarded-For`` / ``X-Real-IP`` 的请求一律按"远程"处理 ——
    否则挂在同机反向代理后面时，所有外部请求的来源都是 127.0.0.1，闸门会失效。
    """
    if not config.get("enabled", True):
        return False, "用户脚本功能已禁用（config.toml 中 [user_script] enabled = false）", 403

    forwarded = bool(
        headers.get("x-forwarded-for") or headers.get("x-real-ip") or headers.get("forwarded")
    )
    if _is_loopback(host) and not forwarded:
        return True, "本机调用", 200

    if not config.get("allow_remote"):
        return (
            False,
            f"用户脚本接口仅允许本机调用（来源 {host or '未知'}）。"
            "如需远程调用，请设置 config.toml 中 [user_script] 的 "
            "allow_remote = true 并配置 api_key。",
            403,
        )

    api_key = config.get("api_key") or ""
    if not api_key:
        return (
            False,
            "已开启 allow_remote 但未配置 api_key，为安全起见拒绝远程调用。",
            403,
        )

    provided = headers.get("x-api-key") or ""
    if not provided or not secrets.compare_digest(provided, api_key):
        return False, "API Key 缺失或不正确（请求头 X-API-Key）", 401

    return True, "远程调用（API Key 校验通过）", 200


async def require_access(request: Request) -> dict:
    """FastAPI 依赖：所有用户脚本接口统一走这里。"""
    config = lua_runtime.script_config()
    host = request.client.host if request.client else ""
    allowed, reason, status = evaluate_access(host, request.headers, config)
    if not allowed:
        logger.warning(f"用户脚本接口拒绝访问: {reason}")
        raise HTTPException(status_code=status, detail=reason)
    return config


def _error(message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=message)


def _client_source(request: Request) -> str:
    host = request.client.host if request.client else ""
    forwarded = request.headers.get("x-forwarded-for")
    return f"{host} via {forwarded}" if forwarded else host


# ----------------------------------------------------------------------
# 把 HTTP 请求变成脚本入参（脚本当 API 端点用）
# ----------------------------------------------------------------------
# 传给脚本的请求头白名单：脚本可能要看 Content-Type / 调用方标识，
# 但绝不能看到 X-API-Key 这类凭据，所以用白名单而不是"全部减去黑名单"。
_SCRIPT_HEADER_ALLOWLIST = (
    "content-type", "accept", "accept-language", "user-agent", "x-request-id",
    "x-forwarded-for", "x-real-ip", "referer", "origin", "host",
)

# 脚本结果里的保留键：指定 HTTP 状态码与响应头，自己不出现在响应体里
_STATUS_KEY = "__status"
_HEADERS_KEY = "__headers"
_MAX_RESPONSE_HEADERS = 16
_MAX_RESPONSE_HEADER_CHARS = 1024
_BLOCKED_RESPONSE_HEADERS = {
    "content-length", "transfer-encoding", "connection", "keep-alive", "upgrade",
}


async def _request_context(request: Request) -> dict:
    """这次请求本身的元信息，脚本里是 ``ctx.request``。"""
    query: dict[str, str] = {}
    for key, value in request.query_params.multi_items():
        query.setdefault(key, value)  # 同名参数取第一个，脚本侧更好用
    headers = {
        name: request.headers[name]
        for name in _SCRIPT_HEADER_ALLOWLIST
        if name in request.headers
    }
    return {
        "method": request.method,
        "path": request.url.path,
        "query": query,
        "headers": headers,
        "ip": request.client.host if request.client else "",
        "content_type": request.headers.get("content-type") or "",
    }


def _parse_body(raw: bytes) -> Any:
    """把请求体解析成脚本能用的值：JSON 就解析，否则原样给字符串；空体给 None。"""
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except ValueError:
        return text  # 不是 JSON（表单、纯文本）就原样给字符串


async def _script_input(request: Request) -> tuple[Any, Any, str | None, dict]:
    """从请求里取出脚本入参，返回 ``(payload, body, code_override, ctx_request)``。

    三种调用姿势：

    1. ``{"car": "AGV-07"}``                直接 POST 业务 JSON —— 入参就是它
    2. ``?car=AGV-07``（GET/POST 都行）      只用 query —— 入参是 query（值都是字符串）
    3. ``{"payload": {...}, "code": "..."}`` 老式包装体（前端在用）—— 入参是 ``payload``

    query 与 body 同时给时会合并，body 优先（同名字段以 body 为准）。
    ``body``（``ctx.body``）始终是 JSON 解析后的原始请求体，数组/字符串也照样给它。
    """
    ctx_request = await _request_context(request)
    query = dict(ctx_request["query"])

    body = _parse_body(await request.body())
    ctx_request["body"] = body  # 脚本里 ctx.request.body 与 ctx.body 是同一个值

    code_override: str | None = None
    if isinstance(body, dict) and isinstance(body.get("payload"), dict):
        # 老式包装体：payload 是入参，code 是临时覆盖正文
        if isinstance(body.get("code"), str):
            code_override = body["code"]
        payload: Any = {**query, **body["payload"]}
    elif isinstance(body, dict):
        # 直接 POST 业务 JSON：整个 body 就是入参（"code" 这样的字段也原样给脚本）
        payload = {**query, **body}
    else:
        # 没有对象 body：query 就是入参；数组/标量 body 只通过 ctx.body 暴露
        payload = dict(query)

    return payload, body, code_override, ctx_request


def _extract_response_meta(result: Any) -> tuple[int | None, dict[str, str]]:
    """取出脚本用 ``__status`` / ``__headers`` 指定的响应元信息（并从结果里摘掉）。"""
    if not isinstance(result, dict):
        return None, {}

    status = result.pop(_STATUS_KEY, None)
    headers_raw = result.pop(_HEADERS_KEY, None)

    code: int | None = None
    if not isinstance(status, bool) and isinstance(status, (int, float)):
        candidate = int(status)
        if 100 <= candidate <= 599:
            code = candidate

    headers: dict[str, str] = {}
    if isinstance(headers_raw, dict):
        for key, value in list(headers_raw.items())[:_MAX_RESPONSE_HEADERS]:
            name = str(key).strip()
            text = str(value)
            if not name or len(text) > _MAX_RESPONSE_HEADER_CHARS:
                continue
            if any(ch in name for ch in "\r\n:") or any(ch in text for ch in "\r\n"):
                continue  # 防响应头注入
            if name.lower() in _BLOCKED_RESPONSE_HEADERS:
                continue  # 由 ASGI 服务器自己管
            headers[name] = text

    return code, headers


# ----------------------------------------------------------------------
# 运行时
# ----------------------------------------------------------------------
@user_script_router.get("/runtime")
async def runtime_status(_: dict = Depends(require_access)):
    """运行时信息 + 端到端自检（顺带验证 Nuitka 产物里 lupa 原生模块是否齐全）。"""
    config = lua_runtime.script_config()
    health = lua_runtime.runtime_healthcheck()
    # api_key 不回传：前端只需要知道"配没配"，不需要知道内容
    safe_config = {k: v for k, v in config.items() if k != "api_key"}
    safe_config["api_key_set"] = bool(config.get("api_key"))
    return {
        "success": health.ok,
        "config": safe_config,
        "healthcheck": health.to_dict("__healthcheck__"),
        "storage": get_store().storage_info(),
    }


# ----------------------------------------------------------------------
# 临时执行（不落库）
# ----------------------------------------------------------------------
@user_script_router.post("/run")
async def run_adhoc(payload: AdhocRun, request: Request, config: dict = Depends(require_access)):
    """执行一段临时 Lua 代码，便于调试后再保存为脚本。"""
    ctx_request = await _request_context(request)
    ctx_request["body"] = payload.payload  # adhoc 的入参就是 body 里的 payload
    result = await lua_runtime.execute_script_async(
        payload.code,
        payload.payload,
        script_id=payload.script_id or "adhoc",
        config=config,
        request=ctx_request,
    )
    logger.info(
        f"用户脚本临时执行 script_id={payload.script_id} "
        f"ok={result.ok} status={result.status} {result.duration_ms}ms"
    )
    body = result.to_dict(payload.script_id or "adhoc")
    http_status, extra_headers = _extract_response_meta(body.get("result"))
    if http_status is not None:
        body["http_status"] = http_status
    return JSONResponse(
        status_code=http_status or 200,
        content=body,
        headers=extra_headers or None,
    )


# ----------------------------------------------------------------------
# 脚本 CRUD
# ----------------------------------------------------------------------
@user_script_router.get("")
@user_script_router.get("/")
async def list_scripts(
    include_code: bool = Query(False, description="是否返回脚本正文"),
    _: dict = Depends(require_access),
):
    scripts = get_store().list(include_code=include_code)
    return {"success": True, "count": len(scripts), "scripts": scripts}


@user_script_router.post("")
@user_script_router.post("/")
async def create_script(payload: ScriptCreate, _: dict = Depends(require_access)):
    config = lua_runtime.script_config()

    if payload.validate_code:
        check = lua_runtime.execute_script(
            payload.code, None, script_id=payload.script_id, mode="check", config=config
        )
        if not check.ok:
            raise _error(f"脚本语法检查未通过: {check.error}", 400)

    try:
        script = get_store().create(
            payload.script_id,
            payload.code,
            name=payload.name,
            description=payload.description,
            enabled=payload.enabled,
        )
    except ScriptIdInvalid as exc:
        raise _error(str(exc)) from exc
    except ValueError as exc:
        raise _error(str(exc)) from exc

    logger.info(f"新建用户脚本: {payload.script_id}")
    return {"success": True, "script": script}


@user_script_router.get("/{script_id}")
async def get_script(script_id: str, _: dict = Depends(require_access)):
    script = get_store().get(script_id)
    if script is None:
        raise _error(f"脚本不存在: {script_id}", 404)
    return {"success": True, "script": script}


@user_script_router.put("/{script_id}")
async def update_script(
    script_id: str, payload: ScriptUpdate, _: dict = Depends(require_access)
):
    config = lua_runtime.script_config()

    if payload.code is not None and payload.validate_code:
        check = lua_runtime.execute_script(
            payload.code, None, script_id=script_id, mode="check", config=config
        )
        if not check.ok:
            raise _error(f"脚本语法检查未通过: {check.error}", 400)

    try:
        script = get_store().update(
            script_id,
            code=payload.code,
            name=payload.name,
            description=payload.description,
            enabled=payload.enabled,
        )
    except ScriptNotFound as exc:
        raise _error(f"脚本不存在: {script_id}", 404) from exc
    except ValueError as exc:
        raise _error(str(exc)) from exc

    logger.info(f"更新用户脚本: {script_id} -> v{script['version']}")
    return {"success": True, "script": script}


@user_script_router.delete("/{script_id}")
async def delete_script(script_id: str, _: dict = Depends(require_access)):
    if not get_store().delete(script_id):
        raise _error(f"脚本不存在: {script_id}", 404)
    logger.info(f"删除用户脚本: {script_id}")
    return {"success": True, "script_id": script_id}


# ----------------------------------------------------------------------
# 检查 / 执行
# ----------------------------------------------------------------------
@user_script_router.post("/{script_id}/check")
async def check_script(
    script_id: str, payload: CheckRequest | None = None, _: dict = Depends(require_access)
):
    """只做语法检查，不执行。"""
    config = lua_runtime.script_config()
    code = payload.code if payload and payload.code else None
    if code is None:
        script = get_store().get(script_id)
        if script is None:
            raise _error(f"脚本不存在: {script_id}", 404)
        code = script["code"]

    result = lua_runtime.execute_script(
        code, None, script_id=script_id, mode="check", config=config
    )
    return {
        "success": result.ok,
        "script_id": script_id,
        "error": result.error or None,
        "error_type": result.error_type or None,
        "duration_ms": result.duration_ms,
        "runtime": result.runtime or None,
    }


async def _run_saved(
    script_id: str,
    request: Request,
    payload: Any,
    code_override: str | None,
    ctx_request: dict | None = None,
):
    config = lua_runtime.script_config()
    store = get_store()

    script = store.get(script_id)
    if script is None:
        raise _error(f"脚本不存在: {script_id}", 404)
    if not script["enabled"] and code_override is None:
        raise _error(f"脚本已禁用: {script_id}（先 PUT enabled=true 再执行）", 403)

    code = code_override if code_override is not None else script["code"]
    payload_bytes = len(
        json.dumps(payload if payload is not None else {}, ensure_ascii=False).encode("utf-8")
    )

    result = await lua_runtime.execute_script_async(
        code, payload, script_id=script_id, config=config, request=ctx_request
    )

    result_bytes = len(json.dumps(result.result, ensure_ascii=False).encode("utf-8")) if result.ok else 0
    store.record_run(
        script_id,
        ok=result.ok,
        status=result.status,
        error=result.error,
        duration_ms=result.duration_ms,
        payload_bytes=payload_bytes,
        result_bytes=result_bytes,
        source=_client_source(request),
    )

    level = "info" if result.ok else "warning"
    getattr(logger, level)(
        f"执行用户脚本 {script_id} v{script['version']}: ok={result.ok} "
        f"status={result.status} {result.duration_ms}ms"
        + ("" if result.ok else f" err={result.error.splitlines()[0][:200] if result.error else ''}")
    )

    body = result.to_dict(script_id)
    body["version"] = script["version"]

    # 脚本可以用 __status / __headers 决定 HTTP 状态码与响应头（当 API 端点用时很有必要），
    # 这两个键会从响应体里摘掉，不会跟着数据一起返回。
    http_status, extra_headers = _extract_response_meta(body.get("result"))
    if http_status is not None:
        body["http_status"] = http_status

    # 脚本自身报错仍然返回 200：请求本身是成功的，"脚本失败"是业务结果，
    # 由调用方读 ok / error_type 判断（便于前端直接把 error 展示出来）。
    # 只有脚本显式给了 __status 才改状态码 —— 那是它作为 API 端点的表态。
    return JSONResponse(
        status_code=http_status or 200,
        content=body,
        headers=extra_headers or None,
    )


@user_script_router.post("/{script_id}/run")
@user_script_router.get("/{script_id}/run")
async def run_script(
    script_id: str,
    request: Request,
    _: dict = Depends(require_access),
):
    """执行已保存的脚本 —— **脚本即 API 端点**，其他服务直接调这个地址。

    三种调用姿势都支持（见 ``_script_input``）：

    * ``POST .../{id}/run`` + ``{"car": "AGV-07"}``   —— 直接 POST 业务 JSON
    * ``GET  .../{id}/run?car=AGV-07``                —— 只带 query，最省事
    * ``POST .../{id}/run`` + ``{"payload": {...}}``  —— 老式包装体（前端在用）

    返回体是执行信封（``ok`` / ``duration_ms`` / ``result`` / ``logs`` ...），
    脚本的返回值在 ``result`` 里；脚本可以用 ``__status`` / ``__headers`` 指定
    HTTP 状态码与响应头。
    """
    payload, _body, code_override, ctx_request = await _script_input(request)
    return await _run_saved(script_id, request, payload, code_override, ctx_request)


@user_script_router.post("/{script_id}")
async def run_script_alias(
    script_id: str,
    request: Request,
    _: dict = Depends(require_access),
):
    """``POST /api/user-script/{id}`` —— 与 ``/{id}/run`` 等价的别名。"""
    payload, _body, code_override, ctx_request = await _script_input(request)
    return await _run_saved(script_id, request, payload, code_override, ctx_request)


@user_script_router.get("/{script_id}/runs")
async def script_runs(
    script_id: str,
    limit: int = Query(50, ge=1, le=500),
    _: dict = Depends(require_access),
):
    return {
        "success": True,
        "script_id": script_id,
        "runs": get_store().list_runs(script_id, limit=limit),
    }
