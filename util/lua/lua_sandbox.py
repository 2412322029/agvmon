"""Lua 用户脚本沙箱（只能在 worker 子进程内导入）。

设计要点
========

1. **白名单环境**：先在完整 Lua 环境里由 ``LUA_PRELUDE`` 构造出"沙箱表"，
   然后把 ``_G`` 的键**全部清空**，再按白名单装回。属于"默认拒绝"而非
   "逐个删除黑名单"，因此 lupa 注入的 ``python`` 全局、``os``/``io``/
   ``package``/``require``/``debug``/``load``/``dofile``/``coroutine`` 之外
   的一切都不存在。``os`` 只保留 ``time``/``date``/``clock``/``difftime``
   这类无副作用的时间函数。

2. **Python 与 Lua 之间只传字符串**：请求 payload 和脚本结果都走 JSON 文本，
   脚本内容本身也是字符串。因此不会有任何 Python 对象被包装进 Lua 环境，
   从根本上杜绝这类逃逸::

       json.dumps.__globals__["__builtins__"]["__import__"]("os").system(...)

   （lupa 会把 Python 函数包装成 Lua 可调用的对象，其 ``__globals__``
   可以一路摸到 ``__builtins__``，实测在本机返回真实 cwd。见
   ``test_user_script.py`` 的逃逸回归用例。）

   唯一的例外是外部 HTTP 的桥（``http`` 表），它是**唯一**一个 Python 可调用
   对象：它在 ``lockdown`` 里作为参数传给 ``__install_http``，只被存成 Lua 闭包
   的 upvalue，既不在 ``_G`` 里也不在任何脚本能索引到的表里 —— Lua 没有 ``debug``
   库，无法反射出 upvalue。脚本能做的只是调用它，因此仍然是"只有字符串跨界"。
   回归用例见 ``test_user_script.py`` 里的 ``http 桥逃逸`` 一节。

3. **JSON 由纯 Lua 实现**：不注入 Python 的 ``json``，``json.encode`` /
   ``json.decode`` 均为 Lua 代码，语义见下。

4. **JSON null 语义**：null 映射为哨兵 ``json.null``（参考 lua-cjson 的
   ``cjson.null``），因此数组里的 null 不会被吞掉；只有"字段缺失"才是 nil。
   判断请用 ``v == json.null``。

5. **内存上限**由 lupa 的 Lua 分配器硬限制（构造时的 ``max_memory`` 参数），
   超限抛 ``LuaMemoryError``。**超时/死循环**由宿主强杀子进程解决：lupa 没有
   暴露 ``lua_sethook``，进程内无法中断正在执行的 C 层循环。

6. **不落地任何 .lua 资源文件**：prelude 内嵌为 Python 字符串常量，
   Nuitka 打包无需额外的 data-files 配置。
"""

from __future__ import annotations

import json

