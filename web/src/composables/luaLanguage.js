/**
 * Lua 语言支持：Monarch 语法高亮、智能提示目录、悬浮文档。
 *
 * 这个模块**故意不 import monaco**：全是纯数据 + 纯函数，因此可以直接用 node 跑
 * （web/test_lua_language.mjs），不需要 DOM。monaco 的接线在 luaMonaco.js。
 *
 * `SANDBOX_GLOBALS` 必须与后端沙箱真实暴露的全局严格一致 —— test_user_script.py
 * 里有一条用例会真的起一个 Lua 沙箱、枚举全局表来和这份清单对齐；`ctx` /
 * `handle` 不是全局（前者是入参，后者由脚本自己定义），单列在 EXTRA_NAMES。
 */

export const LUA_LANGUAGE_ID = 'lua'

/** Lua 5.5 关键字 */
export const LUA_KEYWORDS = [
  'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for', 'function',
  'goto', 'if', 'in', 'local', 'nil', 'not', 'or', 'repeat', 'return', 'then',
  'true', 'until', 'while',
]

/** 与 util/lua_sandbox.py 白名单一致的全局 */
export const SANDBOX_GLOBALS = [
  { name: '_G', kind: 'property', detail: '全局表', doc: '沙箱全局表本体，只包含白名单里的东西。' },
  { name: '_VERSION', kind: 'constant', detail: 'Lua 版本', doc: '例如 `"Lua 5.5"`。' },
  { name: 'json', kind: 'property', detail: 'JSON 编解码', doc: '纯 Lua 实现的 JSON：`json.encode(v)` / `json.decode(s)` / `json.null` 哨兵。' },
  { name: 'http', kind: 'property', detail: '外部 HTTP 客户端', doc: '调用外部 API：`http.get(url)` / `http.post(url, body)` / `http.request{...}`。受 config.toml 的 `[user_script.http]` 白名单与超时约束。' },
  { name: 'log', kind: 'function', detail: 'log(...)', doc: '写一行执行日志（多个参数用 Tab 连接），最多保留 `limits.max_log_lines` 行。与 `print` 等价。' },
  { name: 'print', kind: 'function', detail: 'print(...)', doc: '同 `log`：沙箱里的 print 只进日志缓冲，**不会**写到 worker 的 stdout。' },
  { name: 'console', kind: 'property', detail: 'console.log/info/warn/error/debug', doc: '都指向同一个日志函数，写成前端习惯的 `console.log(...)` 也行。' },
  { name: 'input', kind: 'variable', detail: '请求体（table）', doc: '本次请求的 `payload`（JSON 解码后的 table）。字段缺失是 `nil`，JSON null 是 `json.null`。' },
  { name: 'output', kind: 'variable', detail: '结果容器', doc: '可以 `output.xxx = ...` 代替 `return`；脚本没有返回值时用它当结果。' },
  { name: 'assert', kind: 'function', detail: 'assert(v [, msg])', doc: 'v 为假（nil/false）时抛错并中断脚本。' },
  { name: 'error', kind: 'function', detail: 'error(msg [, level])', doc: '抛错。第二参数给 0 时错误信息不带位置前缀，报错更干净。' },
  { name: 'type', kind: 'function', detail: 'type(v)', doc: '返回 `"nil"|"number"|"string"|"boolean"|"table"|"function"`。' },
  { name: 'tostring', kind: 'function', detail: 'tostring(v)', doc: '转字符串；table 会得到 `table: 0x...`，要看内容请用 `json.encode`。' },
  { name: 'tonumber', kind: 'function', detail: 'tonumber(v [, base])', doc: '转数字，失败返回 nil。' },
  { name: 'select', kind: 'function', detail: 'select(n, ...)', doc: '`select("#", ...)` 取可变参数个数。' },
  { name: 'next', kind: 'function', detail: 'next(t [, k])', doc: '手工遍历表。' },
  { name: 'pairs', kind: 'function', detail: 'pairs(t)', doc: '遍历所有键值对（顺序不确定，要稳定输出请自己排序）。' },
  { name: 'ipairs', kind: 'function', detail: 'ipairs(t)', doc: '按下标 1..n 顺序遍历数组部分。' },
  { name: 'pcall', kind: 'function', detail: 'pcall(f, ...) → ok, err', doc: '保护调用：捕获错误而不中断脚本。' },
  { name: 'xpcall', kind: 'function', detail: 'xpcall(f, handler, ...) → ok, ret', doc: '带错误处理函数的保护调用。' },
  { name: 'rawequal', kind: 'function', detail: 'rawequal(a, b)', doc: '不做元方法比较。' },
  { name: 'rawget', kind: 'function', detail: 'rawget(t, k)', doc: '绕过 `__index` 取值。' },
  { name: 'rawset', kind: 'function', detail: 'rawset(t, k, v)', doc: '绕过 `__newindex` 赋值。' },
  { name: 'rawlen', kind: 'function', detail: 'rawlen(v)', doc: '绕过 `__len` 取长度。' },
  { name: 'setmetatable', kind: 'function', detail: 'setmetatable(t, mt)', doc: '设置元表（`__index` / `__tostring` 等）。' },
  { name: 'getmetatable', kind: 'function', detail: 'getmetatable(t)', doc: '取元表；没有元表时返回 nil。' },
  { name: 'coroutine', kind: 'property', detail: '协程库', doc: '标准协程库。主流程本身跑在 Lua 主协程里，脚本自己 `yield` 会报错。' },
  { name: 'string', kind: 'property', detail: '字符串库', doc: 'Lua 标准字符串库（`string.dump` 被移除）。' },
  { name: 'table', kind: 'property', detail: '表库', doc: 'Lua 标准表库。' },
  { name: 'math', kind: 'property', detail: '数学库', doc: 'Lua 标准数学库。' },
  { name: 'utf8', kind: 'property', detail: 'UTF-8 库', doc: 'UTF-8 编解码，处理中文时很有用。' },
  { name: 'os', kind: 'property', detail: '只保留时间函数', doc: '沙箱里的 os **只有** `time` / `date` / `clock` / `difftime`，没有 `execute` / `getenv` / `remove` / `rename`。' },
]

