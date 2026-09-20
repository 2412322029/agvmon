/**
 * 用户脚本示例。点「插入示例」就能灌进编辑器直接跑。
 *
 * 第一个是默认模板（新建脚本时的初始内容），第二个是"调外部 API → 处理 → 中转"的
 * 完整例子 —— 它在现场没有外网时也能用内置模拟数据跑通链路。
 */

/** 基础回显：脚本约定的最小骨架，也是新建脚本的初始内容 */
const ECHO = `-- 用户脚本：处理传入的请求数据
-- ctx.input  请求体（JSON 解码后的 table）
-- ctx.json   JSON 编解码
-- ctx.log    写执行日志（print/log/console.log 同效）
-- 返回值即响应内容

function handle(ctx)
  local data = ctx.input
  log("收到数据:", ctx.json.encode(data))

  return {
    ok = true,
    car = data.car,
    ts = os.time(),
  }
end
`

/** 调用外部 API → 处理 → 中转（真调接口，不带模拟数据） */
const RELAY = `-- 调用外部 API → 处理 → 中转（典型"中间层"脚本）
--
-- 流程：
--   1. 把请求数据拼成查询串，调外部接口拿数据（GET，响应是 JSON 时自动解码）；
--   2. 按现场需要的结构重新组装；
--   3. 把组装结果 POST 给下游系统 —— 这一步就是"中转"；
--   4. 把两次调用的状态、以及下游回显的内容一起返回，方便确认"下游真的收到了什么"。
--
-- 怎么改成你自己的：把 UPSTREAM / DOWNSTREAM 换成 MES / WMS / 你自己的 webhook 地址。
-- 默认地址是公开的 echo 服务（它会把收到的参数原样回显），所以不用任何模拟数据就能
-- 看到完整链路；只想处理不转发的话，把 DOWNSTREAM 留空即可。
--
-- 两个注意点：
--   * 脚本里两次外网调用，[user_script] 的 timeout_ms 要留够（默认 8000ms）；
--   * 访问内网地址需要 [user_script.http] allow_private_hosts = true，
--     公网地址要么留空 allowed_hosts，要么把主机加进去。

local UPSTREAM   = "https://postman-echo.com/get"    -- 上游：换成你的接口
local DOWNSTREAM = "https://postman-echo.com/post"   -- 下游 webhook：留空 = 只处理不中转
local TIMEOUT_MS = 4000

function handle(ctx)
  local data = ctx.input or {}
  local task_id = data.task_id or data.car or "unknown"
  log("开始处理任务:", task_id)

  -- 1) 取上游数据：请求数据顺手当查询参数带过去
  local up = http.get(UPSTREAM, {
    params = {
      task_id = task_id,
      car = data.car or "",
      step = tostring(data.step or 0),
    },
    timeout_ms = TIMEOUT_MS,
  })
  if not up.ok then
    log("上游调用失败:", up.error)
    return {
      ok = false, stage = "upstream", error = up.error, error_type = up.error_type,
      hint = "内网地址要开 [user_script.http] allow_private_hosts；公网地址要么留空 allowed_hosts，要么加进白名单",
    }
  end
  log("上游:", up.status, up.url)

  -- 2) 处理：echo 类服务会把收到的参数放在 args 里，真实接口按它的字段名取就行
  local body = up.json or {}
  local received = body.args or {}
  local payload = {
    task_id = received.task_id or task_id,
    car = received.car or data.car,
    steps = tonumber(received.step) or 0,
    source = "agvmon/user-script",
    upstream_status = up.status,
    handled_at = os.date("%Y-%m-%d %H:%M:%S"),
  }

  -- 3) 中转：table 会自动 JSON 序列化并带上 Content-Type
  if DOWNSTREAM == "" then
    log("未配置下游地址，只处理不转发")
    return { ok = true, relayed = false, data = payload, upstream = { status = up.status } }
  end

  local down = http.post(DOWNSTREAM, payload, { timeout_ms = TIMEOUT_MS })
  if not down.ok then
    log("下游转发失败:", down.error)
    return {
      ok = false, stage = "downstream", error = down.error, error_type = down.error_type,
      data = payload,
    }
  end
  log("已转发给下游:", down.status)

  -- 4) 下游回显（echo 服务会把收到的 body 放回 data 字段）——直接看它就知道中转对不对
  local echoed = down.json and down.json.data or nil

  return {
    ok = true,
    relayed = down.status >= 200 and down.status < 300,
    upstream = { status = up.status, url = up.url },
    downstream = { status = down.status, url = down.url, echoed = echoed },
    data = payload,
  }
end
`

