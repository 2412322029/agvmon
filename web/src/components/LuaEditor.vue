<template>
  <div class="lua-editor" :style="{ height }">
    <!-- Monaco 容器必须一直有尺寸；没就绪时用 v-show 藏起来但保留占位 -->
    <div ref="hostRef" v-show="status === 'monaco'" class="monaco-host"></div>

    <LuaEditorFallback v-if="status !== 'monaco'" v-model="model" :placeholder="placeholder"
      :readonly="readonly" height="100%" @run="emit('run')" @save="emit('save')" />

    <div v-if="status === 'loading'" class="editor-tip">正在加载代码编辑器…</div>
    <div v-if="status === 'fallback'" class="editor-tip warn" :title="loadError">
      Monaco 编辑器加载失败，已退回简易编辑器（{{ loadError }}）
    </div>
  </div>
</template>

<script setup>
/**
 * Lua 代码编辑器：VS Code 同款内核（Monaco）+ 语法高亮 + 智能提示。
 *
 * Monaco 体积不小，所以这里 **动态 import**：只有真正打开用户脚本页才会加载，
 * 而且万一 chunk 取不到（比如更新包只覆盖了一半），自动退回简易编辑器而不是白屏。
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import LuaEditorFallback from './LuaEditorFallback.vue'

const props = defineProps({
  placeholder: { type: String, default: '' },
  readonly: { type: Boolean, default: false },
  height: { type: String, default: '460px' },
})
const emit = defineEmits(['run', 'save'])

const model = defineModel({ type: String, default: '' })

const hostRef = ref(null)
const status = ref('loading') // loading | monaco | fallback
const loadError = ref('')

let handle = null
let stopThemeWatch = null

watch(
  () => props.readonly,
  (flag) => handle?.setReadOnly(flag),
)

watch(model, (value) => {
  // 只有"外部改内容"才需要写回编辑器；用户自己敲的改动值本来就相等
  if (handle && typeof value === 'string') handle.replaceAll(value)
})

onMounted(async () => {
  try {
    const mod = await import('../composables/luaMonaco.js')
    mod.setupLuaMonaco()
    status.value = 'monaco'
    await nextTick()

    handle = mod.createLuaEditor(hostRef.value, {
      value: model.value || '',
      readOnly: props.readonly,
      placeholder: props.placeholder,
      onChange: (value) => {
        model.value = value
      },
      onRun: () => emit('run'),
      onSave: () => emit('save'),
    })
    stopThemeWatch = mod.watchTheme((name) => handle?.setTheme(name))
  } catch (err) {
    status.value = 'fallback'
    loadError.value = err?.message || String(err)
    // eslint-disable-next-line no-console
    console.error('[LuaEditor] Monaco 加载失败，退回首屏编辑器', err)
  }
})

onBeforeUnmount(() => {
  if (stopThemeWatch) stopThemeWatch()
  if (handle) handle.dispose()
  handle = null
})

defineExpose({
  focus: () => {
    if (handle) handle.editor.focus()
  },
  scrollToTop: () => {
    if (handle) handle.editor.setScrollTop(0)
  },
  /** 供调试：当前用的是 monaco 还是兜底编辑器 */
  engine: () => status.value,
})
</script>

<style scoped>
.lua-editor {
  position: relative;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  overflow: hidden;
  background: #fff;
}

.monaco-host {
  width: 100%;
  height: 100%;
}

[data-theme='dark'] .lua-editor {
  border-color: #3a3a3a;
  background: #1e1e1e;
}

.editor-tip {
  position: absolute;
  right: 10px;
  bottom: 6px;
  z-index: 3;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  color: #8a8a8a;
  background: rgba(128, 128, 128, 0.12);
  pointer-events: none;
}

.editor-tip.warn {
  color: #d03050;
  pointer-events: auto;
  max-width: 80%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