/** 出现在脚本里、但不是沙箱注入的全局：ctx 是入参，handle 由脚本自己定义 */
export const EXTRA_NAMES = [
  { name: 'ctx', kind: 'variable', detail: '执行上下文（入参）', doc: '脚本拿到的参数：`ctx.input` / `ctx.output` / `ctx.json` / `ctx.log` / `ctx.script_id` / `ctx.mode` / `ctx.now` / `ctx.limits`。' },
  { name: 'handle', kind: 'function', detail: 'handle(ctx) → result', doc: '推荐的入口约定。定义了它就会被调用，且**它的非 nil 返回值优先**作为响应。' },
]

/** 库成员：名字 + 一句话说明 */
export const LUA_LIBRARIES = {
  json: [
    { name: 'encode', doc: '`json.encode(v) → string`。表键排序输出，稳定可复现；非有限数字、循环引用会报错。' },
    { name: 'decode', doc: '`json.decode(s) → table`。JSON null 解成 `json.null` 哨兵，不是 nil。' },
    { name: 'null', doc: 'JSON null 哨兵。判断用 `v == json.null`；`type(json.null)` 是 `"table"`。' },
  ],
  http: [
    { name: 'request', doc: '`http.request{ url=, method=, headers=, body=, json=, timeout_ms= } → table`。底层接口。' },
    { name: 'get', doc: '`http.get(url [, opts]) → table`。opts 可带 `headers` / `timeout_ms`。' },
    { name: 'post', doc: '`http.post(url, body [, opts]) → table`。body 是 table 时自动 JSON 序列化并带 `Content-Type: application/json`。' },
    { name: 'put', doc: '`http.put(url, body [, opts]) → table`。同 post。' },
    { name: 'patch', doc: '`http.patch(url, body [, opts]) → table`。同 post。' },
    { name: 'delete', doc: '`http.delete(url [, opts]) → table`。' },
    { name: 'fetch', doc: '`http.fetch(url, opts) → table`，与 `http.request` 等价（前端习惯叫法）。' },
  ],
  string: [
    { name: 'byte', doc: '取字符码 / 字节码。' },
    { name: 'char', doc: '由字符码构造字符串。' },
    { name: 'find', doc: '`s:find(pat [, init [, plain]]) → start, end, captures`。' },
    { name: 'format', doc: '`string.format("%d %s", a, b)`，类似 printf。' },
    { name: 'gmatch', doc: '`for w in s:gmatch("%a+") do ... end`，迭代所有匹配。' },
    { name: 'gsub', doc: '`s:gsub(pat, repl) → 新串, 替换次数`。' },
    { name: 'len', doc: '字符串长度（字节数，一个中文 3 字节）。' },
    { name: 'lower', doc: '转小写。' },
    { name: 'match', doc: '`s:match(pat) → 捕获`，最常用的取值方式。' },
    { name: 'pack', doc: '按格式打包二进制。' },
    { name: 'packsize', doc: '格式占用的字节数。' },
    { name: 'rep', doc: '重复字符串。' },
    { name: 'reverse', doc: '反转字符串。' },
    { name: 'sub', doc: '`s:sub(i [, j])` 取子串（下标从 1 开始，负数从尾部数）。' },
    { name: 'unpack', doc: '解包二进制字符串。' },
    { name: 'upper', doc: '转大写。' },
  ],
  table: [
    { name: 'concat', doc: '`table.concat(t [, sep [, i [, j]]])` 拼接数组。' },
    { name: 'insert', doc: '`table.insert(t, [pos,] v)` 插入元素。' },
    { name: 'move', doc: '搬移元素。' },
    { name: 'pack', doc: '`table.pack(...) → {n=个数, ...}`。' },
    { name: 'remove', doc: '`table.remove(t [, pos])` 删除并返回元素。' },
    { name: 'sort', doc: '`table.sort(t [, cmp])` 原地排序。' },
    { name: 'unpack', doc: '`table.unpack(t) → ...` 展开成多返回值。' },
  ],
  math: [
    { name: 'abs', doc: '绝对值。' },
    { name: 'ceil', doc: '向上取整。' },
    { name: 'floor', doc: '向下取整。' },
    { name: 'fmod', doc: '取余（浮点语义）。' },
    { name: 'huge', doc: '无穷大。' },
    { name: 'max', doc: '取最大值。' },
    { name: 'min', doc: '取最小值。' },
    { name: 'maxinteger', doc: '最大整数。' },
    { name: 'mininteger', doc: '最小整数。' },
    { name: 'modf', doc: '拆分整数与小数部分。' },
    { name: 'pi', doc: '圆周率。' },
    { name: 'random', doc: '`math.random()` / `math.random(m)` / `math.random(m, n)`。' },
    { name: 'randomseed', doc: '设置随机种子。' },
    { name: 'sqrt', doc: '平方根。' },
    { name: 'tointeger', doc: '转整数，无整数表示时返回 nil。' },
    { name: 'type', doc: '`"integer"` 或 `"float"`。' },
    { name: 'ult', doc: '无符号比较。' },
    { name: 'cos', doc: '余弦。' },
    { name: 'sin', doc: '正弦。' },
    { name: 'tan', doc: '正切。' },
    { name: 'deg', doc: '弧度转角度。' },
    { name: 'rad', doc: '角度转弧度。' },
    { name: 'exp', doc: 'e 的幂。' },
    { name: 'log', doc: '对数。' },
  ],
  os: [
    { name: 'time', doc: '`os.time() → 秒级时间戳`。' },
    { name: 'date', doc: '`os.date("%Y-%m-%d %H:%M:%S")`，默认本地时间。' },
    { name: 'clock', doc: 'CPU 时间（秒，浮点）。' },
    { name: 'difftime', doc: '两个时间戳之差。' },
  ],
  utf8: [
    { name: 'char', doc: '`utf8.char(0x4e2d) → "中"`。' },
    { name: 'charpattern', doc: '单个 UTF-8 字符的匹配模式。' },
    { name: 'codepoint', doc: '取码点。' },
    { name: 'codes', doc: '迭代所有码点。' },
    { name: 'len', doc: '`utf8.len("中文") → 2`（字符数，不是字节数）。' },
    { name: 'offset', doc: '按字符位置找字节位置。' },
  ],
  console: [
    { name: 'log', doc: '写日志。' },
    { name: 'info', doc: '写日志。' },
    { name: 'warn', doc: '写日志。' },
    { name: 'error', doc: '写日志（只是日志，不会中断脚本）。' },
    { name: 'debug', doc: '写日志。' },
  ],
  coroutine: [
    { name: 'create', doc: '创建协程。' },
    { name: 'resume', doc: '恢复协程。' },
    { name: 'yield', doc: '让出执行。' },
    { name: 'status', doc: '协程状态。' },
    { name: 'wrap', doc: '包装成函数。' },
    { name: 'isyieldable', doc: '当前是否可挂起。' },
    { name: 'running', doc: '当前协程。' },
    { name: 'close', doc: '关闭协程。' },
  ],
}

