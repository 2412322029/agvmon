#!/usr/bin/env python3
"""用户自定义 Lua 脚本 API 冒烟测试。

用法（务必在项目根目录执行，cfg 依赖 cwd 下的 config.toml）::

    .venv\\Scripts\\python.exe test_user_script.py

覆盖范围
========
* 沙箱逃逸回归：os/io/package/debug/load/python 等全局必须不存在，且 Lua 侧
  不能通过属性链摸到任何 Python 对象；
* JSON 语义：null 哨兵、数组空洞、转义、代理对、循环引用；
* 资源限制：死循环被强杀、Lua 内存超限、结果/脚本体积超限；
* 脚本库 CRUD 与执行审计；
* HTTP 接口（TestClient + 依赖覆盖）与访问闸门（本机/远程/API Key）。

不依赖 Redis / RCMS：脚本执行链路本身与它们无关。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if Path.cwd() != ROOT:
    print(f"请在项目根目录执行本脚本（当前 {Path.cwd()}）")
    sys.exit(2)

# Windows 控制台默认 GBK：正文里的 emoji（代理对用例）会让 print 抛
# UnicodeEncodeError 把测试打断，这里把编码错误降级成替换字符。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def section(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def check(label: str, ok: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {label}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  [FAIL] {label}" + (f"  -> {detail}" if detail else ""))
    return ok


# ----------------------------------------------------------------------
# 测试用的假上游 / 假下游
# ----------------------------------------------------------------------
def make_mock_server():
    """起一个本地 HTTP 服务当"外部 API"，返回 (server, port, received)。

    接口刻意模仿 postman-echo / httpbin 的 echo 结构（``/api/echo`` 回显查询参数、
    ``/api/echo-post`` 把收到的 body 放进 ``data`` 回显），这样示例脚本里那套
    "取上游 → 处理 → 中转" 的逻辑不用改一个字就能在本地确定性验证。
    """
    import threading
    import urllib.parse
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 别刷屏
            pass

        def _send(self, code: int, payload, ctype: str = "application/json", extra=None):
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _record(self, body: str = ""):
            received.append({
                "method": self.command,
                "path": self.path,
                "body": body,
                "content_type": self.headers.get("Content-Type"),
                "x_trace": self.headers.get("X-Trace"),
            })

        def do_GET(self):
            self._record()
            parsed = urllib.parse.urlsplit(self.path)
            path = parsed.path
            if path == "/api/json":
                # 形如 httpbin.org/json 的上游结构
                self._send(200, {"slideshow": {"title": "AGV 任务", "author": "wcs"}})
            elif path == "/api/echo":
                # 形如 postman-echo.com/get：把收到的查询参数原样回显
                args = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
                self._send(200, {"args": args, "url": self.path, "headers": {"host": self.headers.get("Host")}})
            elif path == "/api/text":
                self._send(200, b"plain text body", "text/plain; charset=utf-8")
            elif path == "/api/big":
                self._send(200, b"x" * (300 * 1024), "text/plain; charset=utf-8")
            elif path == "/api/slow":
                time.sleep(1.5)
                self._send(200, {"slow": True})
            elif path == "/api/500":
                self._send(500, {"error": "boom"})
            elif path == "/api/redirect":
                port = self.server.server_address[1]
                self._send(302, b"", "text/plain", {"Location": f"http://localhost:{port}/api/json"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n).decode("utf-8", "replace")
            self._record(body)
            parsed_path = urllib.parse.urlsplit(self.path).path
            if parsed_path == "/api/echo-post":
                # 形如 postman-echo.com/post：把收到的 body 放回 data 字段
                try:
                    echoed = json.loads(body) if body else None
                except ValueError:
                    echoed = body
                self._send(200, {"accepted": True, "data": echoed, "bytes": len(body)})
            else:
                self._send(200, {"accepted": True, "bytes": len(body)})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1], received


def frontend_sandbox_names() -> list[str]:
    """从 web/src/composables/luaLanguage.js 抠出前端声称的沙箱全局名字。"""
    import re

    text = (ROOT / "web" / "src" / "composables" / "luaLanguage.js").read_text(encoding="utf-8")
    match = re.search(r"export const SANDBOX_GLOBALS = \[(.*?)\n\]", text, re.S)
    if not match:
        return []
    return sorted(re.findall(r"\{ name: '([^']+)'", match.group(1)))


def frontend_examples() -> list[tuple[str, str]]:
    """从 web/src/composables/luaExamples.js 抠出示例（变量名, Lua 正文）。"""
    import re

    text = (ROOT / "web" / "src" / "composables" / "luaExamples.js").read_text(encoding="utf-8")
    return [
        (m.group(1), m.group(2))
        for m in re.finditer(r"const (ECHO|API_ENDPOINT|RELAY|VALIDATE) = `(.*?)`", text, re.S)
    ]


def guide_lua_blocks() -> list[tuple[int, str]]:
    """从 LUA_SCRIPT_GUIDE.md 抠出 ```lua 代码块，返回 (代码首行行号, 代码)。

    那份文档是写给 AI 照着写脚本用的，里面的 Lua 片段必须真能编译 —— 否则就是陷阱。
    """
    import re

    path = ROOT / "LUA_SCRIPT_GUIDE.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [
        (text[: m.start()].count("\n") + 2, m.group(1))
        for m in re.finditer(r"```lua\n(.*?)```", text, re.S)
    ]


# ----------------------------------------------------------------------
# 用户脚本页的前端自检
#
# 这些检查原来放在 web/test_*.mjs（需要 node），现在跟着这份 Python 冒烟测试跑，
# 不额外往仓库里放文件；覆盖面比用 vue 编译器窄一些，但正好卡住踩过的两类坑：
#   1) 模板里用了 <script setup> 中不存在的名字 —— 构建期不报错，点下去才炸
#      （「运行」按钮写成 @click="switchToRun" 而函数叫 runNow 就是这么死的）；
#   2) monaco 子模块路径 / 编辑器选项名写错 —— vite build 也不报，运行时静默失效。
# ----------------------------------------------------------------------
# 模板表达式里可以出现的全局（其余裸名字都必须在 <script setup> 里定义）
TEMPLATE_GLOBALS = {
    "$event", "Math", "JSON", "Number", "String", "Boolean", "Object", "Array", "Date",
    "RegExp", "Map", "Set", "Promise", "parseInt", "parseFloat", "isNaN", "isFinite",
    "encodeURIComponent", "decodeURIComponent", "encodeURI", "decodeURI",
    "console", "window", "document", "navigator", "location", "history", "fetch", "URL",
    "URLSearchParams", "Blob", "FormData", "setTimeout", "clearTimeout", "setInterval",
    "clearInterval", "requestAnimationFrame", "alert", "confirm", "prompt",
    "undefined", "NaN", "Infinity", "true", "false", "null", "new", "typeof", "in", "of",
    "void", "this", "instanceof", "async", "await", "return", "delete",
}


def vue_script_bindings(source: str) -> set[str]:
    """从 ``<script setup>`` 里抠出顶层声明名（正则够用，不求完备）。"""
    import re

    names: set[str] = set()
    for pattern in (
        r"^\s*(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*[=,:]",
        r"^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)",
        r"^\s*import\s+([A-Za-z_$][\w$]*)\s*(?:,|from)",
    ):
        names.update(m.group(1) for m in re.finditer(pattern, source, re.M))
    for m in re.finditer(r"^\s*(?:const|let|var)\s*\{([^}]*)\}\s*=", source, re.M):
        names.update(p.split(":")[-1].strip() for p in m.group(1).split(",") if p.strip())
    for m in re.finditer(r"^\s*import\s*\{([^}]*)\}\s*from", source, re.M):
        names.update(p.split(" as ")[-1].strip() for p in m.group(1).split(",") if p.strip())

    # defineProps([...]) / defineProps({...}) / defineProps<{...}>()：模板里能直接用 props 名
    for m in re.finditer(r"defineProps\s*[<(]", source):
        rest = source[m.end() - 1:]
        start = next((i for i, ch in enumerate(rest) if ch in "[{"), None)
        if start is None:
            continue
        opener = rest[start]
        closer = "]" if opener == "[" else "}"
        depth, end = 0, None
        for i in range(start, len(rest)):
            if rest[i] == opener:
                depth += 1
            elif rest[i] == closer:
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end is None:
            continue
        block = rest[start + 1: end]
        if opener == "[":
            names.update(p.strip().strip("'\"") for p in block.split(",") if p.strip())
        else:
            names.update(m2.group(1) for m2 in re.finditer(r"([A-Za-z_$][\w$]*)\s*[?:]", block))

    return names


def expression_code_only(expr: str) -> str:
    """去掉表达式里的字符串字面量（'…' "…" `…`），只留代码部分。

    模板字符串 ``${}`` 里面仍然是代码，递归保留 —— 否则
    ``\u0060/api/util/download/${file}\u0060`` 会被当成标识符 ``api`` / ``download``。
    """
    out: list[str] = []
    i, n = 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch in "'\"":
            quote, i = ch, i + 1
            while i < n:
                if expr[i] == "\\":
                    i += 2
                    continue
                if expr[i] == quote:
                    i += 1
                    break
                i += 1
            out.append('""')
            continue
        if ch == "`":
            i += 1
            while i < n:
                if expr[i] == "\\":
                    i += 2
                    continue
                if expr[i] == "`":
                    i += 1
                    break
                if expr[i] == "$" and i + 1 < n and expr[i + 1] == "{":
                    depth, j = 1, i + 2
                    while j < n and depth:
                        if expr[j] == "{":
                            depth += 1
                        elif expr[j] == "}":
                            depth -= 1
                        j += 1
                    # 用空格隔开，避免相邻插值被拼成一个标识符
                    out.append(" " + expression_code_only(expr[i + 2:j - 1]) + " ")
                    i = j
                    continue
                i += 1
            out.append('""')
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def vue_template_binding_problems(path: Path) -> list[str]:
    """模板里引用的名字是否都在 ``<script setup>`` 里定义过。"""
    import re

    text = path.read_text(encoding="utf-8", errors="replace")
    template = re.search(r"<template>(.*)</template>", text, re.S)
    if not template:
        return []
    script = re.search(r"<script setup[^>]*>(.*?)</script>", text, re.S)
    if not script:
        return []  # 选项式 API：模板走 _ctx.data/methods，不在本检查范围
    declared = vue_script_bindings(script.group(1))

    problems: list[str] = []
    body = template.group(1)

    # 模板自己引入的局部名字（v-for 别名、插槽作用域）。真实作用域是按元素算的，
    # 这里退一步当成"整份模板里都算已定义" —— 会宽松一点，但不会误报。
    template_locals: set[str] = set()
    for m in re.finditer(r'v-for\s*=\s*"\(([^)]*)\)\s+(?:in|of)\b', body):
        template_locals.update(p.strip() for p in m.group(1).split(",") if p.strip())
    for m in re.finditer(r'v-for\s*=\s*"([A-Za-z_$][\w$]*)\s+(?:in|of)\b', body):
        template_locals.add(m.group(1))
    for m in re.finditer(r'(?:#[\w\-]+|v-slot:[\w\-]*)\s*=\s*"\{([^}]*)\}"', body):
        template_locals.update(
            p.split("=")[0].split(":")[-1].strip() for p in m.group(1).split(",") if p.strip()
        )
    known = declared | template_locals

    # 只看"表达式"：指令/绑定值 + 插值。普通 HTML 属性（class= / href=）不在此列。
    expressions = re.findall(r'(?<![\w\-])(?:@|:|v-)[a-zA-Z:.\-]*\s*=\s*"([^"]*)"', body)
    expressions += re.findall(r"\{\{(.*?)\}\}", body, re.S)

    # 1) 表达式里出现的裸名字必须在 setup 里定义过
    for expr in expressions:
        code = expression_code_only(expr)
        # 表达式内部的箭头函数参数是表达式局部名字（reduce((s,i) => ...) 这种嵌套括号也要认）
        expr_locals: set[str] = set()
        for m in re.finditer(r"\(([^)]*)\)\s*=>", code):
            expr_locals.update(re.findall(r"[A-Za-z_$][\w$]*", m.group(1)))
        expr_locals.update(m.group(1) for m in re.finditer(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*=>", code))
        for token in re.finditer(r"(?<![\w$.])([A-Za-z_$][\w$]*)", code):
            name = token.group(1)
            before = code[: token.start()].rstrip()
            after = code[token.end():].lstrip()
            if before and before[-1] in ".$":  # 属性访问（foo.bar）
                continue
            if after.startswith(":"):  # 对象字面量的 key
                continue
            if re.search(r"\b[A-Za-z_$][\w$]*\s*:\s*$", before) or before.endswith(("?", "|")):
                continue
            if name in known or name in expr_locals or name in TEMPLATE_GLOBALS:
                continue
            problems.append(f"未定义的名字 {name}（{path.name}: {expr.strip()[:60]}）")

    # 2) 赋值目标：模板里 `x = 1` 而 x 没定义 —— Home.vue 的 `stop = true` 就是这类
    for expr in expressions:
        for m in re.finditer(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*=(?![=>])", expression_code_only(expr)):
            name = m.group(1)
            if name in known or name in TEMPLATE_GLOBALS:
                continue
            problems.append(f"给未定义的名字赋值 {name}（{path.name}: {expr.strip()[:60]}）")

    return sorted(set(problems))


def monaco_wiring_problems() -> list[str]:
    """luaMonaco.js 的 monaco 接线是否对得上真正装上的那个包。"""
    import re

    problems: list[str] = []
    source = (ROOT / "web" / "src" / "composables" / "luaMonaco.js").read_text(encoding="utf-8")
    monaco_dir = ROOT / "web" / "node_modules" / "monaco-editor"

    # monaco 0.56 的 exports 是 "./*": "./esm/vs/*.js"，所以子模块写 monaco-editor/editor/xxx.js
    specs = re.findall(r"from\s+'monaco-editor/([^']+)'|import\s+'monaco-editor/([^']+)'", source)
    paths = [a or b for a, b in specs]
    if not paths:
        problems.append("luaMonaco.js 里没找到 monaco 子模块导入")
    for spec in paths:
        rel = spec.split("?")[0]  # 去掉 ?worker / ?worker&inline 这类查询串
        if rel.startswith("esm/"):
            problems.append(f"{spec} 会被 exports 规则拼成 esm/vs/esm/vs/... ，vite build 会解析失败")
            continue
        if not (monaco_dir / "esm" / "vs" / rel).exists():
            problems.append(f"{spec} 在 node_modules 里找不到对应文件")
    if not any(p == "editor/editor.api.js" for p in paths):
        problems.append("应该用 monaco-editor/editor/editor.api.js（editor.main.js 会带上全部语言）")
    if len([p for p in paths if "/contrib/" in p or "/quickAccess/" in p]) < 15:
        problems.append("按需引入的 contrib 特性太少，编辑器会缺功能")

    # 编辑器选项名必须在 monaco.d.ts 里存在
    dts = (monaco_dir / "monaco.d.ts").read_text(encoding="utf-8", errors="replace")
    start = source.find("monaco.editor.create(container, {")
    if start < 0:
        problems.append("找不到 monaco.editor.create 的选项对象")
        return problems
    depth, block = 0, ""
    for i in range(source.find("{", start), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                block = source[source.find("{", start) + 1: i]
                break
    keys = {m.group(1) for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*:", block)}
    for key in sorted(keys):
        if not re.search(rf"\b{re.escape(key)}\??\s*[:?]", dts):
            problems.append(f"编辑器选项 {key} 在 monaco.d.ts 里不存在（多半是拼错了）")
    if len(keys) < 30:
        problems.append(f"解析出来的编辑器选项只有 {len(keys)} 个，可能没解析对")

    return problems


def regex_group_layout(src: str) -> tuple[int, list[str]]:
    """扫一遍 JS 正则源码，返回（捕获组个数，顶层消费性原子）。

    monarch 的分组动作（``[/re/, ['a','b']]``）在词法分析时会检查"捕获组是否
    连续铺满整段匹配"，只要有一个字符落在所有捕获组之外且真的匹配上了，就会抛
    "with groups, all characters should be matched in consecutive groups"。
    所以顶层（不在任何捕获组里）的消费性字符都是隐患。前瞻/后顾是零宽的，内容
    不算消费；但里面的捕获组仍会被 JS 计入 matches，所以要一起数。
    """
    capture = 0
    atoms: list[str] = []
    frames: list[str] = []
    capt_depth = 0  # 未闭合的捕获组层数
    look_depth = 0  # 未闭合的零宽组层数
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "\\":
            atom = src[i : i + 2]
            if capt_depth == 0 and look_depth == 0 and atom not in ("\\b", "\\B"):
                atoms.append(atom)
            i += 2
            continue
        if c == "[":
            j = i + 1
            if j < n and src[j] == "^":
                j += 1
            if j < n and src[j] == "]":
                j += 1
            while j < n and src[j] != "]":
                j += 2 if src[j] == "\\" else 1
            if capt_depth == 0 and look_depth == 0:
                atoms.append(src[i : j + 1])
            i = j + 1
            continue
        if c == "(":
            if src.startswith("(?<=", i) or src.startswith("(?<!", i):
                frames.append("look")
                look_depth += 1
                i += 4
            elif src.startswith("(?=", i) or src.startswith("(?!", i):
                frames.append("look")
                look_depth += 1
                i += 3
            elif src.startswith("(?:", i):
                frames.append("noncap")
                i += 3
            elif src.startswith("(?<", i):
                frames.append("group")
                capt_depth += 1
                capture += 1
                i += 3
            else:
                frames.append("group")
                capt_depth += 1
                capture += 1
                i += 1
            continue
        if c == ")":
            if frames:
                kind = frames.pop()
                if kind == "group":
                    capt_depth -= 1
                elif kind == "look":
                    look_depth -= 1
            i += 1
            continue
        if c == "{":  # {2} / {1,3} 量词：数字不能算成字面量
            j = src.find("}", i)
            i = n if j < 0 else j + 1
            continue
        if capt_depth == 0 and look_depth == 0 and c not in "^$*+?|":
            atoms.append(c)
        i += 1
    return capture, atoms


def lua_monarch_group_rules(source: str) -> list[tuple[int, str, list[str]]]:
    """抽出 luaLanguage.js 里所有分组动作规则：(行号, 正则源码, 动作列表)。"""
    import re

    start = source.find("tokenizer: {")
    end = source.find("// 语言配置")
    if start < 0 or end < start:
        return []
    region = source[start:end]
    base_line = source[:start].count("\n") + 1
    rules: list[tuple[int, str, list[str]]] = []
    # 形如 [/re/, ['token', ...]]：只有动作是数组的才是分组动作
    pattern = re.compile(r"/((?:[^/\\\n\[]|\[[^\]]*\]|\\.)+)/\s*,\s*\[([^\]]*)\]")
    for m in pattern.finditer(region):
        names = re.findall(r"'([^']*)'", m.group(2))
        if not names:
            continue
        line = base_line + region[: m.start()].count("\n")
        rules.append((line, m.group(1), names))
    return rules


def lua_monarch_group_problems(source: str) -> list[str]:
    """分组动作规则是否满足 monarch 的捕获组约束。"""
    problems: list[str] = []
    rules = lua_monarch_group_rules(source)
    if not rules:
        problems.append(
            "没扫到任何分组动作规则（如果确实不再使用 [/re/, ['a','b']] 这种写法，"
            "请同步改掉这个检查）"
        )
        return problems
    for line, regex_src, names in rules:
        groups, atoms = regex_group_layout(regex_src)
        if groups != len(names):
            problems.append(
                f"第 {line} 行 /{regex_src}/：捕获组 {groups} 个、动作 {len(names)} 个，"
                "monarch 会报 matched number of groups does not match the number of actions"
            )
        if atoms:
            joined = "、".join(atoms)
            problems.append(
                f"第 {line} 行 /{regex_src}/：{joined} 落在所有捕获组之外，"
                "分组动作要求捕获组连续铺满整段匹配，一旦匹配上就会报 "
                "with groups, all characters should be matched in consecutive groups"
            )
    return problems


# 用 node 跑一遍真的 monarch 词法器（monaco 的 ESM 子路径是纯 JS，不需要 DOM）。
# 静态检查是启发式的，这条才是"真机会不会崩"的证据。
NODE_MONARCH_PROBE = r"""
import { compile } from './web/node_modules/monaco-editor/esm/vs/editor/standalone/common/monarch/monarchCompile.js'
import { MonarchTokenizer } from './web/node_modules/monaco-editor/esm/vs/editor/standalone/common/monarch/monarchLexer.js'
import { LUA_MONARCH } from './web/src/composables/luaLanguage.js'
import { EXAMPLES } from './web/src/composables/luaExamples.js'

const languageService = {
  getLanguageIdByLanguageName: () => null,
  getLanguageIdByMimeType: () => null,
  languageIdCodec: { encodeLanguageId: () => 1 },
}
const tokenizer = new MonarchTokenizer(
  languageService,
  { getColorTheme: () => ({ tokenTheme: null }) },
  'lua',
  compile('lua', LUA_MONARCH),
  { getValue: () => 1000000, onDidChangeConfiguration: () => ({ dispose() {} }) },
)

const samples = [
  ...EXAMPLES.map((e) => e.code),
  'local s = json.encode({ a = 1 })',
  'local car = ctx.input.car',
  'local r = http.post("https://x/y", { a = 1 })',
  'local long = [[ a.b ]] -- 注释里的 json.encode(',
  'local t = { a = 1 } --[[ 块注释 ]] if t.a then print(t.a) end',
]

let lines = 0
for (const code of samples) {
  let state = tokenizer.getInitialState()
  for (const line of code.split('\n')) {
    state = tokenizer.tokenize(line, false, state).endState
    lines++
  }
}

let state = tokenizer.getInitialState()
const probe = 'local x = json.encode(ctx.input.car)'
const tokens = tokenizer.tokenize(probe, false, state).tokens
const types = tokens.map((t) => t.type.replace(/\.lua$/, ''))
console.log('MONARCH_OK ' + lines)
console.log('PROBE ' + JSON.stringify(types))
"""


def lua_monarch_runtime_problems() -> tuple[bool, list[str], str]:
    """用真的 monaco monarch 词法器跑一遍示例，返回 (是否跑过, 问题, 说明)。

    node 不在、或 monaco 的 ESM 子路径取不到（换了打包方式）时返回"没跑过"，
    由调用方打印 [SKIP]，不影响整体结果。
    """
    import subprocess

    if shutil.which("node") is None:
        return False, [], "本机没有 node，装一个才能跑真词法器（静态检查已经覆盖了同样的约束）"

    probe = ROOT / ".tmp_monarch_probe.mjs"
    probe.write_text(NODE_MONARCH_PROBE, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["node", str(probe)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return True, ["monarch 探测脚本 180s 没跑完"], ""
    finally:
        probe.unlink(missing_ok=True)

    out = proc.stdout or ""
    err = proc.stderr or ""
    if "ERR_MODULE_NOT_FOUND" in err or "Cannot find module" in err:
        return False, [], f"node 取不到 monaco 的 ESM 子路径，跳过：{err.strip().splitlines()[0][:140]}"

    problems: list[str] = []
    if proc.returncode != 0 or "MONARCH_OK" not in out:
        tail = (err or out).strip().splitlines()
        problems.append(f"真 monarch 词法器抛错：{tail[-1][:220] if tail else '无输出'}")
        return True, problems, ""

    want = ["variable.predefined", "delimiter", "type.identifier"]  # json . encode
    types = json.loads(out.split("PROBE ", 1)[1].strip()) if "PROBE " in out else []
    if not any(types[i : i + 3] == want for i in range(max(0, len(types) - 2))):
        problems.append(f"json.encode 的着色不是 {want}，实际 {types}")
    return True, problems, ""


def lua_worker_csp_problems() -> list[str]:
    """monaco 的 worker 产物必须满足后端 CSP 的 worker-src。

    这是踩过的坑：后端 CSP 是 `worker-src blob:`（backend/app.py），而 vite 默认的
    `?worker` 会产出 assets/editor.worker-*.js 这种**同源文件 URL**，浏览器直接以
    "Creating a worker from 'http://…/assets/editor.worker-*.js' violates … worker-src blob:"
    拦掉，monaco 便退回主线程（控制台再跟一条 uncaught Event，编辑器看着像能用但会卡）。
    修法是 `?worker&inline`：vite 把 worker 打成 base64，运行时 createObjectURL 出 blob:。
    """
    import re

    problems: list[str] = []

    app = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    block = re.search(r'Content-Security-Policy"\]\s*=\s*\(([^)]*)\)', app, re.S)
    csp = " ".join(re.findall(r'"([^"]*)"', block.group(1))) if block else ""
    worker_src: list[str] = []
    for directive in csp.split(";"):
        parts = directive.split()
        if parts and parts[0] == "worker-src":
            worker_src = parts[1:]
    if not csp:
        problems.append("没能从 backend/app.py 里解析出 Content-Security-Policy")
    elif not worker_src:
        problems.append("CSP 里没有 worker-src（会回落到 child-src/default-src，这里都没配 = 不限制）")

    monaco = (ROOT / "web" / "src" / "composables" / "luaMonaco.js").read_text(encoding="utf-8")
    specs = re.findall(r"from\s+'(monaco-editor/[^']*\?worker[^']*)'", monaco)
    if not specs:
        problems.append("luaMonaco.js 里没有 ?worker 导入：monaco 的 worker 没接线")
        return problems

    inline = [s for s in specs if "&inline" in s]
    if worker_src and "'self'" not in worker_src:
        # CSP 只允许 blob: → 必须用内联 worker（blob:），文件 worker 一定被拦
        for spec in specs:
            if "&inline" not in spec:
                problems.append(
                    f"CSP 的 worker-src 是 {' '.join(worker_src)}（不含 'self'），但 `{spec}` "
                    "会产出同源文件 worker，浏览器会拦掉它；应写成 ?worker&inline（blob:）"
                )
    if worker_src and "blob:" not in worker_src:
        for spec in inline:
            problems.append(f"`{spec}` 产出 blob: worker，但 CSP worker-src 不允许 blob:（{' '.join(worker_src)}）")

    # 有 dist 就顺手验一遍产物（没构建过就跳过，不算失败）
    assets = ROOT / "web" / "dist" / "assets"
    if assets.is_dir():
        stale = sorted(p.name for p in assets.glob("editor.worker-*.js"))
        if stale and inline:
            problems.append(f"dist 里还有独立的 {stale[0]}：构建产物是旧的，请重新 npm run build")
        chunks = sorted(assets.glob("luaMonaco-*.js"))
        if chunks:
            text = chunks[-1].read_text(encoding="utf-8", errors="replace")
            if inline and "editor.worker" in text:
                problems.append(f"{chunks[-1].name} 仍引用 editor.worker 文件，内联 worker 没生效")
            if inline and "createObjectURL" not in text:
                problems.append(f"{chunks[-1].name} 里没有 createObjectURL，内联 worker 没生效")
    return problems


def main() -> int:
    from util import lua_runtime

    # ------------------------------------------------------------------
    section("1. worker 链路与运行时")
    # ------------------------------------------------------------------
    config = lua_runtime.script_config()
    print(f"  worker 命令: {' '.join(lua_runtime.worker_command())}")
    print(f"  配置: {json.dumps({k: config[k] for k in ('enabled', 'allow_remote', 'timeout_ms', 'max_memory_mb')}, ensure_ascii=False)}")

    health = lua_runtime.runtime_healthcheck()
    check("端到端自检通过", health.ok, health.error[:200] if not health.ok else "")
    if health.ok:
        print(f"    运行时: {health.result}")
        print(f"    冷启动+执行耗时: {health.duration_ms}ms（worker 内 {health.worker_ms}ms）")
        check("自检里 http 模块可用", health.result.get("http") == "table", str(health.result.get("http")))
    else:
        print(f"    healthcheck 失败: {health.error}\n{health.traceback[:800]}")
        return 1

    def run(code, payload=None, **kw):
        kw.setdefault("config", config)
        return lua_runtime.execute_script(
            code, payload, script_id=kw.pop("script_id", "test"), **kw
        )

    # ------------------------------------------------------------------
    section("2. 沙箱逃逸回归（必须全部为 nil）")
    # ------------------------------------------------------------------
    escapes = {
        "os.execute": "type(os.execute)",
        "os.getenv": "type(os.getenv)",
        "os.remove": "type(os.remove)",
        "os.exit": "type(os.exit)",
        "io": "type(io)",
        "io.open": "type(io and io.open)",
        "package": "type(package)",
        "require": "type(require)",
        "load": "type(load)",
        "loadstring": "type(loadstring)",
        "loadfile": "type(loadfile)",
        "dofile": "type(dofile)",
        "debug": "type(debug)",
        "collectgarbage": "type(collectgarbage)",
        "python(宿主注入)": "type(python)",
        "jit": "type(jit)",
        "ffi": "type(ffi)",
        "newproxy": "type(newproxy)",
        "string.dump": "type(string.dump)",
    }
    for label, expr in escapes.items():
        r = run(f"return {expr}")
        check(f"{label} 不可用", r.ok and r.result == "nil", f"got {r.result!r}")

    # 关键：Lua 侧拿不到任何 Python 对象（否则 f.__globals__ 可以摸到 __builtins__）
    for label, expr, want in [
        ("input 不是 Python 对象", "type(input.__class__)", "nil"),
        ("json 不是 Python 模块", "type(json.__class__)", "nil"),
        ("_G 无 Python 属性链", "type(_G.__class__)", "nil"),
        ("字符串元表无 dump", "type(getmetatable('').__index.dump)", "nil"),
        # os/string 等表不带元表，就没有 __index 之类的后门
        ("os 表无元表后门", "tostring(getmetatable(os) == nil)", "true"),
        ("string 表无元表后门", "tostring(getmetatable(string) == nil)", "true"),
    ]:
        r = run(f"return {expr}", {"a": 1})
        check(label, r.ok and r.result == want, f"got {r.result!r} {r.error[:60]}")

    # 常用能力仍在
    r = run("return {f = type(string.format) .. type(table.insert) .. type(math.floor), "
            "d = type(os.date), u = type(utf8.char), c = type(coroutine.create)}")
    check(
        "安全子集可用(string/table/math/os.date/utf8/coroutine)",
        r.ok and r.result == {"f": "functionfunctionfunction", "d": "function",
                              "u": "function", "c": "function"},
        str(r.result),
    )

    # ------------------------------------------------------------------
    section("3. JSON 语义")
    # ------------------------------------------------------------------
    r = run("return {n = json.null, b = json.decode('[[1,null,3]]')[1]}")
    check("null 哨兵映射为 JSON null", r.ok and r.result == {"n": None, "b": [1, None, 3]}, str(r.result))

    r = run("local t = json.decode('[[1,null,3]]')[1] return {len = #t, second_is_null = (t[2] == json.null)}")
    check("数组中的 null 不丢位置", r.ok and r.result == {"len": 3, "second_is_null": True}, str(r.result))

    r = run("local t = json.decode('{}') return {missing_is_nil = (t.x == nil)}")
    check("缺失字段是 nil（与 null 区分）", r.ok and r.result == {"missing_is_nil": True}, str(r.result))

    r = run("return '中文😀\\u{4e2d}'")
    check("UTF-8 往返", r.ok and r.result == "中文😀中", repr(r.result))

    r = run('return json.decode([[{"s":"a\\nb\\u4e2d\\t\\ud83d\\ude00"}]])')
    check("转义与代理对解码", r.ok and r.result == {"s": "a\nb中\t😀"}, repr(r.result))

    # 注意用 [==[ ]==] 而不是 [[ ]]：JSON 里本身可能出现 ]]
    r = run('local t = json.decode([==[{"a":[1,[2,{"b":null}]]}]==]) return json.encode(t)')
    # 脚本显式返回字符串时结果就是字符串（不会二次解析）
    check("嵌套结构编解码往返", r.ok and r.result == '{"a":[1,[2,{"b":null}]]}', repr(r.result))

    r = run('return json.decode([==[{"a":[1,[2,{"b":null}]]}]==])')
    check("嵌套结构直接返回表", r.ok and r.result == {"a": [1, [2, {"b": None}]]}, str(r.result))

    r = run("return json.decode('[1,]')")
    check("非法 JSON 报错清晰", (not r.ok) and r.error_type == "lua" and "位置" in r.error,
          f"{r.error_type}: {r.error[:80]}")

    r = run("local t = {} t.self = t return t")
    check("循环引用被拦下", (not r.ok) and "循环引用" in r.error, r.error[:80])

    r = run("return {f = function() end}")
    check("返回值含函数被拦下", (not r.ok) and "不支持的类型" in r.error, r.error[:80])

    # ------------------------------------------------------------------
    section("4. 脚本契约（handle / output / 日志）")
    # ------------------------------------------------------------------
    r = run("function handle(ctx) return {name = ctx.input.name, sid = ctx.script_id} end",
            {"name": "AGV-01"}, script_id="demo")
    check("handle(ctx) 风格", r.ok and r.result == {"name": "AGV-01", "sid": "demo"}, str(r.result))

    r = run("output.msg = 'hi' output.n = 2")
    check("全局 output 作为结果", r.ok and r.result == {"msg": "hi", "n": 2}, str(r.result))

    r = run("print('a', 1) console.error('b') ctx_log = nil return 1")
    r2 = run("print('x') return 1")
    check("print/console 日志被收集", r2.ok and r2.logs == ["x"], str(r2.logs))

    r = run("error('手动报错')")
    check("Lua error 映射为 lua 类型", (not r.ok) and r.error_type == "lua" and "手动报错" in r.error, r.error[:80])

    r = run("return 1 +")
    check("语法错误映射为 syntax 类型", (not r.ok) and r.error_type == "syntax", r.error[:80])

    r = run("error('x')", script_id="named_err")
    check("报错信息带脚本名", (not r.ok) and "named_err" in r.error, r.error[:80])

    # ------------------------------------------------------------------
    section("5. 资源限制")
    # ------------------------------------------------------------------
    # 用一份显式的短超时配置：机器上的 config.toml 可能把 timeout_ms 设得很大，
    # 那会让这个用例白等（连外部接口的脚本确实需要大超时，但不该拖慢测试）
    kill_cfg = {**config, "timeout_ms": 800}
    t0 = time.perf_counter()
    r = run("while true do end", config=kill_cfg)
    dt = (time.perf_counter() - t0) * 1000
    check("死循环被强杀（timeout）", (not r.ok) and r.error_type == "timeout", f"{r.error_type} {dt:.0f}ms")
    check("超时耗时接近配置值", 0.8 <= dt / kill_cfg["timeout_ms"] <= 3.0,
          f"{dt:.0f}ms vs {kill_cfg['timeout_ms']}ms")

    r = run("local t = {} local i = 1 while true do t[i] = string.rep('x', 2000) i = i + 1 end")
    check("Lua 内存超限被强制（memory）", (not r.ok) and r.error_type == "memory", f"{r.error_type}: {r.error[:60]}")

    r = run("local t = {} for i = 1, 40000 do t[i] = 'x' .. i end return t")
    check("结果超限被拦下（result）", (not r.ok) and r.error_type == "result", f"{r.error_type}: {r.error[:80]}")

    r = run("return 1", {"blob": "x" * (config["max_payload_kb"] * 1024 + 100)})
    check("请求体超限被拦下（payload）", (not r.ok) and r.error_type == "payload", f"{r.error_type}: {r.error[:80]}")

    r = run("-- " + "x" * (config["max_script_kb"] * 1024 + 100))
    check("脚本超限被拦下（script）", (not r.ok) and r.error_type == "script", f"{r.error_type}: {r.error[:80]}")

    r = run("print(string.rep('y', 5000)) return 1")
    check("单行日志被截断", r.ok and r.logs and len(r.logs[0]) <= 2000, f"len={len(r.logs[0]) if r.logs else 0}")

    r = run("local t = {} print('before error') error('mid')")
    check("报错时仍返回已产生的日志", (not r.ok) and r.logs == ["before error"], str(r.logs))

    # 无限递归最坏情况会在 C 层爆栈：这里验证"要么干净报错、要么 worker 崩溃被宿主
    # 捕获"，两种结果都证明隔离生效（宿主进程不会跟着挂）。
    # 实测 Lua 5.5 下递归会先撞上内存上限（每层都占栈帧），因此允许 memory。
    t0 = time.perf_counter()
    r = run("local function f() return 1 + f() end return f()")
    check("无限递归被隔离（不拖垮宿主）",
          (not r.ok) and r.error_type in ("lua", "crash", "internal", "memory"),
          f"{r.error_type}: {r.error[:90]}  {(time.perf_counter() - t0) * 1000:.0f}ms")
    check("宿主进程存活", lua_runtime.runtime_healthcheck().ok)

    # ------------------------------------------------------------------
    section("6. 访问闸门（纯函数）")
    # ------------------------------------------------------------------
    from backend.api.user_script import evaluate_access

    base = {"enabled": True, "allow_remote": False, "api_key": ""}
    cases = [
        ("本机放行", "127.0.0.1", {}, base, True, 200),
        ("本机 IPv6 放行", "::1", {}, base, True, 200),
        ("localhost 放行", "localhost", {}, base, True, 200),
        ("远程默认拒绝", "192.168.1.50", {}, base, False, 403),
        ("禁用后本机也拒绝", "127.0.0.1", {}, {**base, "enabled": False}, False, 403),
        ("反代头按远程处理", "127.0.0.1", {"x-forwarded-for": "8.8.8.8"}, base, False, 403),
        ("allow_remote 但无 key 拒绝",
         "192.168.1.50", {}, {**base, "allow_remote": True}, False, 403),
        ("allow_remote + 正确 key 放行",
         "192.168.1.50", {"x-api-key": "s3cret"}, {**base, "allow_remote": True, "api_key": "s3cret"}, True, 200),
        ("allow_remote + 错误 key 拒绝",
         "192.168.1.50", {"x-api-key": "bad"}, {**base, "allow_remote": True, "api_key": "s3cret"}, False, 401),
        ("allow_remote + 缺 key 拒绝",
         "192.168.1.50", {}, {**base, "allow_remote": True, "api_key": "s3cret"}, False, 401),
    ]
    for label, host, headers, cfg, want_ok, want_status in cases:
        allowed, reason, status = evaluate_access(host, headers, cfg)
        check(f"{label}", (allowed == want_ok and status == want_status), f"{allowed} {status} {reason[:60]}")

    # ------------------------------------------------------------------
    section("7. HTTP 接口（TestClient，用临时库）")
    # ------------------------------------------------------------------
    # 临时库放在工作区内的 lua_script/ 下（已被 .gitignore 忽略），用完删除
    tmp_dir = ROOT / "lua_script" / f"_test_scripts_{os.getpid()}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        from fastapi.testclient import TestClient

        from util import user_script_store
        from util.user_script_store import UserScriptStore, default_script_dir

        check("默认脚本目录 = <根>/lua_script", default_script_dir() == ROOT / "lua_script",
              str(default_script_dir()))
        user_script_store._store = UserScriptStore(tmp_dir)

        from backend.app import app
        from backend.api.user_script import require_access

        # 闸门已单独验证过，这里覆盖掉它专测接口
        app.dependency_overrides[require_access] = lambda: lua_runtime.script_config()
        client = TestClient(app)

        r = client.get("/api/user-script/runtime")
        body = r.json()
        check("GET /runtime 200", r.status_code == 200 and body.get("success") is True,
              f"{r.status_code} {str(body)[:120]}")

        r = client.get("/api/user-script")
        check("GET 列表（空）", r.status_code == 200 and r.json()["count"] == 0, str(r.json())[:120])

        code_ok = "function handle(ctx)\n  return {echo = ctx.input, n = 1}\nend\n"
        r = client.post("/api/user-script", json={"script_id": "demo.echo", "code": code_ok, "name": "回显"})
        check("POST 新建脚本", r.status_code == 200 and r.json()["script"]["version"] == 1,
              f"{r.status_code} {str(r.json())[:160]}")

        r = client.post("/api/user-script", json={"script_id": "demo.echo", "code": code_ok})
        check("重复 ID 返回 400", r.status_code == 400, str(r.status_code))

        r = client.post("/api/user-script", json={"script_id": "bad id!", "code": code_ok})
        check("非法 ID 返回 400", r.status_code == 400, str(r.status_code))

        r = client.post("/api/user-script", json={"script_id": "broken", "code": "return 1 +"})
        check("新建时语法检查拦截 400", r.status_code == 400 and "语法" in r.text, r.text[:120])

        r = client.post("/api/user-script", json={"script_id": "broken", "code": "return 1 +", "validate_code": False})
        check("validate_code=false 可跳过语法检查", r.status_code == 200, str(r.status_code))

        r = client.get("/api/user-script/demo.echo")
        check("GET 单个（含正文）", r.status_code == 200 and "handle" in r.json()["script"]["code"], str(r.status_code))

        r = client.get("/api/user-script/nope")
        check("GET 不存在的脚本 404", r.status_code == 404, str(r.status_code))

        r = client.put("/api/user-script/demo.echo", json={"code": code_ok + "-- v2\n"})
        check("PUT 更新并递增版本", r.status_code == 200 and r.json()["script"]["version"] == 2,
              str(r.json()["script"]["version"]))

        r = client.put("/api/user-script/demo.echo", json={"code": "local x ="})
        check("更新时语法检查拦截 400", r.status_code == 400, str(r.status_code))

        r = client.post("/api/user-script/demo.echo/check")
        check("POST /check 通过", r.status_code == 200 and r.json()["success"] is True, str(r.json())[:120])

        r = client.post("/api/user-script/broken/check")
        check("POST /check 报语法错", r.json()["success"] is False and r.json()["error_type"] == "syntax",
              str(r.json())[:140])

        r = client.post("/api/user-script/demo.echo/run", json={"payload": {"car": "AGV-07"}})
        body = r.json()
        check("POST /{id}/run 执行成功",
              r.status_code == 200 and body["ok"] is True and body["result"]["echo"] == {"car": "AGV-07"},
              str(body)[:160])

        r = client.post("/api/user-script/demo.echo", json={"payload": {"car": "AGV-08"}})
        check("POST /{id} 别名等价",
              r.status_code == 200 and r.json()["result"]["echo"] == {"car": "AGV-08"}, str(r.json())[:160])

        r = client.post("/api/user-script/run", json={"code": "return {sum = 1 + 1}", "payload": {}})
        check("POST /run 临时执行", r.status_code == 200 and r.json()["result"]["sum"] == 2, str(r.json())[:160])

        # ── 脚本即 API 端点：请求直通 + __status/__headers ─────────────
        probe = (
            "function handle(ctx)\n"
            "  return { input = ctx.input, query = ctx.query, body = ctx.body,\n"
            "           method = ctx.request.method, path = ctx.request.path,\n"
            "           ip = ctx.request.ip, headers = ctx.request.headers }\n"
            "end\n"
        )
        client.post("/api/user-script", json={"script_id": "api.probe", "code": probe})

        r = client.post("/api/user-script/api.probe/run", json={"car": "AGV-07", "step": 3})
        got = r.json().get("result") or {}
        check("直接 POST 业务 JSON：入参就是 body", got.get("input") == {"car": "AGV-07", "step": 3},
              json.dumps(got, ensure_ascii=False)[:200])

        r = client.get("/api/user-script/api.probe/run?car=AGV-07&step=3")
        got = r.json().get("result") or {}
        check("GET + query 调用脚本（值都是字符串）",
              got.get("input") == {"car": "AGV-07", "step": "3"} and got.get("query", {}).get("step") == "3",
              json.dumps(got.get("input"), ensure_ascii=False))
        check("ctx.request 带 method/path/ip",
              got.get("method") == "GET" and str(got.get("path", "")).endswith("/api.probe/run") and bool(got.get("ip")),
              json.dumps({k: got.get(k) for k in ("method", "path", "ip")}, ensure_ascii=False))
        check("脚本看不到 X-API-Key 等凭据",
              "s3cret" not in client.post("/api/user-script/api.probe/run", json={"a": 1},
                                          headers={"X-Api-Key": "s3cret"}).text)

        r = client.post("/api/user-script/api.probe/run?x=1", json={"car": "AGV-08"})
        check("query 与 body 合并、body 优先",
              (r.json().get("result") or {}).get("input") == {"x": "1", "car": "AGV-08"},
              json.dumps((r.json().get("result") or {}).get("input"), ensure_ascii=False))

        r = client.post("/api/user-script/api.probe", json={"car": "AGV-09"})
        check("POST /{id} 别名同样直通 body",
              (r.json().get("result") or {}).get("input") == {"car": "AGV-09"},
              json.dumps((r.json().get("result") or {}).get("input"), ensure_ascii=False))

        r = client.post("/api/user-script/api.probe/run", json=[1, 2, 3])
        got = r.json().get("result") or {}
        check("数组 body 通过 ctx.body 给脚本", got.get("body") == [1, 2, 3] and got.get("input") == {},
              json.dumps(got, ensure_ascii=False)[:160])

        r = client.post("/api/user-script/api.probe/run", json={"payload": {"car": "W"}})
        check("老式 payload 包装体仍然兼容",
              (r.json().get("result") or {}).get("input") == {"car": "W"},
              json.dumps((r.json().get("result") or {}).get("input"), ensure_ascii=False))

        status_code = (
            'return { ok = false, error = "car 不存在", __status = 404,\n'
            '         __headers = { ["X-Svc"] = "agv-api", ["Content-Length"] = "999" } }\n'
        )
        client.post("/api/user-script", json={"script_id": "api.status", "code": status_code})
        r = client.post("/api/user-script/api.status/run", json={})
        check("__status 决定 HTTP 状态码", r.status_code == 404, str(r.status_code))
        check("__headers 追加响应头", r.headers.get("x-svc") == "agv-api", str(dict(r.headers))[:160])
        check("__status / __headers 不出现在响应体", "__status" not in r.text and "__headers" not in r.text,
              r.text[:200])
        check("响应体里带 http_status 便于排查", r.json().get("http_status") == 404, r.text[:160])
        check("Content-Length 这类头不让脚本覆盖", r.headers.get("content-length") != "999",
              str(r.headers.get("content-length")))

        bad_status = (
            'return { ok = true, __status = 999,\n'
            '         __headers = { ["X-Evil"] = "a\\r\\nX-Injected: 1", ["X-Ok"] = "fine" } }\n'
        )
        client.post("/api/user-script", json={"script_id": "api.badstatus", "code": bad_status})
        r = client.post("/api/user-script/api.badstatus/run", json={})
        check("非法状态码被忽略（回到 200）", r.status_code == 200, str(r.status_code))
        check("响应头注入被拦下", r.headers.get("x-injected") is None, str(dict(r.headers))[:160])
        check("合法响应头照常生效", r.headers.get("x-ok") == "fine")

        r = client.put("/api/user-script/demo.echo", json={"enabled": False})
        r2 = client.post("/api/user-script/demo.echo/run", json={"payload": {}})
        check("禁用脚本执行返回 403", r2.status_code == 403, str(r2.status_code))

        r3 = client.post("/api/user-script/demo.echo/run", json={"payload": {}, "code": "return 'override'"})
        check("禁用脚本仍可用 code 覆盖调试",
              r3.status_code == 200 and r3.json()["result"] == "override", str(r3.json())[:120])
        client.put("/api/user-script/demo.echo", json={"enabled": True})

        r = client.get("/api/user-script/demo.echo/runs")
        runs = r.json()["runs"]
        # 3 次真实执行：/{id}/run、/{id} 别名、code 覆盖；
        # 被 403 拦下的那次不算执行，不记流水
        check("执行流水已记录", r.status_code == 200 and len(runs) == 3, f"{len(runs)} 条")
        check("流水含来源与耗时", bool(runs) and "source" in runs[0] and runs[0]["duration_ms"] > 0,
              json.dumps(runs[0], ensure_ascii=False) if runs else "")

        r = client.get("/api/user-script/demo.echo")
        check("脚本统计已更新", r.json()["script"]["run_count"] == 3 and r.json()["script"]["last_status"] == "ok",
              str(r.json()["script"]["run_count"]))

        r = client.delete("/api/user-script/demo.echo")
        r2 = client.get("/api/user-script/demo.echo")
        check("DELETE 后 404", r.status_code == 200 and r2.status_code == 404, f"{r.status_code}/{r2.status_code}")

        r = client.delete("/api/user-script/demo.echo")
        check("重复 DELETE 404", r.status_code == 404, str(r.status_code))

        # ------------------------------------------------------------------
        section("8. lua_script/ 目录：文件为准、外部编辑热生效、删除留档")
        # ------------------------------------------------------------------
        store = user_script_store.get_store()
        info = store.storage_info()
        check("storage 信息指向脚本目录", info["dir"] == str(tmp_dir), info["dir"])

        code_a = "function handle(ctx)\n  return {v = 'A'}\nend\n"
        r = client.post("/api/user-script", json={"script_id": "disk.hot", "code": code_a})
        script_file = tmp_dir / "disk.hot.lua"
        check("脚本正文落到 .lua 文件",
              r.status_code == 200 and script_file.exists() and "A" in script_file.read_text(encoding="utf-8"),
              str(script_file))

        # 直接用外部编辑器改文件（模拟用户手工编辑 / git 拉取）
        script_file.write_text("function handle(ctx)\n  return {v = 'B'}\nend\n", encoding="utf-8")
        r = client.get("/api/user-script/disk.hot")
        body = r.json()["script"]
        check("外部改文件后 API 读到新正文", "'B'" in body["code"], body["code"].replace("\n", "\\n")[:60])
        check("外部改动递增版本", body["version"] == 2, str(body["version"]))
        r = client.post("/api/user-script/disk.hot/run", json={"payload": {}})
        check("执行用的是文件里的新正文", r.json().get("result") == {"v": "B"}, str(r.json())[:120])

        # 文件被误删 -> 用库里副本自愈
        script_file.unlink()
        r = client.get("/api/user-script/disk.hot")
        check("文件被删后自愈重建", script_file.exists() and "B" in r.json()["script"]["code"],
              str(script_file.exists()))

        client.put("/api/user-script/disk.hot", json={"code": "return 'C'\n"})
        backups = store.list_backups("disk.hot")
        check("覆盖前留历史正文", len(backups) == 1 and backups[0]["version"] == 2,
              json.dumps(backups, ensure_ascii=False))

        r = client.delete("/api/user-script/disk.hot")
        check("删除后 .lua 文件移除", r.status_code == 200 and not script_file.exists())
        backups = store.list_backups("disk.hot")
        check("删除前留历史正文", len(backups) == 2, json.dumps(backups, ensure_ascii=False))

    finally:
        # 单例置空后再删目录：Windows 上残留的 SQLite 句柄会让 rmtree 静默失败
        user_script_store._store = None
        for _ in range(3):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            if not tmp_dir.exists():
                break
            time.sleep(0.2)

    # ------------------------------------------------------------------
    section("9. 外部 HTTP：脚本「调外部 API + 中转」的底座")
    # ------------------------------------------------------------------
    from util import lua_http

    server, port, received = make_mock_server()
    base_url = f"http://127.0.0.1:{port}"

    def http_config(**overrides):
        """可以联网的配置：允许内网（测试服务器就在 127.0.0.1）。"""
        cfg = lua_runtime.script_config()
        cfg["timeout_ms"] = 6000
        cfg["http"] = {
            **cfg["http"],
            "allow_private_hosts": True,
            "max_requests_per_run": 8,
            **overrides,
        }
        return cfg

    try:
        # ── 策略（纯函数，不发请求）────────────────────────────────
        policy = lua_http.HttpPolicy.from_config(
            {"allowed_hosts": "api.example.com", "timeout_ms": 99, "max_requests_per_run": 999}
        )
        check("策略：字符串白名单会转成列表", policy.allowed_hosts == ["api.example.com"],
              str(policy.allowed_hosts))
        check("策略：超时被夹到下限", policy.timeout_ms == 100, str(policy.timeout_ms))
        check("策略：次数被夹到上限", policy.max_requests_per_run == 64, str(policy.max_requests_per_run))
        check("策略：默认禁止内网", lua_http.HttpPolicy.from_config(None).allow_private_hosts is False)

        check("主机匹配：精确", policy.match_host("api.example.com"))
        check("主机匹配：不在名单里拒绝", not policy.match_host("evil.com"))
        wildcard = lua_http.HttpPolicy.from_config({"allowed_hosts": ["*.example.com"]})
        check("主机匹配：通配子域", wildcard.match_host("a.example.com"))
        check("主机匹配：通配不覆盖裸域", not wildcard.match_host("example.com"))
        blocked = lua_http.HttpPolicy.from_config(
            {"allowed_hosts": ["*.example.com"], "blocked_hosts": ["bad.example.com"]}
        )
        check("主机匹配：黑名单优先", not blocked.match_host("bad.example.com"))

        def url_error(url: str, pol=None) -> str:
            try:
                lua_http.check_url(url, pol or policy)
            except lua_http.HttpPolicyError as exc:
                return exc.error_type
            return ""

        check("URL：拒绝 file://", url_error("file:///c:/windows/win.ini") == "http_scheme")
        check("URL：拒绝空主机", url_error("http:///nohost") == "http_url")
        check("URL：拒绝带用户名密码", url_error("http://a:b@api.example.com/") == "http_url")
        check("URL：非白名单主机被拦", url_error("http://evil.com/") == "http_blocked")
        check(
            "URL：默认拦内网",
            url_error("http://127.0.0.1:1/", lua_http.HttpPolicy.from_config(None)) == "http_blocked",
        )
        check("URL：放行时允许内网", url_error(f"{base_url}/api/json", http_config() and lua_http.HttpPolicy.from_config(http_config()["http"])) == "")

        header_error = ""
        try:
            lua_http._sanitize_headers({"X-Bad": "a\r\nX-Injected: 1"})
        except lua_http.HttpPolicyError as exc:
            header_error = exc.error_type
        check("请求头：拒绝 CRLF 注入", header_error == "http_badarg")
        sanitized = lua_http._sanitize_headers({"Host": "evil", "X-Trace": "abc"})
        check("请求头：Host 被丢弃", "Host" not in sanitized and sanitized.get("X-Trace") == "abc")

        bridge = lua_http.make_bridge({"enabled": False})
        disabled = json.loads(bridge("{\"url\": \"http://example.com\"}"))
        check("策略：关掉后返回 http_disabled", disabled["error_type"] == "http_disabled",
              json.dumps(disabled, ensure_ascii=False)[:120])

        bridge = lua_http.make_bridge({"allow_private_hosts": True})
        bad_method = json.loads(bridge(json.dumps({"url": base_url, "method": "TRACE"})))
        check("策略：拒绝 TRACE", bad_method["error_type"] == "http_method")
        check(
            "桥：异常不会冒泡（非法 JSON 输入）",
            json.loads(bridge("not json"))["ok"] is False,
        )

        budget = lua_http.HttpBridge(lua_http.HttpPolicy.from_config({"allow_private_hosts": True}), budget_ms=50)
        exhausted = json.loads(budget(json.dumps({"url": base_url})))
        check("策略：脚本没有剩余时间时不发请求", exhausted["error_type"] == "http_timeout",
              json.dumps(exhausted, ensure_ascii=False)[:140])

        # ── 真正跑脚本 ────────────────────────────────────────────
        demo = """
local up = http.get(URL .. "/api/json", { params = { q = "中文", n = 2 }, headers = { ["X-Trace"] = "t1" } })
log("upstream", up.ok, up.status, up.content_type)
local sent = http.post(URL .. "/hook", { title = up.json.slideshow.title, id = 7 })
local text = http.get(URL .. "/api/text")
local err = http.get(URL .. "/api/500")
return {
  up = { ok = up.ok, status = up.status, title = up.json and up.json.slideshow.title,
         bytes = up.bytes, json_auto = up.json ~= nil },
  down = { ok = sent.ok, status = sent.status, json = sent.json },
  text = { status = text.status, body = text.body, json = text.json },
  http500 = { ok = err.ok, status = err.status, json = err.json },
}
""".replace("URL", f'"{base_url}"')
        result = lua_runtime.execute_script(demo, {"car": "AGV-09"}, script_id="test.http", config=http_config())
        check("脚本里 http.get 成功", result.ok and result.result["up"]["ok"] is True,
              json.dumps(result.result, ensure_ascii=False)[:200] if result.ok else result.error)
        if result.ok:
            check("响应 JSON 自动解码", result.result["up"]["json_auto"] is True
                  and result.result["up"]["title"] == "AGV 任务",
                  json.dumps(result.result["up"], ensure_ascii=False))
            check("http.post 送达下游", result.result["down"]["ok"] is True
                  and result.result["down"]["status"] == 200,
                  json.dumps(result.result["down"], ensure_ascii=False))
            check("非 JSON 响应不硬解码（json 字段直接不存在）",
                  "json" not in result.result["text"]
                  and result.result["text"]["body"] == "plain text body",
                  json.dumps(result.result["text"], ensure_ascii=False))
            check("HTTP 500 算 ok=true（传输成功）", result.result["http500"]["ok"] is True
                  and result.result["http500"]["status"] == 500)

        posts = [r for r in received if r["method"] == "POST" and r["path"] == "/hook"]
        check("下游确实收到了中转数据", len(posts) == 1, json.dumps(received, ensure_ascii=False)[:200])
        if posts:
            check("中转数据是自动序列化的 JSON",
                  posts[0]["content_type"] == "application/json" and '"title":"AGV 任务"' in posts[0]["body"],
                  posts[0]["body"][:120])
        gets = [r for r in received if r["path"].startswith("/api/json?")]
        check("params 拼成查询串并做了转义",
              bool(gets) and "q=%E4%B8%AD%E6%96%87" in gets[0]["path"] and "n=2" in gets[0]["path"],
              gets[0]["path"] if gets else "(没有带参数的请求)")
        check("自定义请求头透传", bool(gets) and gets[0]["x_trace"] == "t1",
              str(gets[0]["x_trace"]) if gets else "")

        # 响应体截断
        big = lua_runtime.execute_script(
            f'local r = http.get("{base_url}/api/big")\n'
            "return { ok = r.ok, bytes = r.bytes, truncated = r.truncated, len = #r.body }",
            None, script_id="test.http.big", config=http_config(max_response_kb=64),
        )
        check("响应体超限被截断",
              big.ok and big.result["truncated"] is True and big.result["len"] == 64 * 1024,
              json.dumps(big.result, ensure_ascii=False) if big.ok else big.error)

        # 单次超时
        timed = lua_runtime.execute_script(
            f'local r = http.get("{base_url}/api/slow", {{ timeout_ms = 300 }})\n'
            "return { ok = r.ok, type = r.error_type, err = r.error }",
            None, script_id="test.http.slow",
            config=http_config(timeout_ms=2500, max_requests_per_run=8),
        )
        check("单次请求超时返回 http_timeout",
              timed.ok and timed.result["ok"] is False and timed.result["type"] == "http_timeout",
              json.dumps(timed.result, ensure_ascii=False) if timed.ok else timed.error)

        # 次数上限
        many = lua_runtime.execute_script(
            f'local out = {{}}\nfor i = 1, 3 do\n'
            f'  local r = http.get("{base_url}/api/json")\n'
            "  out[#out + 1] = r.ok and 'ok' or r.error_type\nend\nreturn out",
            None, script_id="test.http.many", config=http_config(max_requests_per_run=2),
        )
        check("超过单轮次数上限返回 http_busy",
              many.ok and many.result[-1] == "http_busy" and many.result[0] == "ok",
              json.dumps(many.result, ensure_ascii=False) if many.ok else many.error)

        # 重定向每一跳都过策略：目标换成不在白名单的 localhost
        redirect = lua_runtime.execute_script(
            f'local r = http.get("{base_url}/api/redirect")\n'
            "return { ok = r.ok, type = r.error_type, err = r.error }",
            None, script_id="test.http.redirect",
            config=http_config(allowed_hosts=["127.0.0.1"]),
        )
        check("重定向目标也要过策略",
              redirect.ok and redirect.result["ok"] is False and redirect.result["type"] == "http_blocked",
              json.dumps(redirect.result, ensure_ascii=False) if redirect.ok else redirect.error)

        # 请求体上限 / GET 带 body
        check(
            "GET 不允许带 body",
            lua_runtime.execute_script(
                f'return http.request{{ url = "{base_url}/api/json", method = "GET", body = "x" }}',
                None, script_id="test.http.getbody", config=http_config(),
            ).result["error_type"] == "http_badarg",
        )
        over = lua_runtime.execute_script(
            f'return http.post("{base_url}/hook", string.rep("x", 5000))',
            None, script_id="test.http.oversize", config=http_config(max_request_kb=1),
        )
        check("请求体超限返回 http_size", over.ok and over.result["error_type"] == "http_size",
              json.dumps(over.result, ensure_ascii=False) if over.ok else over.error)

        check("非法 method 在 Lua 侧就被挡",
              lua_runtime.execute_script(
                  'return http.request{ url = "http://x/", method = "TRACE" }',
                  None, script_id="test.http.trace", config=http_config(),
              ).result["error_type"] == "http_method")

        # 沙箱逃逸：http 是唯一的 Python 桥，必须爬不出去
        escape = r"""
local function raised(fn)
  return pcall(fn) == false
end
return {
  -- 这几条应该是 true：Lua 里函数值不能被索引，属性链根本建不起来
  index_globals_raised = raised(function() return http.request.__globals__ end),
  index_class_raised = raised(function() return http.request.__class__ end),
  index_bracket_raised = raised(function() return http.request["__globals__"] end),
  escape_raised = raised(function()
    local g = http.request.__globals__["__builtins__"]
    return g["__import__"]("os").getcwd()
  end),
  -- 这几条应该是 false：桥本体和安装函数都不在脚本可见范围
  bridge_reachable = getmetatable(http.request) ~= nil,
  http_call_visible = http_call ~= nil,
  install_visible = __install_http ~= nil,
}
"""
        escaped = lua_runtime.execute_script(escape, None, script_id="test.http.escape", config=http_config())
        check("http 桥不能顺着 Python 对象爬出去", escaped.ok and all([
            escaped.result.get("index_globals_raised") is True,
            escaped.result.get("index_class_raised") is True,
            escaped.result.get("index_bracket_raised") is True,
            escaped.result.get("escape_raised") is True,
        ]), json.dumps(escaped.result, ensure_ascii=False) if escaped.ok else escaped.error)
        check("http 桥本体 / 安装函数对脚本不可见", escaped.ok and all([
            escaped.result.get("bridge_reachable") is False,
            escaped.result.get("http_call_visible") is False,
            escaped.result.get("install_visible") is False,
        ]), json.dumps(escaped.result, ensure_ascii=False) if escaped.ok else escaped.error)

    finally:
        server.shutdown()
        server.server_close()

    # ------------------------------------------------------------------
    section("10. 前后端一致性：沙箱全局 / 示例脚本能被真 Lua 编译")
    # ------------------------------------------------------------------
    from util import lua_sandbox

    js_names = frontend_sandbox_names()
    check("前端提示目录里有沙箱全局", len(js_names) > 20, f"{len(js_names)} 个")

    lua = lua_sandbox.build_runtime(32 * 1024 * 1024)
    sandbox, _logs = lua_sandbox.lockdown(
        lua, max_log_lines=50, max_depth=16, max_nodes=5000,
        http_bridge=lambda spec: '{"ok": false, "error": "test"}',
    )
    limits = lua_runtime.worker_limits(lua_runtime.script_config())
    lua_sandbox.execute(lua, sandbox, "return {ok = true}", "{}", "parity", limits)
    real_names = sorted(k for k in lua.globals().keys() if isinstance(k, str))
    check("沙箱真实全局与前端目录一致", real_names == js_names,
          f"仅沙箱有: {sorted(set(real_names) - set(js_names))} / 仅前端有: {sorted(set(js_names) - set(real_names))}")
    check("http 在沙箱里可见", "http" in real_names)
    check("ctx / handle 不是沙箱全局（前者是入参、后者由脚本定义）",
          "ctx" not in real_names and "handle" not in real_names)

    examples = frontend_examples()
    check("抠出 4 个前端示例", len(examples) == 4, f"{len(examples)} 个")
    for name, code in examples:
        res = lua_runtime.execute_script(code, None, script_id=f"example.{name.lower()}", mode="check")
        check(f"示例 {name} 能通过真 Lua 语法检查", res.ok,
              (res.error or "")[:160] if not res.ok else "")

    # 写给 AI 的脚本指南里的每段 Lua 都要真能编译（只编译，不执行）
    guide_blocks = guide_lua_blocks()
    check("抠出 LUA_SCRIPT_GUIDE.md 里的 lua 代码块", len(guide_blocks) >= 10,
          f"{len(guide_blocks)} 个")
    bad_blocks = []
    for line, code in guide_blocks:
        res = lua_runtime.execute_script(code, None, script_id=f"guide:{line}", mode="check")
        if not res.ok:
            bad_blocks.append(f"第 {line} 行: {(res.error or '').splitlines()[0][:120]}")
    check(f"指南里的 {len(guide_blocks)} 段 Lua 都能通过真 Lua 语法检查", not bad_blocks,
          "；".join(bad_blocks[:4]))

    # 示例 2（中转 demo）在真实网络链路里跑一遍：上游换成 mock，走 http.get/http.post 分支
    import re as _re

    relay = dict(examples).get("RELAY", "")
    server2, port2, received2 = make_mock_server()
    try:
        # 只改地址：示例里的取数/处理/中转逻辑一个字都不动
        live = _re.sub(r'local UPSTREAM\s*=\s*"[^"]*"',
                       f'local UPSTREAM = "http://127.0.0.1:{port2}/api/echo"', relay)
        live = _re.sub(r'local DOWNSTREAM\s*=\s*"[^"]*"',
                       f'local DOWNSTREAM = "http://127.0.0.1:{port2}/api/echo-post"', live)
        check("示例脚本被正确改写为指向本地 echo 服务", "127.0.0.1" in live and "/api/echo-post" in live)

        cfg = lua_runtime.script_config()
        cfg["timeout_ms"] = 8000
        cfg["http"] = {**cfg["http"], "allow_private_hosts": True}
        run = lua_runtime.execute_script(
            live, {"car": "AGV-09", "task_id": "T-1001", "step": 12}, script_id="demo.relay", config=cfg
        )
        check("中转 demo 端到端执行成功", run.ok and run.result.get("ok") is True,
              (run.error or json.dumps(run.result, ensure_ascii=False))[:220])
        if run.ok:
            data = run.result.get("data") or {}
            up = run.result.get("upstream") or {}
            down = run.result.get("downstream") or {}
            check("上游查询参数带上了请求数据（echo 回显一致）",
                  up.get("status") == 200 and data.get("task_id") == "T-1001"
                  and data.get("car") == "AGV-09" and data.get("steps") == 12,
                  json.dumps({"up": up, "data": data}, ensure_ascii=False)[:240])
            check("处理结果已转发下游", run.result.get("relayed") is True and down.get("status") == 200,
                  json.dumps(down, ensure_ascii=False)[:200])
            check("下游回显能证明中转内容正确",
                  isinstance(down.get("echoed"), dict)
                  and down["echoed"].get("task_id") == "T-1001"
                  and down["echoed"].get("source") == "agvmon/user-script",
                  json.dumps(down.get("echoed"), ensure_ascii=False)[:220])
            check("日志里有取数与转发记录",
                  any("上游" in line for line in run.logs) and any("转发" in line for line in run.logs),
                  json.dumps(run.logs, ensure_ascii=False)[:240])

        posts = [r for r in received2 if r["method"] == "POST" and r["path"] == "/api/echo-post"]
        check("下游服务确实收到了中转请求", len(posts) == 1,
              json.dumps(received2, ensure_ascii=False)[:200])
        if posts:
            payload = json.loads(posts[0]["body"])
            check("中转请求体是处理后的 JSON",
                  posts[0]["content_type"] == "application/json"
                  and payload.get("task_id") == "T-1001" and payload.get("steps") == 12,
                  json.dumps(payload, ensure_ascii=False)[:200])
        gets = [r for r in received2 if r["path"].startswith("/api/echo?")]
        check("上游收到了带参数的 GET", bool(gets) and "task_id=T-1001" in gets[0]["path"],
              gets[0]["path"] if gets else "(没有请求)")

        # 「脚本即 API 端点」示例：上游换成本地 echo，正常/缺参数两个分支都跑一遍
        api_example = _re.sub(
            r'local UPSTREAM\s*=\s*"[^"]*"',
            f'local UPSTREAM = "http://127.0.0.1:{port2}/api/echo"',
            dict(examples).get("API_ENDPOINT", ""),
        )
        check("API 端点示例被正确改写", "127.0.0.1" in api_example and "postman-echo" not in api_example)
        api_run = lua_runtime.execute_script(
            api_example, {"car": "AGV-07", "step": 12}, script_id="demo.api", config=cfg,
            # 模拟一次 HTTP 调用：脚本里的 ctx.query / ctx.request 就来自这里
            request={
                "method": "GET", "path": "/api/user-script/demo.api/run",
                "query": {"verbose": "1"}, "headers": {}, "ip": "10.0.0.9", "body": None,
            },
        )
        check("API 端点示例：返回转换后的数据", api_run.ok and api_run.result.get("ok") is True
              and (api_run.result.get("data") or {}).get("status") == "moving"
              and (api_run.result.get("data") or {}).get("car") == "AGV-07",
              (api_run.error or json.dumps(api_run.result, ensure_ascii=False))[:240])
        if api_run.ok:
            check("API 端点示例：带上上游状态与响应头",
                  (api_run.result.get("upstream") or {}).get("status") == 200
                  and (api_run.result.get("__headers") or {}).get("X-Service") == "agv-status",
                  json.dumps(api_run.result, ensure_ascii=False)[:240])
            check("API 端点示例：把调用方信息带回来",
                  (api_run.result.get("caller") or {}).get("method") == "GET"
                  and (api_run.result.get("caller") or {}).get("ip") == "10.0.0.9",
                  json.dumps(api_run.result.get("caller"), ensure_ascii=False))
            check("API 端点示例：?verbose=1 时附上上游原始响应",
                  "upstream_body" in (api_run.result.get("verbose") or {}),
                  json.dumps(api_run.result.get("verbose"), ensure_ascii=False)[:160])

        api_bad = lua_runtime.execute_script(api_example, {}, script_id="demo.api.bad", config=cfg)
        check("API 端点示例：缺参数返回 400 语义",
              api_bad.ok and api_bad.result.get("ok") is False and api_bad.result.get("__status") == 400,
              (api_bad.error or json.dumps(api_bad.result, ensure_ascii=False))[:200])

        # ------------------------------------------------------------------
        # 真实公网：示例脚本的默认地址（postman-echo）直接跑一遍。
        # 现场没有外网时只提示、不算失败；有外网时这就是"真调 API + 真中转"的证据。
        # ------------------------------------------------------------------
        real_cfg = lua_runtime.script_config()
        real_cfg["timeout_ms"] = 20000
        real_cfg["http"] = {**real_cfg["http"], "timeout_ms": 10000, "max_requests_per_run": 4}
        real = lua_runtime.execute_script(
            relay, {"car": "AGV-09", "task_id": "T-REAL", "step": 3}, script_id="demo.relay.real", config=real_cfg
        )
        if real.ok and real.result.get("ok") is True and real.result.get("relayed") is True:
            echoed = (real.result.get("downstream") or {}).get("echoed") or {}
            check("真实公网端到端（示例默认地址）", echoed.get("task_id") == "T-REAL",
                  f"{real.duration_ms}ms 上游{real.result['upstream']['status']} "
                  f"下游{real.result['downstream']['status']} echoed={json.dumps(echoed, ensure_ascii=False)[:120]}")
        else:
            reason = real.error if not real.ok else json.dumps(real.result, ensure_ascii=False)[:160]
            print(f"  [SKIP] 真实公网端到端：本机访问不了示例默认地址（{reason}）——"
                  "本地 echo 服务那几条已经覆盖了同样的代码路径")
    finally:
        server2.shutdown()
        server2.server_close()

    # ------------------------------------------------------------------
    section("11. 用户脚本页前端自检（模板绑定 / monaco 接线）")
    # ------------------------------------------------------------------
    vue_files = sorted((ROOT / "web" / "src").rglob("*.vue"))
    check("找得到 .vue 文件", len(vue_files) > 10, f"{len(vue_files)} 个")

    binding_problems: list[str] = []
    for path in vue_files:
        binding_problems.extend(vue_template_binding_problems(path))
    check("所有模板标识符都在 <script setup> 里定义过", not binding_problems,
          "；".join(binding_problems[:6]))

    # 反向自检：证明上面的检查真的会失败
    probe = ROOT / "web" / "src" / "views" / "__binding_probe__.vue"
    probe.write_text(
        "<template>\n  <n-button @click=\"notDefinedFn\">x</n-button>\n"
        "  <n-button @click=\"declaredFn(stop = true)\">y</n-button>\n</template>\n"
        "<script setup>\nfunction declaredFn(v) { return v }\n</script>\n",
        encoding="utf-8",
    )
    try:
        probe_problems = vue_template_binding_problems(probe)
    finally:
        probe.unlink(missing_ok=True)
    check("模板自检能抓出未定义的处理器", any("notDefinedFn" in p for p in probe_problems), str(probe_problems))
    check("模板自检能抓出给未定义名字赋值", any("stop" in p for p in probe_problems), str(probe_problems))

    monaco_problems = monaco_wiring_problems()
    check("monaco 接线与安装的包一致（路径/选项名）", not monaco_problems,
          "；".join(monaco_problems[:6]))

    worker_csp_problems = lua_worker_csp_problems()
    check("monaco worker 产物满足后端 CSP 的 worker-src（blob:）", not worker_csp_problems,
          "；".join(worker_csp_problems[:4]))

    grammar_source = (ROOT / "web" / "src" / "composables" / "luaLanguage.js").read_text(
        encoding="utf-8"
    )
    group_rules = lua_monarch_group_rules(grammar_source)
    print(f"    monarch 分组动作规则: {len(group_rules)} 条")
    grammar_problems = lua_monarch_group_problems(grammar_source)
    check("monarch 分组动作的捕获组覆盖整段匹配", not grammar_problems,
          "；".join(grammar_problems[:4]))

    # 反向自检：当初 4 条 luaMonaco 报错就是这条规则（点号在捕获组外）
    probe_src = (
        "tokenizer: {\n"
        "  [/([a-zA-Z_]\\w*)\\.([a-zA-Z_]\\w*)/, ['variable.predefined', 'property']],\n"
        "},\n"
        "// 语言配置\n"
    )
    probe_problems = lua_monarch_group_problems(probe_src)
    check("文法自检能抓出「捕获组外的点号」", any("\\." in p for p in probe_problems),
          str(probe_problems))
    # 反向自检 2：捕获组数与动作数不一致
    probe_src2 = (
        "tokenizer: {\n"
        "  [/([a-z]+)([0-9]+)/, ['keyword']],\n"
        "},\n"
        "// 语言配置\n"
    )
    probe_problems2 = lua_monarch_group_problems(probe_src2)
    check("文法自检能抓出「组数与动作数不匹配」",
          any("捕获组 2 个、动作 1 个" in p for p in probe_problems2), str(probe_problems2))

    # 真词法器：静态检查只是启发式，这条直接跑 monaco 自己的 monarch
    ran, runtime_problems, runtime_note = lua_monarch_runtime_problems()
    if ran:
        check("真 monarch 词法器跑完 4 个示例 + 边界样例（不抛分组错误）",
              not runtime_problems, "；".join(runtime_problems[:4]))
        if not runtime_problems:
            print("    json.encode(ctx.input.car) 的着色已确认：库名/点号/函数名 三段分开")
    else:
        print(f"  [SKIP] 真 monarch 词法器：{runtime_note}")

    # ------------------------------------------------------------------
    section("结果")
    # ------------------------------------------------------------------
    print(f"  通过 {PASS} 项，失败 {FAIL} 项")
    if FAILURES:
        print("  失败清单:")
        for name in FAILURES:
            print(f"    - {name}")
        return 1
    print("  全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
