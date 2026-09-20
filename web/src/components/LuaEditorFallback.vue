<template>
  <div class="lua-editor" :style="{ height }">
    <div ref="gutterRef" class="gutter">
      <div v-for="n in lineCount" :key="n" class="ln">{{ n }}</div>
    </div>
    <div class="code-area">
      <!-- 高亮层在下、透明 textarea 在上：两层字号行高完全一致，滚动同步 -->
      <pre ref="preRef" class="hl" aria-hidden="true"><code v-html="highlighted"></code></pre>
      <textarea ref="taRef" class="input" :value="model" :readonly="readonly" :placeholder="placeholder" wrap="off"
        spellcheck="false" autocomplete="off" autocapitalize="off" @input="onInput" @scroll="syncScroll"
        @keydown="onkeydown"></textarea>
    </div>
  </div>
</template>

<script setup>
/**
 * 简易 Lua 编辑器（无依赖版）。
 *
 * 只在 Monaco chunk 加载失败时兜底使用（见 LuaEditor.vue）：行号 + 手写词法高亮 +
 * 透明 textarea 叠层。功能上够用，但没有智能提示，所以正常路径永远是 Monaco。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { escapeHtml, highlightLua } from '../composables/luaHighlight.js'

defineProps({
  placeholder: { type: String, default: '' },
  readonly: { type: Boolean, default: false },
  height: { type: String, default: '460px' },
})
const emit = defineEmits(['run', 'save'])

const model = defineModel({ type: String, default: '' })

const taRef = ref(null)
const preRef = ref(null)
const gutterRef = ref(null)

const INDENT = '  '
// 超过这个长度就不做高亮，避免大脚本每敲一个字都全量扫描
const HIGHLIGHT_LIMIT = 200000

const lineCount = computed(() => (model.value ? model.value.split('\n').length : 1))

const highlighted = computed(() => {
  const code = model.value || ''
  if (code.length > HIGHLIGHT_LIMIT) return escapeHtml(code) + '\n'
  return highlightLua(code)
})

// ── 滚动同步 ──
function syncScroll() {
  const ta = taRef.value
  if (!ta) return
  if (preRef.value) {
    preRef.value.scrollTop = ta.scrollTop
    preRef.value.scrollLeft = ta.scrollLeft
  }
  if (gutterRef.value) gutterRef.value.scrollTop = ta.scrollTop
}

watch(model, () => nextTick(syncScroll))

// ── 输入 ──
function onInput(e) {
  model.value = e.target.value
}

function applyValue(ta, text, start, end) {
  ta.value = text
  ta.selectionStart = start
  ta.selectionEnd = end
  model.value = text
  nextTick(syncScroll)
}

function indentLines(ta, dedent) {
  const value = ta.value
  const selStart = ta.selectionStart
  const selEnd = ta.selectionEnd
  // 选区起始所在行行首
  const lineStart = value.lastIndexOf('\n', selStart - 1) + 1
  const blockEnd = value.indexOf('\n', selEnd)
  const stop = blockEnd < 0 ? value.length : blockEnd
  const lines = value.slice(lineStart, stop).split('\n')
  const changed = lines.map((line) => {
    if (dedent) return line.startsWith(INDENT) ? line.slice(INDENT.length) : line.replace(/^[ \t]/, '')
    return line.length || lines.length > 1 ? INDENT + line : line
  })
  const nextBlock = changed.join('\n')
  const nextValue = value.slice(0, lineStart) + nextBlock + value.slice(stop)
  const delta = nextBlock.length - (stop - lineStart)
  return applyValue(ta, nextValue, selStart + (dedent ? Math.max(delta, -INDENT.length) : INDENT.length), selEnd + delta)
}

function insertIndent(ta, dedent) {
  const value = ta.value
  const selStart = ta.selectionStart
  const selEnd = ta.selectionEnd
  if (selStart !== selEnd || dedent) return indentLines(ta, dedent)

  const lineStart = value.lastIndexOf('\n', selStart - 1) + 1
  const column = selStart - lineStart
  const pad = INDENT.length - (column % INDENT.length)
  const nextValue = value.slice(0, selStart) + ' '.repeat(pad) + value.slice(selEnd)
  return applyValue(ta, nextValue, selStart + pad, selStart + pad)
}

function autoIndent(ta) {
  const value = ta.value
  const selStart = ta.selectionStart
  const lineStart = value.lastIndexOf('\n', selStart - 1) + 1
  const currentLine = value.slice(lineStart, selStart)
  const indent = (currentLine.match(/^[ \t]*/) || [''])[0]
  const trimmed = currentLine.trimEnd()
  // 行尾是块开头就多缩进一级
  const opens = /(\bthen\b|\bdo\b|\belse\b|\brepeat\b|\bfunction\b|[{([])$/.test(trimmed)
  const added = '\n' + indent + (opens ? INDENT : '')
  const nextValue = value.slice(0, selStart) + added + value.slice(ta.selectionEnd)
  const caret = selStart + added.length
  return applyValue(ta, nextValue, caret, caret)
}

function onkeydown(e) {
  const ta = e.target
  if (e.key === 'Tab') {
    e.preventDefault()
    insertIndent(ta, e.shiftKey)
    return
  }
  if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
    e.preventDefault()
    emit('save')
    return
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault()
    emit('run')
    return
  }
  if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault()
    autoIndent(ta)
  }
}