# ----------------------------------------------------------------------
# 沙箱环境构造脚本（Lua）
#
# 以 raw string 保存，反斜杠原样交给 Lua 解释；占位符用 str.replace 注入，
# 避免 str.format 与 Lua 里的 % 冲突。
# ----------------------------------------------------------------------
LUA_PRELUDE = r"""
-- ======================================================================
-- 纯 Lua JSON 实现（encode / decode）
-- ======================================================================
local json = {}
local MAX_DEPTH = __MAX_DEPTH__
local MAX_NODES = __MAX_NODES__

-- JSON null 哨兵：与 nil 区分，保证数组中的 null 不丢位置
local NULL = setmetatable({}, { __tostring = function() return 'json.null' end })
json.null = NULL

-- ---------------------------- 编码 ----------------------------
local ESCAPE_MAP = {
  ['"'] = '\\"', ['\\'] = '\\\\', ['\b'] = '\\b',
  ['\f'] = '\\f', ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t',
}

local function escape_string(s)
  return (s:gsub('[%c\\"]', function(c)
    return ESCAPE_MAP[c] or string.format('\\u%04x', c:byte())
  end))
end

local enc_nodes
local function encode_value(v, out, depth)
  enc_nodes = enc_nodes + 1
  if enc_nodes > MAX_NODES then
    error('json.encode: 结果节点数超过上限 ' .. MAX_NODES, 0)
  end
  if depth > MAX_DEPTH then
    error('json.encode: 嵌套超过 ' .. MAX_DEPTH .. ' 层（可能存在循环引用）', 0)
  end

  local t = type(v)
  if v == NULL then
    out[#out + 1] = 'null'
  elseif t == 'nil' then
    -- 数组空洞，按 null 处理
    out[#out + 1] = 'null'
  elseif t == 'boolean' then
    out[#out + 1] = v and 'true' or 'false'
  elseif t == 'number' then
    if v ~= v or v == math.huge or v == -math.huge then
      error('json.encode: 无法编码非有限数字 ' .. tostring(v), 0)
    end
    if math.type and math.type(v) == 'integer' then
      out[#out + 1] = string.format('%d', v)
    else
      out[#out + 1] = string.format('%.14g', v)
    end
  elseif t == 'string' then
    out[#out + 1] = '"' .. escape_string(v) .. '"'
  elseif t == 'table' then
    if depth > MAX_DEPTH then
      error('json.encode: 嵌套超过 ' .. MAX_DEPTH .. ' 层', 0)
    end
    -- 判定数组：所有键都是 >=1 的整数，且个数等于最大下标
    local nkeys, maxi, is_array = 0, 0, true
    for k in pairs(v) do
      nkeys = nkeys + 1
      if type(k) == 'number' and k >= 1 and k % 1 == 0 then
        if k > maxi then maxi = k end
      else
        is_array = false
        break
      end
    end

    if nkeys == 0 then
      out[#out + 1] = '{}'
    elseif is_array and nkeys == maxi then
      out[#out + 1] = '['
      for i = 1, maxi do
        if i > 1 then out[#out + 1] = ',' end
        encode_value(v[i], out, depth + 1)
      end
      out[#out + 1] = ']'
    else
      -- 对象：键排序，保证输出稳定可复现
      local keys = {}
      for k in pairs(v) do keys[#keys + 1] = k end
      table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
      out[#out + 1] = '{'
      for i = 1, #keys do
        local k = keys[i]
        local kt = type(k)
        if kt ~= 'string' and kt ~= 'number' then
          error('json.encode: 表键必须是字符串或数字，实际为 ' .. kt, 0)
        end
        if i > 1 then out[#out + 1] = ',' end
        out[#out + 1] = '"' .. escape_string(tostring(k)) .. '":'
        encode_value(v[k], out, depth + 1)
      end
      out[#out + 1] = '}'
    end
  else
    error('json.encode: 不支持的类型 ' .. t .. '（只能返回字符串/数字/布尔/表/空值）', 0)
  end
end

function json.encode(v)
  local out = {}
  enc_nodes = 0
  encode_value(v, out, 1)
  return table.concat(out)
end

-- ---------------------------- 解码 ----------------------------
local UNESCAPE = {
  ['"'] = '"', ['\\'] = '\\', ['/'] = '/',
  b = '\b', f = '\f', n = '\n', r = '\r', t = '\t',
}

local dec_nodes

local function utf8_char(cp)
  if utf8 then return utf8.char(cp) end
  if cp < 128 then return string.char(cp) end
  error('json.decode: 当前 Lua 缺少 utf8 库，无法解码 \\u 转义', 0)
end

local function skip_ws(s, i)
  local _, e = s:find('^[ \t\r\n]*', i)
  return e + 1
end

local function decode_string(s, i)
  -- s:sub(i, i) == '"'
  local buf, j = {}, i + 1
  while true do
    local stop = s:find('["\\]', j)
    if not stop then error('json.decode: 字符串未闭合', 0) end
    buf[#buf + 1] = s:sub(j, stop - 1)
    if s:sub(stop, stop) == '"' then
      return table.concat(buf), stop + 1
    end
    -- 处理转义
    local e = s:sub(stop + 1, stop + 1)
    if e == '' then error('json.decode: 转义符后输入结束', 0) end
    if e == 'u' then
      local hex = s:sub(stop + 2, stop + 5)
      if not hex:find('^%x%x%x%x$') then
        error('json.decode: 非法 \\u 转义 "\\u' .. hex .. '"', 0)
      end
      local cp = tonumber(hex, 16)
      j = stop + 6
      if cp >= 0xD800 and cp <= 0xDBFF and s:sub(j, j + 1) == '\\u' then
        local hex2 = s:sub(j + 2, j + 5)
        local lo = tonumber(hex2, 16)
        if lo and lo >= 0xDC00 and lo <= 0xDFFF then
          cp = 0x10000 + (cp - 0xD800) * 0x400 + (lo - 0xDC00)
          j = j + 6
        end
      end
      if cp >= 0xD800 and cp <= 0xDFFF then
        buf[#buf + 1] = '\239\191\189'  -- 孤立代理项 -> U+FFFD
      else
        buf[#buf + 1] = utf8_char(cp)
      end
    else
      local m = UNESCAPE[e]
      if not m then error('json.decode: 非法转义 "\\' .. e .. '"', 0) end
      buf[#buf + 1] = m
      j = stop + 2
    end
  end
end

local function decode_number(s, i)
  local _, e = s:find('^%-?%d+%.?%d*[eE]?[%+%-]?%d*', i)
  if not e then error('json.decode: 非法数字', 0) end
  local raw = s:sub(i, e)
  local num = tonumber(raw)
  if not num then error('json.decode: 非法数字 "' .. raw .. '"', 0) end
  return num, e + 1
end

local decode_value  -- 前置声明（数组/对象互相递归）

local function decode_array(s, i, depth)
  local arr, idx = {}, 1
  i = skip_ws(s, i + 1)
  if s:sub(i, i) == ']' then return arr, i + 1 end
  while true do
    local v
    v, i = decode_value(s, i, depth + 1)
    arr[idx] = v
    idx = idx + 1
    i = skip_ws(s, i)
    local c = s:sub(i, i)
    if c == ',' then
      i = skip_ws(s, i + 1)
    elseif c == ']' then
      return arr, i + 1
    else
      error('json.decode: 数组在位置 ' .. i .. ' 处缺少 , 或 ]', 0)
    end
  end
end

local function decode_object(s, i, depth)
  local obj = {}
  i = skip_ws(s, i + 1)
  if s:sub(i, i) == '}' then return obj, i + 1 end
  while true do
    if s:sub(i, i) ~= '"' then
      error('json.decode: 对象键必须是字符串（位置 ' .. i .. '）', 0)
    end
    local key
    key, i = decode_string(s, i)
    i = skip_ws(s, i)
    if s:sub(i, i) ~= ':' then
      error('json.decode: 对象键后缺少 :（位置 ' .. i .. '）', 0)
    end
    i = skip_ws(s, i + 1)
    local v
    v, i = decode_value(s, i, depth + 1)
    obj[key] = v
    i = skip_ws(s, i)
    local c = s:sub(i, i)
    if c == ',' then
      i = skip_ws(s, i + 1)
    elseif c == '}' then
      return obj, i + 1
    else
      error('json.decode: 对象在位置 ' .. i .. ' 处缺少 , 或 }', 0)
    end
  end
end

decode_value = function(s, i, depth)
  dec_nodes = dec_nodes + 1
  if dec_nodes > MAX_NODES then
    error('json.decode: 节点数超过上限 ' .. MAX_NODES, 0)
  end
  if depth > MAX_DEPTH then
    error('json.decode: 嵌套超过 ' .. MAX_DEPTH .. ' 层', 0)
  end

  i = skip_ws(s, i)
  local c = s:sub(i, i)
  if c == '' then error('json.decode: 输入意外结束', 0) end
  if c == '"' then return decode_string(s, i) end
  if c == '{' then return decode_object(s, i, depth) end
  if c == '[' then return decode_array(s, i, depth) end
  if c == 't' then
    if s:sub(i, i + 3) == 'true' then return true, i + 4 end
  elseif c == 'f' then
    if s:sub(i, i + 4) == 'false' then return false, i + 5 end
  elseif c == 'n' then
    if s:sub(i, i + 3) == 'null' then return NULL, i + 4 end
  elseif c == '-' or (c >= '0' and c <= '9') then
    return decode_number(s, i)
  end
  error('json.decode: 位置 ' .. i .. ' 处出现意外字符 "' .. c .. '"', 0)
end

function json.decode(text)
  if type(text) ~= 'string' then
    error('json.decode: 参数必须是字符串，实际为 ' .. type(text), 0)
  end
  if #text > 4 * 1024 * 1024 then
    error('json.decode: 输入超过 4MB', 0)
  end
  dec_nodes = 0
  local v, i = decode_value(text, 1, 1)
  i = skip_ws(text, i)
  if i <= #text then
    error('json.decode: 位置 ' .. i .. ' 之后存在多余内容', 0)
  end
  return v
end

-- ======================================================================
-- 沙箱表构造
-- ======================================================================
local S = {}

S._VERSION = _VERSION
S.assert = assert          S.error = error        S.type = type
S.tostring = tostring      S.tonumber = tonumber  S.select = select
S.next = next              S.pairs = pairs        S.ipairs = ipairs
S.pcall = pcall            S.xpcall = xpcall      S.rawequal = rawequal
S.rawget = rawget          S.rawset = rawset      S.rawlen = rawlen
S.setmetatable = setmetatable  S.getmetatable = getmetatable
S.coroutine = coroutine

-- string/table/math/utf8 均为纯 Lua 实现，无 IO 能力
string.dump = nil          -- 没有 load 时本就无用，仍然显式移除
S.string = string
S.table = table
S.math = math
if utf8 then S.utf8 = utf8 end

-- os 只保留无副作用的时间函数
S.os = {
  time = os.time, date = os.date, clock = os.clock, difftime = os.difftime,
}

-- ======================================================================
-- 日志收集：print/console 写入内部缓冲，绝不污染 worker 的 stdout
-- ======================================================================
local logs = {}
local MAX_LOGS = __MAX_LOGS__

local function push(...)
  if #logs >= MAX_LOGS then return end
  local n = select('#', ...)
  local parts = {}
  for i = 1, n do
    local v = select(i, ...)
    parts[i] = (type(v) == 'string') and v or tostring(v)
  end
  logs[#logs + 1] = table.concat(parts, '\t')
end

S.__logs = logs
S.log = push
S.print = push
S.console = { log = push, info = push, warn = push, error = push, debug = push }
S.json = json

-- ======================================================================
-- 外部 HTTP
--
-- 网络动作在宿主 Python 进程里做（Lua 自己碰不到 socket）；这里只负责整理参数、
-- 解码结果。宿主那个 Python 可调用对象由 __install_http 存进**闭包 upvalue**，
-- 脚本拿不到它 —— 所以 http.request.__globals__ 这类爬 Python 对象的逃逸路径不成立。
-- ======================================================================
local http_call = nil
local ALLOWED_METHODS = {
  GET = true, POST = true, PUT = true, PATCH = true, DELETE = true, HEAD = true,
}

local function urlencode(s)
  return (tostring(s):gsub('[^%w%-_%.~]', function(c)
    return string.format('%%%02X', string.byte(c))
  end))
end

local function with_query(url, params)
  if type(params) ~= 'table' then return url end
  local parts = {}
  for k, v in pairs(params) do
    parts[#parts + 1] = urlencode(k) .. '=' .. urlencode(v)
  end
  if #parts == 0 then return url end
  table.sort(parts)  -- 顺序稳定，便于复现
  local sep = url:find('?', 1, true) and '&' or '?'
  return url .. sep .. table.concat(parts, '&')
end

-- 响应是 JSON 时顺手解一份，脚本不用每次自己 decode
local function attach_json(res)
  if type(res) ~= 'table' or not res.ok then return res end
  local body = res.body
  if type(body) ~= 'string' or #body == 0 then return res end
  local ct = string.lower(tostring(res.content_type or ''))
  local first = body:sub(1, 1)
  if ct:find('json', 1, true) or first == '{' or first == '[' then
    local ok, decoded = pcall(json.decode, body)
    if ok then res.json = decoded end
  end
  return res
end

local function raw_request(spec)
  if http_call == nil then
    return { ok = false, error = 'HTTP 桥未就绪', error_type = 'http_unavailable' }
  end
  local ok, raw = pcall(http_call, json.encode(spec))
  if not ok then
    return { ok = false, error = tostring(raw), error_type = 'http_internal' }
  end
  local decoded_ok, decoded = pcall(json.decode, raw)
  if not decoded_ok or type(decoded) ~= 'table' then
    return { ok = false, error = '宿主返回了非法结果', error_type = 'http_internal' }
  end
  return attach_json(decoded)
end

local function has_content_type(headers)
  for k in pairs(headers) do
    if string.lower(tostring(k)) == 'content-type' then return true end
  end
  return false
end

local http = {}

function http.request(spec)
  if type(spec) ~= 'table' then
    return { ok = false, error = 'http.request 的参数必须是 table', error_type = 'http_badarg' }
  end
  if type(spec.url) ~= 'string' or spec.url == '' then
    return { ok = false, error = 'url 不能为空', error_type = 'http_url' }
  end

  local method = string.upper(tostring(spec.method or 'GET'))
  if not ALLOWED_METHODS[method] then
    return { ok = false, error = '不支持的 method: ' .. method, error_type = 'http_method' }
  end

  local headers = spec.headers
  if headers ~= nil and type(headers) ~= 'table' then
    return { ok = false, error = 'headers 必须是 table', error_type = 'http_badarg' }
  end

  local body = spec.body
  if body == nil and spec.json ~= nil then body = spec.json end
  if type(body) == 'table' then
    local ok, encoded = pcall(json.encode, body)
    if not ok then
      return { ok = false, error = 'body/json 无法编码: ' .. tostring(encoded),
               error_type = 'http_badarg' }
    end
    body = encoded
    if headers == nil then headers = {} end
    if not has_content_type(headers) then headers['Content-Type'] = 'application/json' end
  elseif body ~= nil and type(body) ~= 'string' then
    return { ok = false, error = 'body 必须是字符串或 table', error_type = 'http_badarg' }
  end

  return raw_request({
    url = with_query(spec.url, spec.params),
    method = method,
    headers = headers,
    body = body,
    timeout_ms = tonumber(spec.timeout_ms),
  })
end

local function send(method, url, body, opts)
  opts = opts or {}
  local spec = {
    url = url,
    method = method,
    headers = opts.headers,
    params = opts.params,
    timeout_ms = opts.timeout_ms,
  }
  if body ~= nil then spec.body = body end
  return http.request(spec)
end

function http.get(url, opts) return send('GET', url, nil, opts) end
function http.head(url, opts) return send('HEAD', url, nil, opts) end
function http.delete(url, opts) return send('DELETE', url, nil, opts) end
function http.post(url, body, opts) return send('POST', url, body, opts) end
function http.put(url, body, opts) return send('PUT', url, body, opts) end
function http.patch(url, body, opts) return send('PATCH', url, body, opts) end
http.fetch = http.request

S.http = http
-- 宿主注入 HTTP 桥。注意：lupa 包装出来的 Python 可调用对象在 Lua 里的 type()
-- 不是 'function'（是 userdata），所以这里只能判 nil，不能判类型。
S.__install_http = function(raw)
  if raw ~= nil then http_call = raw end
end

-- ======================================================================
-- 内部驱动（不以 __ 前缀暴露给脚本：装回全局时会被跳过）
-- ======================================================================
local function __prepare(payload_json, script_id, limits_json, request_json)
  local env = _ENV

  -- 重置上一次运行留下的状态，保证多次运行互不影响
  -- （worker 目前是一进程一次执行，但模块本身要能安全复用）
  env['handle'] = nil
  env['input'] = nil
  env['output'] = nil
  for i = #logs, 1, -1 do logs[i] = nil end

  local payload = json.decode(payload_json)
  local limits = json.decode(limits_json)
  local request = json.decode(request_json or '{}')

  -- 请求体：JSON null（含"没有 body"）在 Lua 侧统一看成 nil
  local body = request.body
  if body == NULL then body = nil end
  local query = request.query
  if type(query) ~= 'table' then query = {} end

  -- 结果容器，允许脚本用 output.xxx = ... 而不必 return
  local out = {}
  env['output'] = out
  env['input'] = payload

  return {
    input = payload,
    output = out,
    -- 请求本身的元信息：脚本要当"API 端点"给别的服务用时靠它
    body = body,               -- JSON 解析后的原始 body（对象/数组/字符串，空就是 nil）
    query = query,             -- query 参数（值都是字符串）
    request = request,         -- { method, path, query, headers, ip, content_type }
    script_id = script_id,
    mode = 'run',
    now = os.time(),
    json = json,
    log = push,
    limits = limits,
  }
end

local function __run(chunk, ctx)
  local env = _ENV
  local result = chunk(ctx)

  -- 脚本定义了 handle(ctx) 时优先采用它的返回值
  local handler = env['handle']
  if type(handler) == 'function' then
    local r = handler(ctx)
    if r ~= nil then result = r end
  end

  if result == nil then
    result = env['output']
  end
  if result == nil then
    result = NULL
  end
  return json.encode(result)
end

S.__prepare = __prepare
S.__run = __run

return S
"""

