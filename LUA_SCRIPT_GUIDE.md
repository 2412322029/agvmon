# 用户 Lua 脚本编写指南（AI 版）

> **读者**：需要为本平台**生成、修改、审查用户脚本**的 AI（人类同样适用）。
> **目标**：写出来的脚本第一次跑就通、能当 API 端点给别的服务调用、出错时能被快速定位。
> **事实来源**：本文每一条都对应仓库当前实现 —— 运行时 `util/lua_sandbox.py` / `util/lua_runtime.py`、
> 外部 HTTP `util/lua_http.py`、接口层 `backend/api/user_script.py`、脚本库 `util/user_script_store.py`、
> 默认配置 `util/config.toml`。改代码时请同步改本文。
> 一般不用读取修改py.
---

## 目录

1. [30 秒速览（先看这个）](#1-30-秒速览先看这个)
2. [运行模型：脚本跑在什么地方](#2-运行模型脚本跑在什么地方)
3. [脚本骨架与返回约定](#3-脚本骨架与返回约定)
4. [`ctx` 与全局变量全表](#4-ctx-与全局变量全表)
5. [入参是怎么来的（三种调用姿势）](#5-入参是怎么来的三种调用姿势)
6. [JSON 语义与坑](#6-json-语义与坑)
7. [调用外部 HTTP](#7-调用外部-http)
8. [把脚本当 API 端点](#8-把脚本当-api-端点)
9. [可用标准库白名单](#9-可用标准库白名单)
10. [错误类型与调试](#10-错误类型与调试)
11. [资源预算](#11-资源预算)
12. [可复制的脚本模式库](#12-可复制的脚本模式库)
13. [反模式清单](#13-反模式清单)
14. [交付前自检清单](#14-交付前自检清单)
15. [通过 HTTP 管理脚本](#15-通过-http-管理脚本)
16. [配置速查](#16-配置速查)

---

## 1. 30 秒速览（先看这个）

**六个硬约束**（违反任何一个都会让脚本失败或行为不符预期）：

| # | 约束 | 说明 |
|---|------|------|
| 1 | 沙箱里**没有 `os.execute` / `io` / `require` / `load` / `debug` / `package`** | 也不能访问文件、环境变量、网络 socket。唯一的外部动作是 `http.*` |
| 2 | **只有字符串能跨语言** | 脚本给宿主的一切都经过 `json.encode`，因此返回值必须是「字符串/数字/布尔/表/`json.null`」 |
| 3 | **JSON null ≠ nil** | 解码得到的 null 是哨兵 `json.null`；表里显式写 `nil` 等于**没有这个字段** |
| 4 | **外部 HTTP 要过策略** | 默认禁内网/回环、单次执行最多 6 个请求、响应超 512KB 截断、每一次都计进总超时 |
| 5 | **超时 = 杀进程** | 墙钟超时（默认 8000ms）直接 `kill`，脚本没有"优雅退出"的机会 |
| 6 | **默认只有本机可调用** | 别的服务要调，得开 `allow_remote` + `api_key`，并带 `X-API-Key` 请求头 |

**最小可用骨架**（新建脚本时的默认内容就是它）：

```lua
-- ctx.input  请求体（JSON 解码后的 table）
-- 返回值即响应内容
function handle(ctx)
  local data = ctx.input or {}
  log("收到数据:", ctx.json.encode(data))
  return { ok = true, car = data.car, ts = os.time() }
end
```

**一段"能当接口用"的骨架**（详见 [§12](#12-可复制的脚本模式库)）：

```lua
local UPSTREAM = "http://wms.internal/api/agv"   -- 内网要开 allow_private_hosts

function handle(ctx)
  local d = ctx.input or {}
  if d.car == nil then
    return { ok = false, error = "缺少 car 参数", __status = 400 }   -- 给调用方一个明确的 400
  end
  local up = http.get(UPSTREAM, { params = { car = d.car }, timeout_ms = 3000 })
  if not up.ok then
    return { ok = false, error = "上游不可用", detail = up.error,
             error_type = up.error_type, __status = 502 }            -- 网关式语义
  end
  return { ok = true, data = { car = d.car, status = (up.json or {}).status },
           __headers = { ["X-Service"] = "agv-status" } }
end
```

---

## 2. 运行模型：脚本跑在什么地方

```
HTTP 请求
   │
   ├─ FastAPI 路由（backend/api/user_script.py）
   │    ├─ 访问闸门：本机 / allow_remote + X-API-Key
   │    ├─ 把请求变成入参（query + body 合并）
   │    └─ 落一条执行审计（user_script_runs）
   │
   ├─ 起一个**独立子进程**跑 worker（util/lua_worker.py）
   │    ├─ stdin 收一个 JSON job（code / payload / limits / http 策略 / request 元信息）
   │    ├─ lupa 建 Lua 5.5 运行时（lupa 在 C 层限制内存）
   │    ├─ 白名单锁定全局表（先清空所有全局，再装回允许的那些）
   │    ├─ 编译并执行脚本
   │    └─ stdout 打一行 `__AGVMON_LUA_RESULT__ {json}`
   │
   └─ 父进程：墙钟超时（默认 8s）到点就 kill；解析结果，套上响应信封返回
```

对写脚本有实际影响的四点：

1. **进程隔离**：脚本崩了、死循环了、把内存写爆了，都不会影响主服务 —— 但也**没有任何跨请求状态**。
   每次执行都是全新的 Lua 运行时，全局变量不会保留，不要写"上次的结果我存在全局里"。
2. **内存硬上限**：`max_memory_mb`（默认 64）由 lupa 在 C 层卡住，超了抛 `LuaMemoryError`（`error_type=memory`）。
3. **超时按墙钟算**：包含建运行时、编译、联网等待在内的全部时间。**联网脚本要按调用次数分配预算**（见 [§11](#11-资源预算)）。
4. **并发上限**：`max_concurrency`（默认 4）。排队超过 `timeout_ms + 5s` 直接返回 `error_type=busy`。

> `ctx.mode` 在真正执行时恒为 `"run"`。语法检查模式（`POST /{id}/check`）**只编译不执行**，
> 脚本正文一行都不会跑 —— 所以不要写"`if mode == 'check' then` 跳过危险操作"这种逻辑，
> 它永远不会被执行到，也没有必要。

---

## 3. 脚本骨架与返回约定

脚本正文是一个 **Lua chunk**，宿主会用一个参数 `ctx` 调用它，然后按下面的优先级取结果：

```
1. handle(ctx) 的非 nil 返回值      ← 推荐只依赖这一条
2. chunk 自身的 return 值（通常是 nil）
3. 全局 output 表（output.xxx = ... 累积的内容）
4. json.null                        ← 三者都没有时，result 就是 null
```

四种等价写法（都能跑，**推荐第一种**）：

**① 推荐：全局 `handle`**

```lua
function handle(ctx)
  return { ok = true, n = 1 }
end
```

**② 顶层 return**（简单脚本可以用；注意它必须是 chunk 的最后一条语句）

```lua
local d = ctx.input or {}
return { ok = true, car = d.car }
```

**③ `output` 容器**（不 return，宿主用 `output` 当结果）

```lua
function handle(ctx)
  output.ok = true
  output.n = 1
end
```

**④ 两者混用**：`handle` 返回非 nil 时**覆盖** `output`

```lua
function handle(ctx)
  output.debug = "这个会被丢掉"
  return { ok = true }          -- 最终结果是 { ok = true }
end
```

几个必须记住的细节：

* `handle` **必须接受一个参数**（收到的是 `ctx`）。写成 `function handle()` 也能跑，但你拿不到入参。
* `handle` 返回 `nil`（或没有 return）**不会**清空结果 —— 宿主会退回到 chunk 返回值，再退回 `output`。
* 脚本**报错**时（`error` / `assert` 失败 / 类型错误）：HTTP 仍是 **200**，信封里 `ok=false` +
  `error` + `error_type=lua`。想要调用方看到真正的 4xx/5xx，必须显式给 `__status`（见 [§8](#8-把脚本当-api-端点)）。
* 中文、emoji 都能返回（UTF-8）；大整数建议控制在 Lua integer 范围内。

---

## 4. `ctx` 与全局变量全表

### 4.1 `ctx` 字段（全部）

| 字段 | 类型 | 说明 |
|------|------|------|
| `ctx.input` | table | 本次入参。**query 与 body 已合并**，同名字段以 body 为准。与全局 `input` 是同一个表 |
| `ctx.output` | table | 结果容器。`ctx.output.x = 1` 等价于 `output.x = 1` |
| `ctx.json` | table | 同全局 `json`（`encode` / `decode` / `null`） |
| `ctx.log` | function | 同全局 `log` |
| `ctx.script_id` | string | 当前脚本 ID |
| `ctx.mode` | string | 实际执行恒为 `"run"` |
| `ctx.now` | number | 执行时刻的 Unix 时间戳（秒），等价于 `os.time()` |
| `ctx.limits` | table | 本次限制：`timeout_ms` / `max_memory_mb` / `max_result_kb` / `max_depth` / `max_nodes` |
| `ctx.query` | table | **仅** query 参数；值都是字符串；同名参数取第一个。没有就是空表（不是 nil） |
| `ctx.body` | any | **原始请求体** JSON 解析后的值：对象 / 数组 / 字符串 / `nil`（没有 body） |
| `ctx.request` | table | 请求元信息（见下表） |

`ctx.request` 的字段：

| 字段 | 说明 |
|------|------|
| `method` | `"GET"` / `"POST"` ... |
| `path` | 请求路径，如 `/api/user-script/demo.api/run` |
| `query` | 同 `ctx.query` |
| `headers` | **白名单**请求头（见下） |
| `ip` | 调用方 IP（经过反向代理时是代理的 IP，同时能拿到 `x-forwarded-for`） |
| `content_type` | `Content-Type`（没有就是空串） |
| `body` | 与 `ctx.body` 同一个值 |

**脚本能看到的请求头（白名单，只有这 10 个）**：
`content-type`、`accept`、`accept-language`、`user-agent`、`x-request-id`、`x-forwarded-for`、
`x-real-ip`、`referer`、`origin`、`host`。

> ⚠️ **`X-API-Key` 永远不会传给脚本**（白名单机制，不是黑名单过滤）。
> 推论：**脚本无法用自定义请求头做业务鉴权**。要传业务令牌，走 body 或 query（如 `?token=...`），
> 并且自己比对 —— 想追踪调用链就用 `x-request-id`。

### 4.2 全局变量

| 名字 | 说明 |
|------|------|
| `input` | 同 `ctx.input` |
| `output` | 结果容器（`ctx.output` 是同一个表） |
| `handle` | 由**脚本自己定义**的入口函数（宿主回调它） |
| `ctx` | 本次执行上下文 |
| `json` / `http` | 见 [§6](#6-json-语义与坑) / [§7](#7-调用外部-http) |
| `log` / `print` / `console` | 写执行日志（多个参数用 Tab 连接）。**只进日志缓冲，不会写到 worker 的 stdout** |
| `assert` `error` `type` `tostring` `tonumber` `select` `next` `pairs` `ipairs` `pcall` `xpcall` `rawequal` `rawget` `rawset` `rawlen` `setmetatable` `getmetatable` `coroutine` | 标准库（`coroutine` 可用，但**主流程本身跑在 Lua 主协程里，脚本自己 `yield` 会报错**） |
| `string` `table` `math` `utf8` `os` | 标准库（`os` 只剩时间函数，见 [§9](#9-可用标准库白名单)） |
| `_VERSION` | 例如 `"Lua 5.5"` |
| `_G` | 沙箱全局表本体（只含白名单项） |

日志上限：`max_log_lines`（默认 200）行，单行超过 2000 字符会被截断。**日志会随信封一起返回**，
所以"把中间结果 log 出来"是最省事的调试手段 —— 但不要把整个大响应体 log 进去。

---

## 5. 入参是怎么来的（三种调用姿势）

同一个 `POST|GET /api/user-script/{script_id}/run`（`POST /api/user-script/{script_id}` 是等价别名）
支持三种调用方式，**脚本不用关心调用方用的是哪一种**：

| 姿势 | 例子 | `ctx.input` | 备注 |
|------|------|-------------|------|
| ① 直接 POST 业务 JSON | `curl -X POST .../demo.api/run -d '{"car":"AGV-07"}' -H 'Content-Type: application/json'` | `{ car = "AGV-07" }` | **推荐** |
| ② 只用 query | `curl ".../demo.api/run?car=AGV-07&step=12"` | `{ car = "AGV-07", step = "12" }` | **值都是字符串** |
| ③ 老式包装体 | `-d '{"payload":{"car":"AGV-07"},"code":"..."}'` | `{ car = "AGV-07" }` | 前端调试在用；`code` 会临时覆盖正文并跳过"已禁用"检查 |

合并规则（务必记住）：

```
ctx.input = { ...query, ...body对象 }      -- body 里的同名字段覆盖 query
```

* 若 body 是 **数组或标量**（不是对象）：`ctx.input` **只有 query**，数组本身只出现在 `ctx.body`。
* 若 body 不是合法 JSON（表单、纯文本）：原样作为字符串给 `ctx.body`，`ctx.input` 只有 query。
* query 里同名参数取**第一个**值（`setdefault` 语义），`ctx.query.k` 永远是字符串，数字要 `tonumber`。
* body 没有时 `ctx.body` 是 `nil`（JSON `null` 在 Lua 侧统一看成 `nil`）。

因此推荐的入参读取姿势：

```lua
local d = ctx.input or {}                 -- 兜底成表：入参形态变化时脚本也不会崩
local step = tonumber(d.step) or 0        -- query 来的 step 是字符串，统一转换
local verbose = (ctx.query or {}).verbose == "1"
```

> 严谨一点：`ctx.input` 正常情况下**总是表**（没有入参时是空表 `{}`），所以 `ctx.input.car`
> 本身不会报错；**真正可能为 `nil` 的是 `ctx.body`**（没有请求体时）以及业务字段。
> 兜底写法的价值在于：这段脚本被临时执行接口（`POST /api/user-script/run`）用别的 payload 调用时也不会崩。

---

## 6. JSON 语义与坑

`json` 是**纯 Lua 实现**（沙箱里没有 C 库），语义与"标准 JSON"有几处关键差别：

### 6.1 `json.null` 哨兵

```lua
local v = json.decode('{"a": null}')
log(type(v.a))            -- "table"（不是 "nil"！）
log(v.a == json.null)     -- true
log(tostring(v.a))        -- "json.null"
```

* 判断"字段缺失"用 `v.a == nil`；判断"明确是 null"用 `v.a == json.null`；
  两者都要当"空"处理时：`v.a == nil or v.a == json.null`（见 [§12.4](#124-校验--字段映射纯处理不联网)）。
* 想让返回值里出现 `null`：显式写 `json.null`。**写 `nil` 是没用的 —— 字段会直接消失**：

```lua
return { a = nil, b = json.null }   -- 编码结果：{"b":null}
```

### 6.2 表 → 数组 还是 对象

判定规则：**所有键都是 ≥1 的整数，且键个数 == 最大下标**（即"1..n 连续"）才编码成数组，否则编码成对象。

| Lua 值 | JSON |
|--------|------|
| `{}` | `{}` ⚠️ 空表编码成**空对象**，不是 `[]` |
| `{1,2,3}` | `[1,2,3]` |
| `{ [1]="a", [3]="c" }` | `{"1":"a","3":"c"}` ⚠️ 有洞 → 变成对象，键变字符串 |
| `{ [0]="a", [1]="b" }` | `{"0":"a","1":"b"}` ⚠️ 下标从 0 开始 → 不是数组 |
| `{ a = 1 }` | `{"a":1}` |

**推论（很重要）**：本实现**无法表达空数组 `[]`**。要返回"空列表"，请改成
`{ count = 0 }` 或干脆省略该字段，让调用方容忍字段缺失：

```lua
local items = {}
for _, row in ipairs(rows) do
  if row.enabled then items[#items + 1] = row end
end
return { ok = true, count = #items, items = #items > 0 and items or nil }  -- 空时字段消失
```

同理，**不要用 `table.remove` 制造空洞**后还指望它编码成数组。

### 6.3 其他编码细节

* **对象键排序输出**：按键的字符串形式排序，所以同样的数据每次编码结果一致（方便比对/缓存）。
* 键只能是**字符串或数字**；布尔/表做键会报错 `表键必须是字符串或数字`。
* 非有限数字（`0/0`、`math.huge`）会报错。
* 循环引用会报错（`嵌套超过 64 层`）。
* 整数输出 `%d`，浮点输出 `%.14g`。
* `json.decode` 输入上限 4MB；节点数/嵌套深度超过 `max_nodes`(50000)/`max_depth`(64) 报错。
* `json.encode` 里的 `error()` 会当成**脚本错误**返回（`error_type=lua`），不是"编码失败但继续跑"。

---

## 7. 调用外部 HTTP

沙箱里**唯一**的外部能力就是 `http.*`：真正的网络动作在宿主 Python 进程里做，Lua 侧只是整理参数、
解码结果。所有调用都要过策略（[§16](#16-配置速查)）。

### 7.1 API

```lua
-- 下面这些是签名速查（方括号里是可选项），不是能直接粘贴的代码
-- http.get(url [, opts])            opts: { headers=, params=, timeout_ms= }
-- http.head(url [, opts])
-- http.delete(url [, opts])
-- http.post(url, body [, opts])     body 是 table 时自动 json.encode + Content-Type: application/json
-- http.put(url, body [, opts])
-- http.patch(url, body [, opts])
-- http.request{ url=, method=, headers=, body=, json=, params=, timeout_ms= }   -- 底层接口
-- http.fetch = http.request         -- 前端习惯叫法，等价
```

* `params` 会按 `key=urlencode(value)` 拼进 URL，**并按 key 排序**（顺序稳定，便于复现）。
* `body` 可以是字符串或 table；table 自动序列化（`json` 字段是 `body` 的别名）。
* `headers` 里**不允许**：`host`、`content-length`、`connection`、`transfer-encoding`、`expect`、`upgrade`；
  最多 32 个头，头名/头值不能含换行（防注入）。没给 `User-Agent` 时会用配置里的那个。
* `GET` / `HEAD` **不允许带 body**。
* URL 最多 2048 字符，只允许 http/https，不允许带用户名密码。

### 7.2 返回值（**永远返回 table，绝不抛异常**）

成功：

```lua
-- 成功：local res = http.get(url)
local res = {
  ok = true,
  status = 200,                  -- 4xx/5xx 也算 ok=true（"拿到了应答"就是传输成功）
  headers = { ["content-type"] = "application/json" },
  content_type = "application/json",
  body = "…原始响应文本…",        -- 永远是字符串，可能被截断
  json = { car = "AGV-07" },     -- 仅当响应像 JSON 且解析成功时存在；否则是 nil
  bytes = 1234,
  truncated = false,             -- 超过 max_response_kb 时为 true（body 只剩前面一段）
  url = "…最终 URL（跟随重定向之后）…",
  redirects = 0,
  duration_ms = 137,
}
```

失败：

```lua
-- local res = http.get(url)  —— 失败时也是 table，字段少一些
local res = { ok = false, error = "人能看懂的原因", error_type = "http_timeout", duration_ms = 4001 }
```

**判断成功只看 `ok`**（不要用 `status` 判断 —— 失败的响应里没有 `status`）。
`json` 只在 `content_type` 含 `json` 或 body 首字符是 `{` / `[` 时才有值，其它情况要自己 `json.decode(res.body)`。

### 7.3 错误类型与建议处理

| `error_type` | 含义 | 脚本该怎么返回 |
|--------------|------|----------------|
| `http_disabled` | 配置里 `[user_script.http] enabled = false` | 502，并提示运维开开关 |
| `http_blocked` | 命中 `blocked_hosts`，或目标是内网/回环但 `allow_private_hosts=false` | 502 |
| `http_dns` | 域名解析失败 | 502 |
| `http_timeout` | 超时（单次超时 = min(脚本要求, 策略 4000ms, **脚本剩余总预算**)） | **504** |
| `http_network` | 连接被拒 / TLS 失败 / 连接中断等 | 502 |
| `http_url` / `http_scheme` / `http_method` | URL 写错、协议不是 http(s)、method 不支持 | **500**（这是脚本的 bug） |
| `http_badarg` | 参数类型不对（headers 不是 table、GET 带 body 等） | 500（脚本的 bug） |
| `http_size` | 请求体超过 `max_request_kb` | 500 |
| `http_busy` | 本次执行的外部请求次数用完了（默认 6 次） | 429 |
| `http_unavailable` | HTTP 桥没装好（宿主问题） | 502 |
| `http_internal` | 宿主内部异常 | 502 |

**上游 4xx/5xx 不是错误**：`ok=true` 且 `status=404`。要按业务处理：

```lua
local up = http.get(url)
if not up.ok then
  return { ok = false, stage = "upstream", error = up.error, error_type = up.error_type, __status = 502 }
end
if up.status == 404 then
  return { ok = false, error = "上游没有这个车", __status = 404 }    -- 把上游语义透传给调用方
end
if up.status >= 500 then
  return { ok = false, error = "上游故障", upstream_status = up.status, __status = 502 }
end
```

### 7.4 超时与预算（最容易翻车的地方）

* 单次请求的连接/读取超时 = `min(脚本传的 timeout_ms, [user_script.http].timeout_ms, 脚本剩余总时间)`，
  最小 100ms。
* **总预算**：`[user_script] timeout_ms`（默认 8000ms）覆盖整次执行，包括所有外网调用。
  **每次 http 调用前宿主都会检查剩余时间，不够 100ms 就直接返回 `http_timeout`。**
* 所以：**一次执行里做 N 个同步外部调用时，把每次的 `timeout_ms` 设成 `总预算 / (N+1)` 量级**。
  例：总预算 8000ms，两个上游调用 → 每次 `timeout_ms = 3000`，留 2s 给解析与返回。
* 默认**禁止内网/回环地址**（SSRF 防护），每一跳重定向都会重新检查。要调内网接口：
  `[user_script.http] allow_private_hosts = true`（同时建议用 `allowed_hosts` 收紧范围）。

---

## 8. 把脚本当 API 端点

### 8.1 响应信封（调用方实际收到的 JSON）

```json
{
  "success": true,
  "ok": true,
  "script_id": "demo.api",
  "version": 3,
  "duration_ms": 620,
  "worker_ms": 585,
  "result": { "…脚本的返回值…" : true },
  "logs": ["开始处理…", "上游: 200 …"],
  "runtime": { "lua": "Lua", "lua_version": [5, 5], "lupa": "2.8" },
  "http_status": 400
}
```

* 失败时 `ok=false`，并有 `error` / `error_type` /（非 lua/syntax/memory 时）`traceback`，**没有 `result`**。
* `http_status` 只在脚本显式指定了 `__status` 时出现。
* **脚本的返回值一定在 `result` 里**，调用方要按 `json.result.xxx` 取（这是本平台的固定信封，
  不是"脚本返回什么就是什么"）。若你的调用方期望裸数据，让它在 `result` 里取即可。

### 8.2 `__status` / `__headers`

脚本返回的 table 里可以带两个**保留键**，它们会被摘掉、不会出现在 `result` 里：

```lua
return {
  ok = false, error = "缺少 car 参数",
  __status = 400,                                  -- HTTP 状态码
  __headers = { ["X-Service"] = "agv-status" },    -- 自定义响应头
}
```

规则：

| 项 | 限制 |
|----|------|
| `__status` | 必须是 100–599 的整数；`true`/`false`、字符串、越界值**静默忽略**（退回 200） |
| `__headers` | 最多 **16** 个；头名/头值不能含 `\r` `\n` `:`；值超过 **1024** 字符会被丢掉 |
| 被禁的响应头 | `content-length`、`transfer-encoding`、`connection`、`keep-alive`、`upgrade`（由服务器自己管） |

**状态码语义建议**（照抄这套，调用方会很好过）：

| 场景 | 状态码 |
|------|--------|
| 正常返回 | 200（不写 `__status` 就是 200） |
| 入参缺失/格式错 | 400 |
| 上游返回 404（资源不存在） | 404 |
| 上游 5xx / 连不上 / 配置不允许 | 502 |
| 上游超时 | 504 |
| 本次执行的外部请求配额用完 | 429 |
| 脚本自身 bug（不该出现） | 500 |

> ⚠️ **不写 `__status` 时，哪怕脚本 `error()` 报错，HTTP 也是 200**（脚本失败被当成"业务结果"，
> 信封里 `ok=false`）。所以**对外提供接口的脚本一定要显式写 `__status`**。

### 8.3 调用方怎么调

```bash
# 本机（默认就允许）
curl "http://127.0.0.1:8000/api/user-script/demo.api/run?car=AGV-07&step=12"
curl -X POST http://127.0.0.1:8000/api/user-script/demo.api/run \
     -H "Content-Type: application/json" -d '{"car":"AGV-07","step":12}'
curl -X POST http://127.0.0.1:8000/api/user-script/demo.api -d '{"car":"AGV-07"}'    # 等价别名

# 跨机（需要 config.toml: allow_remote = true + api_key = "..."）
curl -H "X-API-Key: <那串 key>" \
     "http://<服务器IP>:8000/api/user-script/demo.api/run?car=AGV-07"
```

访问闸门（`backend/api/user_script.py` 的 `evaluate_access`）：

1. `[user_script] enabled = false` → 一律拒绝（403）；
2. 来源是本机（loopback）**且没有** `X-Forwarded-For`/`X-Real-IP`/`Forwarded` → 放行；
3. 否则必须有 `allow_remote = true` **且**配了 `api_key`，且请求头 `X-API-Key` 用常数时间比较匹配 → 否则 403/401。

> 注意第 2 条：**带了 `X-Forwarded-For` 的请求一律按"远程"处理** —— 所以挂在同机反代后面时，
> 也必须开 `allow_remote` + `api_key`。
> 脚本**看不到** `X-API-Key`（白名单），鉴权只发生在接口层。

---

## 9. 可用标准库白名单

沙箱构造方式是「先清空所有全局，再装回 prelude 提供的项」，因此**除了下表以外的一切都不存在**。

| 类别 | 可用的 |
|------|--------|
| 基础函数 | `assert` `error` `type` `tostring` `tonumber` `select` `next` `pairs` `ipairs` `pcall` `xpcall` `rawequal` `rawget` `rawset` `rawlen` `setmetatable` `getmetatable` |
| `coroutine` | 完整协程库（但主流程不能 `yield`） |
| `string` | 标准库，**`string.dump` 被移除** |
| `table` | `concat` `insert` `move` `pack` `remove` `sort` `unpack` |
| `math` | 标准库（含 `math.floor` / `tointeger` / `type` / `huge` / `random`…） |
| `utf8` | `char` `charpattern` `codepoint` `codes` `len` `offset`（处理中文很有用） |
| `os` | **只有** `time` `date` `clock` `difftime` |
| 平台注入 | `json` `http` `log` `print` `console` `input` `output` `_G` `_VERSION` |

**明确不可用**（写了就报 nil 索引错误，或直接被沙箱自检拦掉）：

`os.execute` `os.getenv` `os.remove` `os.rename` `os.exit` `io` `io.open` `package` `require`
`load` `loadstring` `loadfile` `dofile` `debug` `collectgarbage` `string.dump` `warn` `newproxy`
`jit` `ffi` `python`（宿主原生对象）

**能做的替代**：

* 读时间是 `os.time()` / `os.date("%Y-%m-%d %H:%M:%S")`，不是 `os.getenv`；
* 要打日志用 `log(...)` / `print(...)` / `console.log(...)`（都进日志缓冲，不会污染 worker stdout）；
* 要"读文件/查数据库/写数据库" → **不存在**。必须让上游提供一个 HTTP 接口，用 `http.*` 调它。
* 需要排序/去重/分组：用 `table.sort` + 自己写比较函数（`pairs` 顺序不确定，要稳定输出请显式排序）。

---

## 10. 错误类型与调试

### 10.1 信封里的 `error_type` 全表

| `error_type` | 触发条件 | 谁的问题 |
|--------------|----------|----------|
| `script` | 脚本为空，或超过 `max_script_kb`（128KB） | 脚本 |
| `payload` | 请求体无法序列化成 JSON，或超过 `max_payload_kb`（256KB） | 调用方 |
| `syntax` | Lua 语法错误（保存时 `validate_code=true` 就已经拦下） | 脚本 |
| `lua` | 运行时错误：`error()` / `assert` 失败 / 类型错误（如 `attempt to index a nil value`） | 脚本 |
| `memory` | Lua 内存超过 `max_memory_mb`（64MB） | 脚本 |
| `result` | 结果不是合法 JSON / 超过 `max_result_kb`（256KB）/ 含非 UTF-8 字节 | 脚本 |
| `timeout` | 墙钟超时，worker 已被 kill | 脚本（多半是死循环/调用太多） |
| `crash` | worker 异常退出且没吐结果 | 宿主/环境 |
| `spawn` | worker 起不来（python 或 `main.py` 不可用） | 环境 |
| `busy` | 并发数已满且排队超过 `timeout_ms + 5s` | 容量 |
| `internal` | 宿主内部异常 | 宿主 |

（`http_*` 系列**不会**出现在信封顶层 —— 它们在 `http` 返回值的 `error_type` 里，
要靠脚本自己搬到结果里，见 §12.2。）

### 10.2 调试手法

1. **`log()` 中间结果**：日志随信封返回（`logs` 数组），前端执行面板也会显示。
   带上关键状态，别把整个响应体 log 进去（200 行上限、单行 2000 字符）。
2. **`pcall` 兜住可能失败的一段**，把失败原因带回结果，而不是让整脚本挂掉：
   ```lua
   local ok, res = pcall(json.decode, raw)
   if not ok then return { ok = false, error = "上游返回的不是 JSON", raw_head = raw:sub(1, 200) } end
   ```
3. **`error(msg, 0)`**：第二参数给 0，错误信息不带 `script:行号:` 前缀，报错更干净。
   反之，行号定位问题时就别给 0。
4. **`?verbose=1` 这类调试开关**：用 `ctx.query.verbose == "1"` 控制是否把上游原始 body
   一起返回（正式调用不带这个参数就没有额外噪音）。
5. **先用临时执行试**：`POST /api/user-script/run`（`{code, payload}`，不落库）或
   `POST /api/user-script/{id}/check`（只查语法）。跑通了再保存。

---

## 11. 资源预算

| 项目 | 默认值 | 配置项 | 脚本侧注意 |
|------|--------|--------|------------|
| 总墙钟超时 | 8000ms | `[user_script] timeout_ms` | 所有外部调用之和；超时直接杀进程 |
| Lua 内存 | 64MB | `max_memory_mb` | 别把大数组全读进内存再处理 |
| 单次请求超时 | 4000ms | `[user_script.http] timeout_ms` | 会被总预算进一步压缩 |
| 外部请求次数 | 6 次/执行 | `max_requests_per_run` | 循环里调 http 很容易用光 |
| 响应体上限 | 512KB（超出截断） | `max_response_kb` | `truncated=true` 时别当完整数据处理 |
| 请求体上限 | 256KB | `max_request_kb` | 批量的数据要分页 |
| 重定向 | 3 跳 | `max_redirects` | 每跳都重新过策略 |
| 结果上限 | 256KB | `max_result_kb` | 超了 `error_type=result`，要分页/裁剪字段 |
| 脚本体积 | 128KB | `max_script_kb` | — |
| 日志行数 | 200 行 | `max_log_lines` | — |
| 并发执行 | 4 | `max_concurrency` | 超了 `busy`（HTTP 仍 200） |
| 结果嵌套/节点 | 64 层 / 50000 | `max_depth` / `max_nodes` | 也约束 `json.encode`/`decode` |

**经验值**：一次执行里做 2 次外网调用（每次 3s 上限）在默认 8000ms 下是安全的；
做 3 次以上就要么提高 `timeout_ms`，要么改成"上游一次批量取回"。

---

## 12. 可复制的脚本模式库

> 这四种模式覆盖了绝大多数需求。**直接改造，不要从零发明结构。**

### 12.1 回显 / 透传（最小骨架）

```lua
-- 用途：联调、验证链路、做"字段改名"的薄中间层
function handle(ctx)
  local data = ctx.input or {}
  log("收到:", json.encode(data))
  return { ok = true, echo = data, at = os.date("%Y-%m-%d %H:%M:%S") }
end
```

### 12.2 脚本即 API 端点（校验 → 上游 → 转换 → 对外）

```lua
-- 用途：给别的服务提供一个"稳定的业务接口"，内部去调现场接口并整理结构
local UPSTREAM   = "http://10.0.0.9:8080/api/agv/status"   -- 内网要开 allow_private_hosts
local TIMEOUT_MS = 3000
local SERVICE    = "agv-status"

function handle(ctx)
  -- 1) 入参校验：给调用方明确的 400
  local d = ctx.input or {}
  local car = d.car
  if car == nil or car == "" then
    return { ok = false, service = SERVICE, error = "缺少 car 参数",
             usage = "GET /api/user-script/demo.api/run?car=AGV-07", __status = 400 }
  end
  local step = tonumber(d.step) or 0

  -- 2) 取上游
  local up = http.get(UPSTREAM, { params = { car = car, step = tostring(step) }, timeout_ms = TIMEOUT_MS })
  if not up.ok then
    log("上游失败:", up.error_type, up.error)
    local code = (up.error_type == "http_timeout") and 504 or 502
    return { ok = false, service = SERVICE, error = "上游接口不可用",
             detail = up.error, error_type = up.error_type, __status = code }
  end
  if up.status >= 400 then
    return { ok = false, service = SERVICE, error = "上游返回错误",
             upstream_status = up.status, body_head = up.body:sub(1, 200),
             __status = (up.status == 404) and 404 or 502 }
  end

  -- 3) 转换：**只暴露你需要调用方依赖的字段**（上游字段改了你还能在这里兜住）
  local body = up.json or {}
  local result = {
    ok = true, service = SERVICE,
    data = {
      car = body.car or car,
      step = tonumber(body.step) or step,
      status = body.status or "unknown",
      source = "agvmon/user-script",
      generated_at = os.date("%Y-%m-%d %H:%M:%S"),
    },
    upstream = { status = up.status, url = up.url },
    caller = { method = ctx.request.method, ip = ctx.request.ip },
  }
  if (ctx.query or {}).verbose == "1" then
    result.verbose = { upstream_body = up.body }        -- 调试开关
  end
  log("处理", car, "step=" .. step, "->", result.data.status)
  return result
end
```

### 12.3 中转 / 转发（取数 → 处理 → POST 下游）

```lua
-- 用途：把现场数据加工后推给 MES/WMS/webhook（"中间层"）
local UPSTREAM   = "http://10.0.0.9:8080/api/task"
local DOWNSTREAM = "http://10.0.0.20:9000/hook"     -- 留空 = 只处理不转发
local TIMEOUT_MS = 2500                              -- 两次调用 → 预算对半分

function handle(ctx)
  local d = ctx.input or {}
  local task_id = d.task_id or d.car or "unknown"

  local up = http.get(UPSTREAM, { params = { task_id = task_id }, timeout_ms = TIMEOUT_MS })
  if not up.ok then
    return { ok = false, stage = "upstream", error = up.error, error_type = up.error_type, __status = 502 }
  end

  local payload = {
    task_id = task_id,
    car = d.car,
    steps = tonumber(d.step) or 0,
    source = "agvmon/user-script",
    upstream_status = up.status,
    handled_at = os.date("%Y-%m-%d %H:%M:%S"),
  }

  if DOWNSTREAM == "" then
    return { ok = true, relayed = false, data = payload }
  end

  local down = http.post(DOWNSTREAM, payload, { timeout_ms = TIMEOUT_MS })   -- table 自动 JSON 化
  if not down.ok then
    return { ok = false, stage = "downstream", error = down.error,
             error_type = down.error_type, data = payload, __status = 502 }
  end
  log("已转发:", down.status)
  return { ok = true, relayed = down.status >= 200 and down.status < 300,
           downstream = { status = down.status, url = down.url }, data = payload }
end
```

> **中转语义注意**：本平台不做自动重试，也**不保证幂等**。脚本里若"下游失败要重试"，
> 必须在 payload 里带一个业务唯一键（如 `task_id`）让下游去重，并且最多重试 1 次（请求次数预算有限）。

### 12.4 校验 + 字段映射（纯处理，不联网）

```lua
local REQUIRED = { "car", "step" }

local function is_blank(v)
  return v == nil or v == json.null or (type(v) == "string" and v:match("^%s*$") ~= nil)
end

function handle(ctx)
  local d = ctx.input or {}
  local errors = {}

  for _, key in ipairs(REQUIRED) do
    if is_blank(d[key]) then errors[#errors + 1] = key .. " 不能为空" end
  end
  if not is_blank(d.step) and type(d.step) ~= "number" then
    errors[#errors + 1] = "step 必须是数字，实际是 " .. type(d.step)
  end

  if #errors > 0 then
    log("校验失败:", table.concat(errors, "；"))
    return { ok = false, errors = errors, __status = 400 }
  end

  local pos = d.pos or {}
  return { ok = true, normalized = {
    robot = d.car,                                  -- 上报叫 car，规范字段叫 robot
    step = math.floor(d.step),
    x = math.floor(tonumber(pos.x) or 0),
    y = math.floor(tonumber(pos.y) or 0),
    theta = math.floor(tonumber(pos.theta) or 0),
    reported_at = d.ts or os.time(),
  } }
end
```

### 12.5 列表分页 + 裁剪（避免超结果上限）

```lua
-- 用途：上游返回一大堆数据，只回前 N 条给调用方（防止触发 max_result_kb）
local MAX_ITEMS = 50

function handle(ctx)
  local d = ctx.input or {}
  local limit = math.min(tonumber(d.limit) or MAX_ITEMS, MAX_ITEMS)

  local up = http.get("http://10.0.0.9:8080/api/agv/list", { timeout_ms = 3000 })
  if not up.ok then return { ok = false, error = up.error, __status = 502 } end

  local items, total = {}, 0
  for _, row in ipairs((up.json or {}).list or {}) do
    total = total + 1
    if #items < limit then
      items[#items + 1] = { car = row.car, status = row.status, battery = tonumber(row.battery) }
    end
  end
  return { ok = true, total = total, count = #items,
           truncated = total > #items,
           items = #items > 0 and items or nil }        -- 空列表：字段消失（见 §6.2）
end
```

---

## 13. 反模式清单

| ❌ 不要这样 | ✅ 应该这样 | 原因 |
|-------------|-------------|------|
| `ctx.input.car` 直接用 | `local d = ctx.input or {}` 再取 | `ctx.input` 本身总是表（不会报错），但 `ctx.body` 可能是 `nil`；统一兜底后同一段脚本换个入口调用也不会崩 |
| 用 `nil` 表示 JSON null | 用 `json.null` | 写 nil 等于删字段；数组里 nil 会变 null 但对象里直接消失 |
| 指望 `{}` 变成 `[]` | 用 `count = 0` 或省略字段 | 纯 Lua 编码器无法表达空数组 |
| `for i,v in pairs(t)` 后直接输出 | 先 `table.sort` 或按键取值 | `pairs` 顺序不确定，输出不可复现 |
| 循环里对每条数据调一次 `http.*` | 让上游支持批量，或最多 6 次内搞定 | 6 次/执行就报 `http_busy` |
| 以为 `error()` 会返回 500 | 显式 `__status = 400/502/...` | 脚本报错默认仍是 HTTP 200 |
| 用 `status` 判断 `http` 成功 | 用 `ok` | 失败结果里根本没有 `status` 字段 |
| 把 `os.getenv` / `require` / `io.open` 当可用 | 没有这些；需要外部数据就走 `http` | 沙箱白名单 |
| 自己拼 query 字符串 | 用 `http.get(url, { params = {...} })` | 自动 urlencode，中文/特殊字符不会出错 |
| 在脚本里写死 `api_key`、口令、内网 IP | 放配置/环境侧；脚本只写业务 | 脚本正文会随接口返回（`GET /{id}`）、进日志、进备份 |
| 一次返回几百 KB / 上万条 | 分页 + 只返回必要字段 | `max_result_kb` = 256KB，超了直接失败 |
| 依赖全局变量在多次执行间保留 | 每次执行都是全新进程 | 无跨请求状态 |
| 把自定义请求头当业务入参 | 用 body / query；追踪用 `x-request-id` | 请求头白名单只有 10 个，其它看不到 |

---

## 14. 交付前自检清单

写完后逐条打勾（**AI 生成脚本时必须自己过一遍**）：

- [ ] 有 `handle(ctx)`，里面第一行就 `local d = ctx.input or {}`
- [ ] 必填参数缺失时返回 `__status = 400` + 人能看懂的中文 `error`
- [ ] 所有 `http.*` 调用都检查了 `if not up.ok then ...`，并按错误类型给了 502/504/429
- [ ] 所有 `http.*` 调用都传了 `timeout_ms`，且**总和不超出** `[user_script] timeout_ms`
- [ ] 外部调用次数 ≤ 6（默认预算）
- [ ] 上游字段都用 `(up.json or {})` / `tonumber()` / `or 默认值` 兜过
- [ ] 返回值是 table（不是字符串/数字/函数），键都是字符串，没有 `nil` 依赖
- [ ] 数组是"1..n 连续"的（`items[#items+1] = x`），没有空洞、没有下游标 0
- [ ] 要在结果里表达 null 的地方用了 `json.null`
- [ ] 结果体积粗估 < 256KB（必要时分页/裁剪）
- [ ] 用 `log()` 打了关键路径（不含敏感信息、不含整个大 body）
- [ ] 对外服务的脚本给了 `__status` 与必要的 `__headers`
- [ ] **没有**用 `os.execute` / `io` / `require` / `load` / `debug` / `package`
- [ ] 没有把口令、`api_key`、内网地址以外的敏感信息写进正文
- [ ] 如果访问内网：已提示需要 `allow_private_hosts = true`（或在结果/日志里给出该提示）
- [ ] 用 `POST /api/user-script/run`（临时执行）实际跑过一次，`logs` 符合预期

---

## 15. 通过 HTTP 管理脚本

脚本库落在 **`<应用根目录>/lua_script/<script_id>.lua`**（**正文以文件为准**），元信息与执行审计落 SQLite。
`script_id` 规则：`^[A-Za-z0-9_.\-]{1,64}$`（字母数字与 `_ . -`，最长 64）。正文覆盖/删除前会自动留一份历史（保留 5 份）。
`lua_script/` 是运行期数据目录（`.gitignore` 忽略），**仓库里不带示例脚本** —— 示例都在前端页面的「插入示例」里。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/user-script` | 列出脚本（带 `last_status` / `run_count` 等） |
| `POST` | `/api/user-script` | 新建。`{script_id, code, name?, description?, enabled?, validate_code?}`；`validate_code=true` 会先做语法检查 |
| `GET` | `/api/user-script/{id}` | 取脚本（含正文与版本号） |
| `PUT` | `/api/user-script/{id}` | 改正文/名称/启用状态（改正文会递增 `version`） |
| `DELETE` | `/api/user-script/{id}` | 删除（留备份） |
| `POST` | `/api/user-script/{id}/check` | **只查语法不执行**；可带 `{code}` 检查未保存的草稿 |
| `POST`/`GET` | `/api/user-script/{id}/run` | **执行**（= 脚本作为 API 端点的主入口） |
| `POST` | `/api/user-script/{id}` | 与 `/run` 等价的别名 |
| `GET` | `/api/user-script/{id}/runs` | 该脚本的执行流水（`?limit=` 1–500） |
| `POST` | `/api/user-script/run` | 临时执行一段代码（不落库）：`{code, payload, script_id?}` |
| `GET` | `/api/user-script/runtime` | 运行时信息 + 端到端自检 + 生效配置（`api_key` 只回 `api_key_set` 布尔值） |

> 若脚本正文在磁盘上被外部编辑（编辑器直接改 `.lua`），**下次执行会自动生效**（文件优先），
> 不需要走 PUT。

---

## 16. 配置速查

```toml
[user_script]
enabled = true
allow_remote = false       # 别的机器/服务要调用必须开，并且配 api_key
api_key = ""               # 远程调用方带请求头 X-API-Key: <这串>
timeout_ms = 8000          # 整次执行的墙钟超时（也是死循环能烧 CPU 的窗口，别设太大）
max_memory_mb = 64         # Lua 分配器硬上限
max_payload_kb = 256       # 入参上限
max_script_kb = 128        # 脚本正文上限
max_result_kb = 256        # 返回值上限
max_log_lines = 200        # 日志行数上限
max_concurrency = 4        # 同时执行数
max_depth = 64             # JSON 嵌套深度上限
max_nodes = 50000          # JSON 节点数上限

[user_script.http]
enabled = true             # 关掉后所有调用返回 error_type=http_disabled
allowed_hosts = []         # 白名单，空 = 任意主机；支持 "*.example.com"
blocked_hosts = []         # 黑名单，优先级高于白名单
allow_private_hosts = false# 内网/回环地址默认禁止（防 SSRF）；调内网接口要改 true
timeout_ms = 4000          # 单次请求超时（还会被 [user_script] timeout_ms 压缩）
max_request_kb = 256       # 请求体上限
max_response_kb = 512      # 响应体上限（超出截断，truncated = true）
max_requests_per_run = 6   # 单次执行最多发几次请求
max_redirects = 3          # 最多跟随几次重定向（每跳重新过策略）
user_agent = "agvmon-user-script/1.0"
```

**给脚本作者的配置相关提醒**（写脚本时如果发现"跑不通"，先怀疑这几条）：

* 调内网/`127.0.0.1` 的接口 → 必须 `allow_private_hosts = true`；
* 调公网但配了 `allowed_hosts` → 目标域名必须在白名单里（或白名单留空）；
* 上游慢 → 确认 `[user_script.http].timeout_ms` 与 `[user_script] timeout_ms` 都够；
* 别的服务调不通 → `allow_remote = true` + `api_key`，调用方带 `X-API-Key`；
* 顺手提示：调用方拿到 403 时，响应体里会直接写明该改哪个配置项（照抄提示即可）。

---

## 附：一句话总结给 AI 的提示词

> 你在为 agvmon 平台写 Lua 用户脚本：沙箱里只有 `json`/`http`/`log` 与纯 Lua 标准库（`os` 只有时间函数）；
> 入口是 `handle(ctx)`，`ctx.input` 是合并后的入参（query 的值都是字符串），返回值即响应体内容；
> 调外部接口一律用 `http.get/post(..., { timeout_ms = ... })` 并检查 `ok`；要当 API 端点就给 `__status`/`__headers`；
> 结果 ≤256KB、外部调用 ≤6 次、总耗时 ≤8s；JSON null 用 `json.null`，空数组无法表达（用 `count=0`）。
> 详细规则见 `LUA_SCRIPT_GUIDE.md`。
