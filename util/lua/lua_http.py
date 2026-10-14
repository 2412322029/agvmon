"""用户脚本的外部 HTTP 客户端（只在 worker 子进程里用）。

为什么单独一个模块
==================

脚本里的 ``http`` 表是纯 Lua 写的，但它不能自己联网 —— 真正的请求动作由宿主
Python 完成。桥接方式见 ``util/lua/lua_sandbox.py`` 的 ``__install_http``：

* Lua → Python 只传一个 JSON 字符串（请求描述）；
* Python → Lua 只回一个 JSON 字符串（结果）；
* Python 可调用对象只在安装时作为 upvalue 存进 Lua 闭包，脚本拿不到它，
  因此 ``http.request.__globals__`` 这类爬 Python 对象的逃逸路径不成立。

策略（HttpPolicy）
=================

脚本能做什么，完全由 config.toml 的 ``[user_script.http]`` 决定：

* ``enabled``：总开关，关掉后所有请求返回 ``error_type=http_disabled``；
* ``allowed_hosts`` / ``blocked_hosts``：主机白名单/黑名单（支持 ``*.example.com``）；
* ``allow_private_hosts``：是否允许内网/回环地址（默认禁止，防 SSRF）；
* ``timeout_ms`` / ``max_requests_per_run`` / ``max_request_kb`` / ``max_response_kb``；
* ``max_redirects``：重定向每一跳都会重新过一遍策略，避免用跳转绕过白名单。

只用标准库 urllib，不引入新依赖，Nuitka 也无需额外配置。

DNS 说明：策略校验会解析一次域名来判断是不是内网，urllib 实际连接时会再解析一次
（存在极小的 TOCTOU 窗口）—— 对"本机可调用的运维工具"这个定位足够了。
"""

from __future__ import annotations

import ipaddress
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

# 允许的方法（够覆盖 REST 场景，不给 CONNECT/TRACE 这类东西）
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}

# 由 urllib 自己管理的头，脚本不能覆盖
FORBIDDEN_HEADERS = {"host", "content-length", "connection", "transfer-encoding", "expect", "upgrade"}

MAX_HEADERS = 32
MAX_HEADER_CHARS = 2048
MAX_URL_CHARS = 2048

DEFAULT_POLICY: dict[str, Any] = {
    "enabled": True,
    "allowed_hosts": [],
    "blocked_hosts": [],
    "allow_private_hosts": False,
    "timeout_ms": 4000,
    "max_request_kb": 256,
    "max_response_kb": 512,
    "max_requests_per_run": 6,
    "max_redirects": 3,
    "user_agent": "agvmon-user-script/1.0",
}

_CLAMPS = {
    "timeout_ms": (100, 60_000),
    "max_request_kb": (1, 8192),
    "max_response_kb": (1, 8192),
    "max_requests_per_run": (1, 64),
    "max_redirects": (0, 10),
}


class HttpPolicyError(RuntimeError):
    """策略/传输层错误，带上给脚本看的 error_type。"""

    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type