# 白名单装回全局时跳过的内部键
_PRIVATE_PREFIX = "__"


class LuaSecurityError(RuntimeError):
    """沙箱构造/策略违规。"""


def import_lupa():
    """导入 lupa。

    显式按变体名导入，而不是依赖 ``lupa.LuaRuntime`` 的运行时目录扫描
    （``lupa/__init__._import_newest_lib`` 用 ``os.listdir`` + ``__import__``
    动态发现实现），这样 Nuitka 的静态分析才能正确收集扩展模块。
    """
    import lupa

    for variant in ("lua55", "lua54", "lua53", "lua52", "lua51", "luajit21", "luajit20"):
        try:
            mod = __import__("lupa." + variant, fromlist=[variant])
        except ImportError:
            continue
        return lupa, mod
    # 兜底：交给 lupa 自己的动态发现
    return lupa, lupa


def runtime_available() -> bool:
    """lupa / Lua VM 是否可用（宿主侧做健康检查用，不导入 lupa）。"""
    try:
        import importlib.util

        return importlib.util.find_spec("lupa") is not None
    except Exception:
        return False


def build_runtime(max_memory_bytes: int, **kwargs):
    """创建受限 Lua 运行时。

    :param max_memory_bytes: Lua 分配器硬上限，由 lupa 在 C 层强制执行。
    """
    lupa, variant = import_lupa()
    runtime_cls = getattr(variant, "LuaRuntime", None) or lupa.LuaRuntime
    return runtime_cls(
        encoding="utf-8",
        unpack_returned_tuples=True,
        max_memory=int(max_memory_bytes),
        **kwargs,
    )