defineExpose({
  focus: () => taRef.value?.focus(),
  scrollToTop: () => {
    if (taRef.value) taRef.value.scrollTop = 0
    syncScroll()
  },
})
</script>

<style scoped>
.lua-editor {
  display: flex;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  overflow: hidden;
  background: #fbfbfb;
}

.gutter {
  flex: 0 0 auto;
  padding: 8px 6px 8px 10px;
  overflow: hidden;
  text-align: right;
  user-select: none;
  background: #f3f3f3;
  border-right: 1px solid #e5e5e5;
  color: #9aa0a6;
  font: 13px/20px ui-monospace, SFMono-Regular, Consolas, 'Cascadia Mono', monospace;
}

.ln {
  height: 20px;
}

.code-area {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
}

.hl,
.input {
  position: absolute;
  inset: 0;
  margin: 0;
  padding: 8px 12px;
  border: 0;
  font: 13px/20px ui-monospace, SFMono-Regular, Consolas, 'Cascadia Mono', monospace;
  tab-size: 2;
  white-space: pre;
  word-wrap: normal;
}

.hl {
  overflow: hidden;
  pointer-events: none;
  color: #333;
  background: transparent;
}

.input {
  overflow: auto;
  resize: none;
  outline: none;
  background: transparent;
  color: transparent;
  caret-color: #1677ff;
}

.input::placeholder {
  color: #b8b8b8;
}

.input::selection {
  background: rgba(22, 119, 255, 0.28);
}

/* 着色 */
.tk-cmt {
  color: #7a8b99;
  font-style: italic;
}

.tk-str {
  color: #a31515;
}

.tk-num {
  color: #098658;
}

.tk-kw {
  color: #0000ff;
}

.tk-bi {
  color: #795e26;
}

.tk-fn {
  color: #795e26;
}

/* 暗色 */
[data-theme='dark'] .lua-editor {
  border-color: #3a3a3a;
  background: #1b1b1b;
}

[data-theme='dark'] .gutter {
  background: #171717;
  border-right-color: #303030;
  color: #6b6b6b;
}

[data-theme='dark'] .hl {
  color: #d4d4d4;
}

[data-theme='dark'] .tk-cmt {
  color: #6a9955;
}

[data-theme='dark'] .tk-str {
  color: #ce9178;
}

[data-theme='dark'] .tk-num {
  color: #b5cea8;
}

[data-theme='dark'] .tk-kw {
  color: #569cd6;
}

[data-theme='dark'] .tk-bi,
[data-theme='dark'] .tk-fn {
  color: #dcdcaa;
}

[data-theme='dark'] .input {
  caret-color: #7cc4ff;
}
</style>
