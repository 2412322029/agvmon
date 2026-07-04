<template>
  <!-- 浮动终端窗口 -->
  <div class="shell-float" v-show="open && !minimized"
    :style="{ left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px' }">
    <!-- 标题栏 -->
    <div class="float-bar" @mousedown="startDrag">
      <span class="float-title">终端</span>
      <n-button size="tiny" quaternary @click.stop="store.create()" title="新建">
        <template #icon><AddOutline /></template>
      </n-button>
      <div class="float-tabs">
        <div v-for="s in mySessions" :key="s.id"
          class="float-tab" :class="{ active: s.id === store.activeId.value }"
          @click.stop="store.activate(s.id)">
          <span class="tab-dot" :class="s.connected ? 'on' : 'off'"></span>
          <span class="tab-name">{{ s.id.slice(0, 8) }}</span>
          <span class="tab-x" @click.stop="store.remove(s.id)">&times;</span>
        </div>
      </div>
      <span style="flex:1"></span>
      <n-button size="tiny" quaternary @click.stop="minimized = true" title="最小化">
        <template #icon><RemoveOutline /></template>
      </n-button>
      <n-button size="tiny" quaternary @click.stop="open = false" title="关闭">
        <template #icon><CloseOutline /></template>
      </n-button>
    </div>

    <!-- 终端体 — 全部保持连接，v-show 切换 -->
    <div class="float-body">
      <template v-for="s in mySessions" :key="s.id">
        <div v-show="s.id === store.activeId.value" class="float-term">
          <WebShell :sessionId="s.id" :embedded="true" :fitTrigger="fitCounter"
            @status-change="(e) => store.updateStatus(s.id, e)" />
        </div>
      </template>
      <div v-if="mySessions.length === 0" class="float-empty">点击 + 创建终端</div>
    </div>

    <!-- 右下角缩放 -->
    <div class="float-resize" @mousedown="startResize"></div>
  </div>

  <!-- 最小化胶囊 — 屏幕右侧 -->
  <div v-show="open && minimized" class="shell-pill" @click="minimized = false" title="点击恢复终端">
    <span class="pill-dot" :class="hasConnected ? 'on' : 'off'"></span>
    <span class="pill-text">终端 ({{ store.sessions.value.length }})</span>
  </div>
</template>

<script setup>
import WebShell from '@/components/WebShell.vue';
import { useShellStore } from '@/composables/useShellStore';
import { AddOutline, CloseOutline, RemoveOutline } from '@vicons/ionicons5';
import { NButton } from 'naive-ui';
import { computed, ref, watch } from 'vue';

const store = useShellStore();

// 记忆窗口位置（localStorage）
const _posKey = 'webshell_win_pos';
function _loadPos() {
  try { return JSON.parse(localStorage.getItem(_posKey)) || {}; } catch { return {}; }
}
function _savePos() {
  try { localStorage.setItem(_posKey, JSON.stringify({ x: x.value, y: y.value, w: w.value, h: h.value })); } catch { /* */ }
}
const saved = _loadPos();
const open = ref(false);
const minimized = ref(false);
const fitCounter = ref(0);
const x = ref(saved.x || window.innerWidth - 900);
const y = ref(saved.y || window.innerHeight - 520);
const w = ref(saved.w || 880);
const h = ref(saved.h || 480);
// 位置变化时自动保存
watch([x, y, w, h], _savePos, { deep: false });
// 切换 tab 时触发终端自适应
watch(() => store.activeId.value, () => { fitCounter.value++; });

const hasConnected = computed(() => store.sessions.value.some(s => s.connected));
// 浮窗只显示本窗口创建的会话
const mySessions = computed(() => store.sessions.value.filter(s => s._win === store.winId));

function toggle() {
  if (!open.value) { open.value = true; minimized.value = false; }
  else if (minimized.value) { minimized.value = false; }
  else { minimized.value = true; }
}

defineExpose({ toggle });