def lockdown(
    lua,
    *,
    max_log_lines: int,
    max_depth: int,
    max_nodes: int,
    http_bridge=None,
):
    """构造沙箱环境。

    返回 ``(sandbox, logs)``：``sandbox`` 是 prelude 返回的 Lua 表（含
    ``__run`` / ``__prepare`` / ``__logs``），``logs`` 是日志缓冲表。

    完成后 Lua 全局表中**只剩白名单项**。

    :param http_bridge: 形如 ``callable(spec_json: str) -> result_json: str`` 的
        Python 可调用对象。它只在安装时作为 upvalue 存进 Lua 闭包，不进入任何
        全局表；脚本因此拿不到这个 Python 对象。为 None 时 ``http.*`` 会返回
        ``error_type=http_unavailable``。
    """
    prelude = (
        LUA_PRELUDE.replace("__MAX_DEPTH__", str(int(max_depth)))
        .replace("__MAX_NODES__", str(int(max_nodes)))
        .replace("__MAX_LOGS__", str(int(max_log_lines)))
    )

    sandbox = lua.execute(prelude)
    if sandbox is None:
        raise LuaSecurityError("沙箱 prelude 未返回环境表")

    # 先把 HTTP 桥装进闭包 upvalue，再清全局 —— 顺序无所谓，但早装早省心
    installer = sandbox["__install_http"]
    if installer is not None:
        installer(http_bridge)

    # 白名单装回：先清空全部全局，再只装回 prelude 给出的项
    globals_table = lua.globals()
    for key in list(globals_table.keys()):
        globals_table[key] = None

    for key, value in sandbox.items():
        if isinstance(key, str) and key.startswith(_PRIVATE_PREFIX):
            continue  # __run / __prepare / __logs / __install_http 不给脚本看
        globals_table[key] = value

    globals_table["_G"] = globals_table

    # 自检：确认危险全局确实不存在、Python 桥也确实没漏进全局表
    leaked = [
        name
        for name in ("os.execute", "io", "package", "require", "debug", "load",
                     "loadfile", "dofile", "python", "warn", "jit", "ffi", "collectgarbage",
                     "__install_http", "__run", "__prepare", "http_call")
        if _global_exists(globals_table, name)
    ]
    if leaked:
        raise LuaSecurityError(f"沙箱自检失败，以下全局仍然存在: {', '.join(leaked)}")

    logs = sandbox["__logs"]
    if logs is None:
        raise LuaSecurityError("沙箱 prelude 未提供日志缓冲")
    return sandbox, logs