@dataclass
class HttpPolicy:
    enabled: bool = True
    allowed_hosts: list[str] = field(default_factory=list)
    blocked_hosts: list[str] = field(default_factory=list)
    allow_private_hosts: bool = False
    timeout_ms: int = 2500
    max_request_kb: int = 256
    max_response_kb: int = 512
    max_requests_per_run: int = 6
    max_redirects: int = 3
    user_agent: str = "agvmon-user-script/1.0"

    @classmethod
    def from_config(cls, raw: Mapping[str, Any] | None) -> "HttpPolicy":
        """把 config.toml 里的 [user_script.http] 归一化成策略对象。"""
        merged = dict(DEFAULT_POLICY)
        if isinstance(raw, Mapping):
            for key in DEFAULT_POLICY:
                value = raw.get(key)
                if value is not None:
                    merged[key] = value

        for key, (low, high) in _CLAMPS.items():
            try:
                merged[key] = max(low, min(high, int(merged[key])))
            except (TypeError, ValueError):
                merged[key] = DEFAULT_POLICY[key]

        for key in ("allowed_hosts", "blocked_hosts"):
            value = merged[key]
            if isinstance(value, str):
                value = [value]
            merged[key] = [str(v).strip().lower() for v in (value or []) if str(v).strip()]

        merged["enabled"] = bool(merged["enabled"])
        merged["allow_private_hosts"] = bool(merged["allow_private_hosts"])
        merged["user_agent"] = str(merged["user_agent"] or DEFAULT_POLICY["user_agent"])
        return cls(**merged)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # ------------------------------------------------------------------
    # 主机策略
    # ------------------------------------------------------------------
    def match_host(self, host: str) -> bool:
        """主机是否在允许范围内（不解析 DNS，只看名字）。"""
        host = (host or "").strip().lower().rstrip(".")
        if not host:
            return False
        for pattern in self.blocked_hosts:
            if _host_matches(host, pattern):
                return False
        if not self.allowed_hosts:
            return True
        return any(_host_matches(host, pattern) for pattern in self.allowed_hosts)


def _host_matches(host: str, pattern: str) -> bool:
    """``*.example.com`` 通配（含子域，不含裸域）；其余按精确匹配。"""
    pattern = (pattern or "").strip().lower().rstrip(".")
    if not pattern:
        return False
    if pattern.startswith("*."):
        return host.endswith(pattern[1:]) and host != pattern[2:]
    return host == pattern


def _is_blocked_ip(ip: str) -> bool:
    """内网/回环/链路本地/保留/组播地址一律算"不可直连"。"""
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return True
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def check_url(url: str, policy: HttpPolicy) -> urllib.parse.SplitResult:
    """校验 URL 是否允许访问；不允许就抛 ``HttpPolicyError``。"""
    if not isinstance(url, str) or not url.strip():
        raise HttpPolicyError("http_url", "URL 不能为空")
    url = url.strip()
    if len(url) > MAX_URL_CHARS:
        raise HttpPolicyError("http_url", f"URL 太长（>{MAX_URL_CHARS} 字符）")

    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise HttpPolicyError(
            "http_scheme", f"只支持 http/https，收到 {parsed.scheme or '(空)'}"
        )
    host = parsed.hostname
    if not host:
        raise HttpPolicyError("http_url", f"URL 里没有主机名：{url}")
    if parsed.username or parsed.password:
        raise HttpPolicyError("http_url", "URL 里不允许带用户名密码")

    if not policy.match_host(host):
        raise HttpPolicyError(
            "http_blocked",
            f"主机 {host} 不在允许列表内（config.toml 的 [user_script.http] allowed_hosts）"
            if policy.allowed_hosts
            else f"主机 {host} 被 blocked_hosts 拦下",
        )

    if not policy.allow_private_hosts:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        for ip in _resolve(host, port):
            if _is_blocked_ip(ip):
                raise HttpPolicyError(
                    "http_blocked",
                    f"主机 {host} 解析到内网地址 {ip}，已被策略拦下"
                    "（确需访问内网请把 [user_script.http] allow_private_hosts 设为 true）",
                )
    return parsed


def _resolve(host: str, port: int) -> list[str]:
    """解析主机名；字面 IP 直接返回。解析不了抛 http_dns。"""
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise HttpPolicyError("http_dns", f"域名解析失败：{host}（{exc}）") from exc
    except OSError as exc:
        raise HttpPolicyError("http_dns", f"域名解析失败：{host}（{exc}）") from exc
    out = []
    for info in infos:
        ip = info[4][0]
        if ip not in out:
            out.append(ip)
    if not out:
        raise HttpPolicyError("http_dns", f"域名解析结果为空：{host}")
    return out