/** ctx 的字段 */
export const CTX_MEMBERS = [
  { name: 'input', doc: '请求体（JSON 解码后的 table）。与全局 `input` 是同一个表。' },
  { name: 'output', doc: '结果容器，`ctx.output.x = 1` 等价于 `output.x = 1`。' },
  { name: 'json', doc: '同全局 `json`。' },
  { name: 'log', doc: '同全局 `log`。' },
  { name: 'script_id', doc: '当前脚本 ID（字符串）。' },
  { name: 'mode', doc: '执行模式，正常执行为 `"run"`。' },
  { name: 'now', doc: '执行时刻的 Unix 时间戳（秒）。' },
  { name: 'limits', doc: '本次执行的限制：`timeout_ms` / `max_memory_mb` / `max_result_kb` / `max_depth` / `max_nodes`。' },
]

/** 代码片段：body 用 monaco snippet 语法，`${1:占位}` 是制表位，`$0` 是最终光标 */
export const LUA_SNIPPETS = [
  {
    label: 'handle',
    detail: '脚本入口函数',
    doc: '推荐的入口约定：定义 handle(ctx)，它的非 nil 返回值就是响应。',
    body: 'function handle(ctx)\n  local data = ctx.input\n  log("收到:", ctx.json.encode(data))\n\n  $0\n  return { ok = true }\nend',
  },
  { label: 'if', detail: '条件分支', body: 'if ${1:cond} then\n  $0\nend' },
  { label: 'ifelse', detail: '条件分支（含 else）', body: 'if ${1:cond} then\n  ${2:-- body}\nelse\n  $0\nend' },
  { label: 'fori', detail: '数值 for', body: 'for i = 1, ${1:n} do\n  $0\nend' },
  { label: 'forp', detail: '遍历数组 (ipairs)', body: 'for _, ${1:item} in ipairs(${2:list}) do\n  $0\nend' },
  { label: 'forpair', detail: '遍历键值 (pairs)', body: 'for ${1:k}, ${2:v} in pairs(${3:t}) do\n  $0\nend' },
  { label: 'while', detail: 'while 循环（注意超时）', body: 'while ${1:cond} do\n  $0\nend' },
  { label: 'func', detail: '局部函数', body: 'local function ${1:name}(${2:args})\n  $0\nend' },
  {
    label: 'pcall',
    detail: '保护调用',
    body: 'local ok, err = pcall(function()\n  $0\nend)\nif not ok then\n  log("失败:", err)\nend',
  },
  {
    label: 'httpget',
    detail: 'GET 外部接口并解码 JSON',
    doc: '返回值：ok / status / json / body / error。失败时 ok=false，不会抛错。',
    body: 'local resp = http.get("${1:https://example.com/api}")\nif not resp.ok then\n  return { ok = false, error = resp.error }\nend\nlocal data = resp.json  -- Content-Type 是 JSON 时自动解码，否则是 nil\n$0',
  },
  {
    label: 'httppost',
    detail: 'POST JSON 到下游（中转）',
    doc: 'body 传 table 会自动 JSON 序列化并设置 Content-Type。',
    body: 'local resp = http.post("${1:https://example.com/hook}", {\n  ${2:key} = ${3:value},\n})\nlog("转发结果:", resp.status)',
  },
]