def _global_exists(globals_table, dotted: str) -> bool:
    """检查 ``a.b`` 形式的全局链是否存在（用于沙箱自检）。

    用下标而不是属性访问，避免与 lupa ``_LuaTable`` 的 Python 方法名撞车。
    """
    head, _, tail = dotted.partition(".")
    value = globals_table[head]
    if value is None:
        return False
    if not tail:
        return True
    try:
        return value[tail] is not None
    except Exception:
        return False


def _compile(lua, code: str, script_id: str):
    """编译用户脚本为 Lua 函数（不执行）。"""
    try:
        return lua.compile(code, f"@{script_id}")
    except TypeError:
        # 老版本 lupa 的签名只接受一个参数
        return lua.compile(code)


def read_logs(logs_table) -> list[str]:
    """按顺序读出日志缓冲（Lua 数组，用下标读取保证顺序）。"""
    out: list[str] = []
    try:
        n = len(logs_table)
    except Exception:
        return out
    for i in range(1, n + 1):
        item = logs_table[i]
        out.append(item if isinstance(item, str) else str(item))
    return out


def _limits_json(limits: dict) -> str:
    return json.dumps(
        {
            "timeout_ms": limits.get("timeout_ms"),
            "max_memory_mb": limits.get("max_memory_mb"),
            "max_result_kb": limits.get("max_result_kb"),
            "max_depth": limits.get("max_depth"),
            "max_nodes": limits.get("max_nodes"),
        },
        ensure_ascii=False,
    )