// ---- 拖拽移动 ----
let dX = 0, dY = 0, sX = 0, sY = 0;
function startDrag(e) {
  if (e.target.closest('.float-tab') || e.target.closest('button')) return;
  e.preventDefault(); sX = e.clientX; sY = e.clientY; dX = x.value; dY = y.value;
  document.addEventListener('mousemove', onDrag); document.addEventListener('mouseup', stopDrag);
}
function onDrag(e) {
  x.value = Math.max(0, Math.min(window.innerWidth - 300, dX + (e.clientX - sX)));
  y.value = Math.max(0, Math.min(window.innerHeight - 60, dY + (e.clientY - sY)));
}
function stopDrag() { document.removeEventListener('mousemove', onDrag); document.removeEventListener('mouseup', stopDrag); }

// ---- 缩放 ----
let rzX = 0, rzY = 0, rzW = 0, rzH = 0;
function startResize(e) {
  e.preventDefault(); e.stopPropagation();
  rzX = e.clientX; rzY = e.clientY; rzW = w.value; rzH = h.value;
  document.addEventListener('mousemove', onResize); document.addEventListener('mouseup', stopResize);
}
function onResize(e) { w.value = Math.max(360, rzW + (e.clientX - rzX)); h.value = Math.max(180, rzH + (e.clientY - rzY)); fitCounter.value++; }
function stopResize() { document.removeEventListener('mousemove', onResize); document.removeEventListener('mouseup', stopResize); }
</script>

<style scoped>
/* 浮动窗口 */
.shell-float {
  position: fixed; z-index: 1001;
  background: #0d1117; border: 1px solid #30363d;
  border-radius: 8px; display: flex; flex-direction: column;
  box-shadow: 0 8px 32px rgba(0,0,0,.5);
  overflow: hidden; min-width: 360px; min-height: 180px;
}
.float-bar {
  display: flex; align-items: center; gap: 4px;
  height: 32px; padding: 0 4px;
  background: #161b22; border-bottom: 1px solid #21262d;
  cursor: move; user-select: none; flex-shrink: 0;
}
.float-title { font-size: 12px; color: #8b949e; margin-right: 4px; flex-shrink: 0; }
.float-tabs { display: flex; gap: 2px; overflow-x: auto; flex: 1; }
.float-tabs::-webkit-scrollbar { height: 2px; }
.float-tab {
  display: flex; align-items: center; gap: 4px;
  padding: 2px 8px; height: 22px; font-size: 11px;
  color: #8b949e; cursor: pointer; border-radius: 4px;
  white-space: nowrap; user-select: none; transition: background .12s;
  border: 1px solid transparent;
}
.float-tab:hover { background: #21262d; color: #c9d1d9; }
.float-tab.active { background: #0d1117; color: #e6edf3; border-color: #21262d; }
.tab-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.tab-dot.on  { background: #3fb950; }
.tab-dot.off { background: #6e7681; }
.tab-name { max-width: 80px; overflow: hidden; text-overflow: ellipsis; }
.tab-x { width: 12px; height: 12px; line-height: 12px; text-align: center; border-radius: 2px; font-size: 12px; opacity: 0; }
.float-tab:hover .tab-x, .float-tab.active .tab-x { opacity: .6; }
.tab-x:hover { opacity: 1; background: #f8514940; color: #f85149; }

.float-body { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }
.float-term { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }
.float-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: #484f58; font-size: 13px; }

.float-resize {
  position: absolute; bottom: 0; right: 0;
  width: 16px; height: 16px; cursor: nwse-resize;
}
.float-resize::after {
  content: ''; position: absolute; bottom: 2px; right: 2px;
  width: 8px; height: 8px;
  border-right: 2px solid #484f58; border-bottom: 2px solid #484f58;
}

/* 最小化胶囊 */
.shell-pill {
  position: fixed; z-index: 1001;
  right: 12px; top: 50%; transform: translateY(-50%);
  display: flex; align-items: center; gap: 6px;
  padding: 8px 14px;
  background: #161b22; border: 1px solid #30363d;
  border-radius: 20px;
  cursor: pointer; user-select: none;
  box-shadow: 0 4px 16px rgba(0,0,0,.4);
  transition: background .15s;
}
.shell-pill:hover { background: #21262d; }
.pill-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.pill-dot.on  { background: #3fb950; box-shadow: 0 0 4px #3fb95088; }
.pill-dot.off { background: #6e7681; }
.pill-text { font-size: 12px; color: #c9d1d9; white-space: nowrap; }
</style>
