/**
 * 极简 Lua 词法着色（给 LuaEditor 的高亮层用）。
 *
 * 手写扫描而不是一条大正则，是为了正确处理 `[==[ ... ]==]` 长括号字符串、转义引号
 * 与 `--[[ ]]` 块注释 —— 正则版本在遇到嵌套方括号时很容易截断。
 *
 * 只做"看着舒服"级别的着色，不追求语法完备（非法代码也不能崩）。
 */

export const LUA_KEYWORDS = new Set([
  'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for', 'function', 'goto',
  'if', 'in', 'local', 'nil', 'not', 'or', 'repeat', 'return', 'then', 'true', 'until', 'while',
])

/** 沙箱暴露给脚本的全局表 / 函数，着色出来当提示 */
export const LUA_BUILTINS = new Set([
  'json', 'string', 'table', 'math', 'os', 'utf8', 'coroutine', 'input', 'output',
  'handle', 'ctx', 'print', 'log', 'console', 'select', 'type', 'tostring', 'tonumber',
  'pairs', 'ipairs', 'pcall', 'xpcall', 'next', 'error', 'assert', 'setmetatable',
  'getmetatable', 'rawget', 'rawset', 'rawequal', 'rawlen', '_G', '_VERSION',
])

export function escapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function span(cls, text) {
  return `<span class="tk-${cls}">${escapeHtml(text)}</span>`
}

const isDigit = (c) => c >= '0' && c <= '9'
const isIdentStart = (c) => !!c && /[A-Za-z_]/.test(c)
const isIdent = (c) => !!c && /[A-Za-z0-9_]/.test(c)

/** 若 src[i] 处是长括号开头（[=*[ ），返回等号个数，否则返回 -1 */
function longBracketLevel(src, i) {
  if (src[i] !== '[') return -1
  let k = i + 1
  let eq = 0
  while (src[k] === '=') {
    eq++
    k++
  }
  return src[k] === '[' ? eq : -1
}

export function highlightLua(src) {
  let out = ''
  let i = 0
  const n = src.length

  while (i < n) {
    const c = src[i]

    // 注释：-- 到行尾，或 --[[ / --[==[ 块注释
    if (c === '-' && src[i + 1] === '-') {
      const level = longBracketLevel(src, i + 2)
      if (level >= 0) {
        const close = ']' + '='.repeat(level) + ']'
        const bodyStart = i + 2 + level + 2
        const end = src.indexOf(close, bodyStart)
        const stop = end < 0 ? n : end + close.length
        out += span('cmt', src.slice(i, stop))
        i = stop
      } else {
        let end = src.indexOf('\n', i)
        if (end < 0) end = n
        out += span('cmt', src.slice(i, end))
        i = end
      }
      continue
    }

    // 短字符串
    if (c === '"' || c === "'") {
      let j = i + 1
      while (j < n && src[j] !== c) {
        if (src[j] === '\\') j++
        else if (src[j] === '\n') break
        j++
      }
      const stop = Math.min(j + 1, n)
      out += span('str', src.slice(i, stop))
      i = stop
      continue
    }

    // 长括号字符串 [[ ]] / [==[ ]==]
    const strLevel = longBracketLevel(src, i)
    if (strLevel >= 0) {
      const close = ']' + '='.repeat(strLevel) + ']'
      const end = src.indexOf(close, i + strLevel + 2)
      const stop = end < 0 ? n : end + close.length
      out += span('str', src.slice(i, stop))
      i = stop
      continue
    }

    // 数字（含 0x 与科学计数法）
    if (isDigit(c) || (c === '.' && isDigit(src[i + 1]))) {
      let j = i
      while (j < n && /[0-9a-fA-FxX.]/.test(src[j])) j++
      if (/[eE]/.test(src[j] || '')) {
        j++
        if (src[j] === '+' || src[j] === '-') j++
        while (j < n && isDigit(src[j])) j++
      }
      out += span('num', src.slice(i, j))
      i = j
      continue
    }

    // 标识符 / 关键字
    if (isIdentStart(c)) {
      let j = i
      while (j < n && isIdent(src[j])) j++
      const word = src.slice(i, j)
      let k = j
      while (k < n && (src[k] === ' ' || src[k] === '\t')) k++
      if (LUA_KEYWORDS.has(word)) out += span('kw', word)
      else if (src[k] === '(') out += span('fn', word)
      else if (LUA_BUILTINS.has(word)) out += span('bi', word)
      else out += escapeHtml(word)
      i = j
      continue
    }

    out += escapeHtml(c)
    i++
  }

  // 末尾补一个换行：高亮层比 textarea 少一行的话，滚动到底会错位
  return out + '\n'
}