def check_syntax(lua, code: str, script_id: str) -> None:
    """只编译不执行；语法错误抛 ``lupa.LuaSyntaxError``。"""
    _compile(lua, code, script_id)


def execute(
    lua,
    sandbox,
    code: str,
    payload_json: str,
    script_id: str,
    limits: dict,
    request_json: str = "{}",
) -> str:
    """在沙箱内执行脚本，返回结果的 JSON 文本。

    全程只有字符串在 Python 与 Lua 之间传递。

    :param request_json: 这次 HTTP 请求的元信息（method/path/query/headers/ip/body），
        脚本通过 ``ctx.request`` / ``ctx.body`` / ``ctx.query`` 拿到。
    """
    chunk = _compile(lua, code, script_id)

    context = sandbox["__prepare"](
        payload_json, script_id, _limits_json(limits), request_json or "{}"
    )
    result_json = sandbox["__run"](chunk, context)

    if not isinstance(result_json, str):
        raise RuntimeError(
            f"内部错误：结果编码未返回字符串（{type(result_json).__name__}）"
        )
    return result_json


def runtime_info(lua) -> dict:
    """运行时的 Lua 实现信息。"""
    lupa, _ = import_lupa()
    try:
        max_memory = lua.get_max_memory()
    except Exception:
        max_memory = None
    return {
        "lupa": getattr(lupa, "__version__", "unknown"),
        "lua": getattr(lua, "lua_implementation", "unknown"),
        "lua_version": list(getattr(lua, "lua_version", ()) or ()),
        "max_memory_bytes": max_memory,
    }