def _sanitize_headers(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise HttpPolicyError("http_badarg", "headers 必须是对象")
    if len(raw) > MAX_HEADERS:
        raise HttpPolicyError("http_badarg", f"请求头数量超过 {MAX_HEADERS}")
    out: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key).strip()
        text = "" if value is None else str(value)
        if not name or len(name) > 128 or len(text) > MAX_HEADER_CHARS:
            raise HttpPolicyError("http_badarg", f"请求头不合法：{name!r}")
        if any(ch in name for ch in "\r\n:") or any(ch in text for ch in "\r\n"):
            raise HttpPolicyError("http_badarg", f"请求头含非法字符（防注入）：{name!r}")
        if name.lower() in FORBIDDEN_HEADERS:
            continue  # 由 urllib 自己管，忽略而不是报错
        out[name] = text
    return out


class HttpBridge:
    """挂在沙箱里的 ``http`` 表背后的实际执行者。

    对 Lua 只暴露 ``__call__(spec_json) -> result_json``；任何异常都会被转成
    ``{"ok": false, "error": ...}``，绝不让 Python 异常冒进 Lua。
    """

    def __init__(self, policy: HttpPolicy, budget_ms: int | None = None):
        self.policy = policy
        self.budget_ms = budget_ms
        self.started = time.perf_counter()
        self.requests = 0
        self.redirects = 0

    # ------------------------------------------------------------------
    # 对 Lua 的入口
    # ------------------------------------------------------------------
    def __call__(self, spec_json: str) -> str:
        started = time.perf_counter()
        try:
            spec = json.loads(spec_json) if isinstance(spec_json, str) else {}
            if not isinstance(spec, dict):
                raise HttpPolicyError("http_badarg", "请求描述必须是 JSON 对象")
            result = self.request(spec)
        except HttpPolicyError as exc:
            result = {"ok": False, "error": str(exc), "error_type": exc.error_type}
        except Exception as exc:  # 任何意外都不许把 Python 异常漏给脚本
            result = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "error_type": "http_internal",
            }
        result["duration_ms"] = int((time.perf_counter() - started) * 1000)
        return json.dumps(result, ensure_ascii=False, default=str)

    # ------------------------------------------------------------------
    # 真正干活
    # ------------------------------------------------------------------
    def request(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        policy = self.policy
        if not policy.enabled:
            raise HttpPolicyError(
                "http_disabled",
                "外部 HTTP 已禁用（config.toml 里 [user_script.http] enabled = false）",
            )

        url = str(spec.get("url") or "")
        method = str(spec.get("method") or "GET").upper()
        if method not in ALLOWED_METHODS:
            raise HttpPolicyError(
                "http_method", f"不支持的 method：{method}（可用 {'/'.join(sorted(ALLOWED_METHODS))}）"
            )

        self.requests += 1
        if self.requests > policy.max_requests_per_run:
            raise HttpPolicyError(
                "http_busy",
                f"单次执行最多调用 {policy.max_requests_per_run} 次外部接口，已用完",
            )

        parsed = check_url(url, policy)

        headers = _sanitize_headers(spec.get("headers"))
        body_text = spec.get("body")
        if body_text is not None and not isinstance(body_text, str):
            raise HttpPolicyError("http_badarg", "body 必须是字符串")
        body = body_text.encode("utf-8") if body_text else None
        if body is not None and len(body) > policy.max_request_kb * 1024:
            raise HttpPolicyError(
                "http_size",
                f"请求体 {len(body) // 1024}KB 超过上限 {policy.max_request_kb}KB",
            )
        if body is not None and method in ("GET", "HEAD"):
            raise HttpPolicyError("http_badarg", f"{method} 请求不允许带 body")

        timeout_s = self._timeout_seconds(spec.get("timeout_ms"))

        url = urllib.parse.urlunsplit(parsed)
        request = urllib.request.Request(url, data=body, method=method)
        for name, value in headers.items():
            request.add_header(name, value)
        if not any(k.lower() == "user-agent" for k in headers):
            request.add_header("User-Agent", policy.user_agent)
        request.add_header("Accept", "*/*")

        opener = urllib.request.build_opener(_PolicyRedirectHandler(self))
        limit = policy.max_response_kb * 1024
        started = time.perf_counter()

        try:
            with opener.open(request, timeout=timeout_s) as response:
                raw, truncated = _read_capped(response, limit)
                status = response.status
                resp_headers = response.headers
                final_url = response.geturl()
        except urllib.error.HTTPError as exc:
            # 4xx/5xx：urllib 把它当异常抛，但"拿到了应答"本身是成功的传输
            raw, truncated = _read_capped(exc, limit)
            status = exc.code
            resp_headers = exc.headers
            final_url = exc.geturl() if hasattr(exc, "geturl") else url
        except HttpPolicyError:
            raise
        except (socket.timeout, TimeoutError) as exc:
            raise HttpPolicyError(
                "http_timeout", f"请求超时（{timeout_s * 1000:.0f}ms）：{url}"
            ) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise HttpPolicyError(
                    "http_timeout", f"请求超时（{timeout_s * 1000:.0f}ms）：{url}"
                ) from exc
            raise HttpPolicyError("http_network", f"网络错误：{reason}") from exc
        except Exception as exc:
            raise HttpPolicyError("http_network", f"{type(exc).__name__}: {exc}") from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        text = raw.decode("utf-8", errors="replace")
        return {
            "ok": True,
            "status": status,
            "headers": _headers_dict(resp_headers),
            "content_type": (resp_headers.get("Content-Type") if resp_headers else "") or "",
            "body": text,
            "bytes": len(raw),
            "truncated": truncated,
            "url": final_url,
            "redirects": self.redirects,
            "duration_ms": duration_ms,
        }

    def _timeout_seconds(self, requested: Any) -> float:
        """单次超时 = min(脚本要求, 策略上限, 脚本剩余时间)。"""
        policy_ms = self.policy.timeout_ms
        try:
            want = int(requested)
        except (TypeError, ValueError):
            want = policy_ms
        timeout_ms = max(100, min(policy_ms, want if want > 0 else policy_ms))

        if self.budget_ms is not None:
            remaining = self.budget_ms - int((time.perf_counter() - self.started) * 1000)
            if remaining <= 100:
                raise HttpPolicyError(
                    "http_timeout",
                    "脚本剩余执行时间不足，无法发起外部请求"
                    "（把 [user_script] timeout_ms 调大即可）",
                )
            timeout_ms = min(timeout_ms, remaining - 50)
        return max(0.1, timeout_ms / 1000.0)

    # 重定向钩子用
    def note_redirect(self, new_url: str) -> None:
        self.redirects += 1
        if self.redirects > self.policy.max_redirects:
            raise HttpPolicyError(
                "http_blocked",
                f"重定向次数超过上限 {self.policy.max_redirects}",
            )
        check_url(new_url, self.policy)  # 每一跳都重新过策略


def _read_capped(response: Any, limit: int) -> tuple[bytes, bool]:
    raw = response.read(limit + 1)
    if len(raw) > limit:
        return raw[:limit], True
    return raw, False


def _headers_dict(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    out: dict[str, str] = {}
    try:
        items = headers.items()
    except AttributeError:
        return out
    for key, value in items:
        name = str(key).lower()
        text = str(value)
        if len(text) > MAX_HEADER_CHARS:
            text = text[:MAX_HEADER_CHARS]
        out[name] = f"{out[name]}, {text}" if name in out else text
    return out


class _PolicyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """重定向也要过策略：否则 302 到 127.0.0.1 就能绕过内网限制。"""

    def __init__(self, bridge: HttpBridge):
        super().__init__()
        self.bridge = bridge

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urljoin(req.full_url, newurl)
        self.bridge.note_redirect(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


def make_bridge(policy: HttpPolicy | Mapping[str, Any] | None = None, budget_ms: int | None = None) -> HttpBridge:
    """便捷构造：policy 可以直接给 dict（config 里的那一坨）。"""
    if isinstance(policy, HttpPolicy):
        resolved = policy
    else:
        resolved = HttpPolicy.from_config(policy)
    return HttpBridge(resolved, budget_ms=budget_ms)