/** 脚本即 API 端点：访问上游 API → 转换数据 → 给其他服务当接口用 */
const API_ENDPOINT = `-- 脚本即 API 端点：别的服务调这个脚本，它去上游取数、转换后返回
--
-- 调用方（其他服务）怎么用 —— 三种都行，路径里的 demo.api 就是脚本 ID：
--   curl "http://<本机IP>:8000/api/user-script/demo.api/run?car=AGV-07"
--   curl -X POST http://<本机IP>:8000/api/user-script/demo.api/run \\
--        -H "Content-Type: application/json" -d '{"car":"AGV-07","step":12}'
--   curl -X POST http://<本机IP>:8000/api/user-script/demo.api -d '{"car":"AGV-07"}'   # 别名，少一层路径
--
-- 默认只允许本机调用；要让别的机器/服务调用，去 config.toml 打开：
--   [user_script] allow_remote = true
--                 api_key = "换成一串足够长的随机串"
-- 然后调用方带上请求头 X-API-Key: <那串 key>。
--
-- 脚本能拿到的请求信息：
--   ctx.input     入参（query 与 body 已经在宿主侧合并好，同名字段以 body 为准）
--   ctx.query     query 参数（值都是字符串，数字要 tonumber）
--   ctx.body      原始请求体（JSON 解析后的对象/数组/字符串；没有就是 nil）
--   ctx.request   { method, path, ip, headers, content_type }
-- 返回值就是响应体；另外可以用 __status 指定 HTTP 状态码、__headers 指定响应头
-- （这两个键不会出现在响应体里）。

local UPSTREAM   = "https://postman-echo.com/get"   -- 换成你的 WMS / MES 接口
local TIMEOUT_MS = 4000
local SERVICE    = "agv-status"

function handle(ctx)
  -- 1) 校验入参：给调用方一个明确的 400，比含糊的 200 好排查
  local d = ctx.input or {}
  local car = d.car
  if car == nil or car == "" then
    return {
      ok = false, service = SERVICE, error = "缺少 car 参数",
      usage = "GET /api/user-script/demo.api/run?car=AGV-07",
      __status = 400,
    }
  end
  local step = tonumber(d.step) or 0             -- query 来的值时是字符串，统一转换

  -- 2) 访问上游 API
  local up = http.get(UPSTREAM, {
    params = { car = car, step = tostring(step) },
    timeout_ms = TIMEOUT_MS,
  })
  if not up.ok then
    log("上游失败:", up.error)
    return {
      ok = false, service = SERVICE, error = "上游接口不可用",
      detail = up.error, error_type = up.error_type,
      __status = 502,          -- 网关式语义：上游坏了就是 502
    }
  end

  -- 3) 转换：上游回显的参数 + 本地入参 → 稳定的对外结构
  --    （真实接口按它自己的字段名取，比如 up.json.data.list[1].status）
  local received = (up.json or {}).args or {}
  local received_step = tonumber(received.step) or step
  local result = {
    ok = true,
    service = SERVICE,
    data = {
      car = received.car or car,
      step = received_step,
      status = received_step > 10 and "moving" or "idle",
      source = "agvmon/user-script",
      generated_at = os.date("%Y-%m-%d %H:%M:%S"),
    },
    upstream = { status = up.status, url = up.url },
    caller = {
      method = ctx.request and ctx.request.method,
      ip = ctx.request and ctx.request.ip,
    },
    __headers = { ["X-Service"] = SERVICE },   -- 想给响应加头就这么写
  }
  log("处理", result.data.car, "step=" .. result.data.step, "->", result.data.status)

  -- 调试开关：?verbose=1 时把上游原始响应也带回来（query 参数都是字符串）
  if (ctx.query or {}).verbose == "1" then
    result.verbose = { upstream_body = up.body }
  end

  -- 4) 返回：这就是调用方拿到的 JSON
  return result
end
`

/** 校验 + 字段映射：不联网的纯处理脚本 */
const VALIDATE = `-- 数据校验 + 字段映射：把现场上报的数据整理成规范结构
-- 校验不通过时返回 ok=false 与 errors 列表，调用方据此决定是否重试。

local REQUIRED = { "car", "step" }

local function is_blank(v)
  return v == nil or v == json.null or (type(v) == "string" and v:match("^%s*$") ~= nil)
end

function handle(ctx)
  local d = ctx.input or {}
  local errors = {}

  for _, key in ipairs(REQUIRED) do
    if is_blank(d[key]) then
      errors[#errors + 1] = key .. " 不能为空"
    end
  end

  if not is_blank(d.step) and type(d.step) ~= "number" then
    errors[#errors + 1] = "step 必须是数字，实际是 " .. type(d.step)
  end
  if not is_blank(d.pos) and type(d.pos) ~= "table" then
    errors[#errors + 1] = "pos 必须是对象 {x=, y=, theta=}"
  end

  if #errors > 0 then
    log("校验失败:", table.concat(errors, "；"))
    return { ok = false, errors = errors }
  end

  -- 规范化：统一字段名、补默认值、坐标取整
  local pos = d.pos or {}
  local normalized = {
    robot = d.car,                                  -- 上报叫 car，规范字段叫 robot
    step = math.floor(d.step),
    x = math.floor(pos.x or 0),
    y = math.floor(pos.y or 0),
    theta = math.floor(pos.theta or 0),
    reported_at = d.ts or os.time(),
  }

  log("校验通过:", normalized.robot, normalized.step)
  return { ok = true, normalized = normalized }
end
`

export const EXAMPLES = [
  {
    name: '基础回显（handle 约定）',
    code: ECHO,
  },
  {
    name: '脚本即 API 端点（上游 API → 转换 → 对外提供）',
    code: API_ENDPOINT,
  },
  {
    name: '调用外部 API → 处理 → 中转',
    code: RELAY,
  },
  {
    name: '数据校验 + 字段映射',
    code: VALIDATE,
  },
]

/** 新建脚本时的初始内容 */
export const DEFAULT_TEMPLATE = ECHO

/** 按名字取示例 */
export function exampleByName(name) {
  return EXAMPLES.find((e) => e.name === name) || null
}