/** 关键字片段 */
export const LUA_KEYWORD_SNIPPETS = [
  { label: 'local', detail: '局部变量', body: 'local ${1:name} = ${2:value}' },
  { label: 'function', detail: '函数定义', body: 'function ${1:name}(${2:args})\n  $0\nend' },
  { label: 'return', detail: '返回', body: 'return ${1:value}' },
  { label: 'repeat', detail: 'repeat/until', body: 'repeat\n  $0\nuntil ${1:cond}' },
]

// ----------------------------------------------------------------------
// 语法高亮（Monarch）
// ----------------------------------------------------------------------
// 长括号（--[==[ ]==] / [==[ ]==]）受限于 monarch 的逐行匹配，结束条件统一写成
// "任意层级"：--[[ a ]] b ]] 在第一处 ]] 结束 —— VS Code 内置的 Lua 文法也是这样。
export const LUA_MONARCH = {
  defaultToken: '',
  tokenPostfix: '.lua',

  keywords: LUA_KEYWORDS,
  sandboxGlobals: SANDBOX_GLOBALS.map((g) => g.name),
  libs: Object.keys(LUA_LIBRARIES),

  brackets: [
    { open: '{', close: '}', token: 'delimiter.curly' },
    { open: '[', close: ']', token: 'delimiter.square' },
    { open: '(', close: ')', token: 'delimiter.parenthesis' },
  ],

  escapes: /\\(?:[abfnrtv\\"']|x[0-9A-Fa-f]{2}|[0-9]{1,3}|u\{[0-9A-Fa-f]+\}|z\s*)/,

  tokenizer: {
    root: [
      { include: '@whitespace' },

      // 库/字段访问：json.encode(...) 里的 encode 当成函数色，input.car 里的 car 当成属性色
      // 注意：monarch 的分组动作要求「捕获组连续铺满整段匹配」，点号必须自己占一个组，
      // 否则报 "with groups, all characters should be matched in consecutive groups"。
      [
        /([a-zA-Z_]\w*)(\.)([a-zA-Z_]\w*)(?=\s*\()/,
        ['variable.predefined', 'delimiter', 'type.identifier'],
      ],
      [/([a-zA-Z_]\w*)(\.)([a-zA-Z_]\w*)/, ['variable.predefined', 'delimiter', 'property']],

      [
        /[a-zA-Z_]\w*/,
        {
          cases: {
            '@keywords': 'keyword',
            '@sandboxGlobals': 'variable.predefined',
            '@default': 'identifier',
          },
        },
      ],

      [/"/, { token: 'string.quote', bracket: '@open', next: '@string_double' }],
      [/'/, { token: 'string.quote', bracket: '@open', next: '@string_single' }],
      // 长括号字符串 [[ ]] / [==[ ]==]
      [/\[(=*)\[/, { token: 'string.quote', bracket: '@open', next: '@longstring' }],

      [/\d+\.\d+([eE][-+]?\d+)?/, 'number.float'],
      [/\.\d+([eE][-+]?\d+)?/, 'number.float'],
      [/0[xX][0-9a-fA-F]+/, 'number.hex'],
      [/\d+/, 'number'],

      [/[{}()[\]]/, '@brackets'],
      [/[;,.]+/, 'delimiter'],
      [/[=><!~?:&|+\-*/^%#]+/, 'operator'],
    ],

    whitespace: [
      [/[ \t\r\n]+/, ''],
      [/--\[(=*)\[/, { token: 'comment', next: '@longcomment' }],
      [/--.*$/, 'comment'],
    ],

    longcomment: [
      [/\]=*\]/, { token: 'comment', next: '@pop' }],
      [/[^\]=]+/, 'comment'],
      [/[=\]]/, 'comment'],
    ],

    longstring: [
      [/\]=*\]/, { token: 'string.quote', bracket: '@close', next: '@pop' }],
      [/[^\]=]+/, 'string'],
      [/[=\]]/, 'string'],
    ],

    string_double: [
      [/[^\\"]+/, 'string'],
      [/@escapes/, 'string.escape'],
      [/\\./, 'string.escape.invalid'],
      [/"/, { token: 'string.quote', bracket: '@close', next: '@pop' }],
    ],

    string_single: [
      [/[^\\']+/, 'string'],
      [/@escapes/, 'string.escape'],
      [/\\./, 'string.escape.invalid'],
      [/'/, { token: 'string.quote', bracket: '@close', next: '@pop' }],
    ],
  },
}

// ----------------------------------------------------------------------
// 语言配置：注释 / 括号 / 自动闭合 / 缩进 / 折叠
// ----------------------------------------------------------------------
export const LUA_LANGUAGE_CONFIGURATION = {
  comments: {
    lineComment: '--',
    blockComment: ['--[[', ']]'],
  },
  brackets: [
    ['{', '}'],
    ['[', ']'],
    ['(', ')'],
  ],
  autoClosingPairs: [
    { open: '{', close: '}' },
    { open: '[', close: ']' },
    { open: '(', close: ')' },
    { open: '"', close: '"', notIn: ['string', 'comment'] },
    { open: "'", close: "'", notIn: ['string', 'comment'] },
  ],
  surroundingPairs: [
    { open: '{', close: '}' },
    { open: '[', close: ']' },
    { open: '(', close: ')' },
    { open: '"', close: '"' },
    { open: "'", close: "'" },
  ],
  indentationRules: {
    increaseIndentPattern: /(\b(then|do|else|repeat)\s*(--.*)?|\bfunction\b[^\n]*\)\s*)$/,
    decreaseIndentPattern: /^\s*(\b(end|until|else|elseif)\b|[)\]}])/,
  },
  // indentAction 在这里写字符串，由 luaMonaco.js 映射成 monaco 的枚举
  onEnterRules: [
    {
      beforeText: /\b(then|do|else|repeat)\s*(--.*)?$/,
      action: { indentAction: 'indent' },
    },
    {
      beforeText: /\bfunction\b[^\n]*\)\s*(--.*)?$/,
      action: { indentAction: 'indent' },
    },
    {
      beforeText: /^\s*(\b(end|until|else|elseif)\b|[)\]}])/,
      action: { indentAction: 'outdent' },
    },
  ],
  folding: {
    markers: {
      start: /^\s*--\s*#?region\b/,
      end: /^\s*--\s*#?endregion\b/,
    },
  },
}

// ----------------------------------------------------------------------
// 提示目录
// ----------------------------------------------------------------------
const DOC_FALLBACK = ' `Lua` 标准库函数。'

/** 光标前文本 → 提示上下文。`beforeWord` 是「正在输入的单词之前」的文本。 */
export function completionContext(beforeWord) {
  const text = beforeWord || ''
  const member = /([A-Za-z_][\w.]*)\.\s*$/.exec(text)
  if (member) {
    return { kind: 'member', receiver: member[1].split('.').pop() }
  }
  return { kind: 'global', receiver: '' }
}

function matchPrefix(prefix, name) {
  if (!prefix) return true
  return name.toLowerCase().startsWith(String(prefix).toLowerCase())
}

/** 全局补全：片段 + 关键字 + 沙箱全局 + ctx/handle */
export function globalCompletions(prefix = '') {
  const out = []
  for (const s of LUA_SNIPPETS) {
    if (!matchPrefix(prefix, s.label)) continue
    out.push({
      label: s.label,
      kind: 'snippet',
      detail: s.detail,
      documentation: s.doc || '',
      insertText: s.body,
      sortText: `0_${s.label}`,
    })
  }
  for (const s of LUA_KEYWORD_SNIPPETS) {
    if (!matchPrefix(prefix, s.label)) continue
    out.push({
      label: s.label,
      kind: 'snippet',
      detail: s.detail,
      insertText: s.body,
      sortText: `0_${s.label}`,
    })
  }
  for (const k of LUA_KEYWORDS) {
    if (!matchPrefix(prefix, k)) continue
    out.push({ label: k, kind: 'keyword', detail: '关键字', sortText: `1_${k}` })
  }
  for (const g of [...SANDBOX_GLOBALS, ...EXTRA_NAMES]) {
    if (!matchPrefix(prefix, g.name)) continue
    out.push({
      label: g.name,
      kind: g.kind,
      detail: g.detail,
      documentation: g.doc,
      sortText: `2_${g.name}`,
    })
  }
  return out
}

/** 成员补全：ctx. / json. / http. / string. ... */
export function memberCompletions(receiver, prefix = '') {
  if (!receiver) return []
  if (receiver === 'ctx') {
    return CTX_MEMBERS.filter((m) => matchPrefix(prefix, m.name)).map((m) => ({
      label: m.name,
      kind: 'property',
      detail: `ctx.${m.name}`,
      documentation: m.doc,
    }))
  }
  const lib = LUA_LIBRARIES[receiver]
  if (!lib) return []
  return lib
    .filter((m) => matchPrefix(prefix, m.name))
    .map((m) => ({
      label: m.name,
      kind: receiver === 'json' && m.name === 'null' ? 'constant' : 'function',
      detail: `${receiver}.${m.name}`,
      documentation: m.doc || `\`${receiver}.${m.name}\`。${DOC_FALLBACK}`,
    }))
}

/** 一次调用拿全：先看上下文，再给提示 */
export function completionsFor(prefix, beforeWord) {
  const ctx = completionContext(beforeWord)
  if (ctx.kind === 'member') return memberCompletions(ctx.receiver, prefix)
  return globalCompletions(prefix)
}

/** 悬浮文档：word 可以是 `json.encode` 这样的点分名字 */
export function hoverDocFor(word) {
  if (!word) return null
  const dotted = /^([A-Za-z_]\w*)\.([A-Za-z_]\w*)$/.exec(word)
  if (dotted) {
    const [, head, member] = dotted
    if (head === 'ctx') {
      const m = CTX_MEMBERS.find((x) => x.name === member)
      return m ? { name: word, doc: m.doc } : null
    }
    const lib = LUA_LIBRARIES[head]
    if (lib) {
      const m = lib.find((x) => x.name === member)
      if (m) return { name: word, doc: m.doc || `\`${word}\`。${DOC_FALLBACK}` }
    }
    return null
  }
  const g = [...SANDBOX_GLOBALS, ...EXTRA_NAMES].find((x) => x.name === word)
  return g ? { name: word, doc: g.doc } : null
}

/** 文档里的补全名字（含 ctx/handle） */
export function completionNames() {
  return [...SANDBOX_GLOBALS, ...EXTRA_NAMES].map((g) => g.name)
}

/** 沙箱真实全局名字清单（给前后端对齐测试用） */
export function sandboxGlobalNames() {
  return SANDBOX_GLOBALS.map((g) => g.name).sort()
}
