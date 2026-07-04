<template>
  <div class="webshell-wrapper" :class="{ embedded: embedded }">
    <div v-if="!embedded" class="webshell-status" :class="{ connected, denied }">
      {{ denied ? '🚫 访问拒绝' : connected ? '● 已连接' : '● 未连接' }}
    </div>
    <div class="webshell-inner">
      <div ref="terminalContainer" class="webshell-container" :class="{ embedded }" @click="focusTerminal"></div>
      <!-- 被其他窗口占用 -->
      <div v-if="busy && !connected" class="busy-overlay">
        <span>此终端在另一个窗口使用中</span>
        <span class="busy-client" v-if="busyClient">{{ busyClient }}</span>
        <div class="busy-actions">
          <span class="busy-btn" @click="supplant()">抢占回来</span>
        </div>
      </div>
      <!-- 断开时重连 -->
      <div v-if="!connected && !denied && !busy" class="reconnect-badge" @click="connect(); focusTerminal()" title="重新连接">
        ↻
      </div>
    </div>
  </div>
</template>

<script setup>
import { CanvasAddon } from '@xterm/addon-canvas';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { useDialog } from 'naive-ui';
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';

const dialog = useDialog();

const props = defineProps({
  sessionId: { type: String, required: true },
  embedded: { type: Boolean, default: false },
  fitTrigger: { type: Number, default: 0 },
  disconnectVer: { type: Number, default: 0 },
});

const emit = defineEmits(['status-change']);

const terminalContainer = ref(null);
const connected = ref(false);
const denied = ref(false);
const busy = ref(false);
const busyClient = ref('');

let term = null;
let fitAddon = null;
let wsRef = null;        // 闭包安全引用，始终指向当前 WebSocket
let reconnectTimer = null;
let resizeObserver = null;
let pingTimer = null;
let pongTimeout = null;
let reconnectDelay = 1000;  // 重连延迟，初始 1s，指数退避
const MAX_RECONNECT_DELAY = 30000;
const MAX_INPUT_BUFFER = 8192;  // 输入缓冲上限（字符数）

// ---------------------------------------------------------------------------
// 初始化终端 — Canvas 渲染器，DOM 回退
// ---------------------------------------------------------------------------
function initTerminal() {
  term = new Terminal({
    cursorBlink: true,
    cursorStyle: 'bar',
    disableStdin: false,
    fontSize: 15,
    fontFamily: 'Cascadia Code, Fira Code, Consolas, "Courier New", monospace',
    theme: {
      background: '#0d1117',
      foreground: '#c9d1d9',
      cursor: '#58a6ff',
      selectionBackground: '#264f78',
      black:   '#484f58',
      red:     '#ff7b72',
      green:   '#3fb950',
      yellow:  '#d29922',
      blue:    '#58a6ff',
      magenta: '#bc8cff',
      cyan:    '#39c2d3',
      white:   '#b1bac4',
      brightBlack:   '#6e7681',
      brightRed:     '#ffa198',
      brightGreen:   '#56d364',
      brightYellow:  '#e3b341',
      brightBlue:    '#79c0ff',
      brightMagenta: '#d2a8ff',
      brightCyan:    '#56d4dd',
      brightWhite:   '#f0f6fc',
    },
    allowProposedApi: true,
    scrollback: 5000,
    tabStopWidth: 4,
  });

  // Canvas 渲染器（性能最优），失败回退 DOM
  try {
    term.loadAddon(new CanvasAddon());
  } catch (e) {
    console.warn('[WebShell] Canvas unavailable, using DOM renderer:', e.message);
  }

  fitAddon = new FitAddon();
  term.loadAddon(fitAddon);
  term.loadAddon(new WebLinksAddon());

  term.open(terminalContainer.value);
  fitAddon.fit();
  setTimeout(() => term.focus(), 100);
}

// ---------------------------------------------------------------------------
// WebSocket 连接 — 指数退避重连 + 客户端心跳
// ---------------------------------------------------------------------------

// 输入缓冲：WebSocket 未就绪时暂存，连上后批量发送
let inputBuffer = '';
let busyDialogShown = false;

function connect() {
  if (busyDialogShown) return;
  if (wsRef && (wsRef.readyState === WebSocket.OPEN || wsRef.readyState === WebSocket.CONNECTING)) return;

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/shell/${props.sessionId}`);
  ws.binaryType = 'arraybuffer';
  wsRef = ws;

  ws.onopen = () => {
    console.log('[WebShell] connected');
    connected.value = true;
    busy.value = false;
    busyDialogShown = false;
    reconnectDelay = 1000;  // 重置退避
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    // 发送终端尺寸
    ws.send(JSON.stringify({ type: 'resize', rows: term.rows, cols: term.cols }));
    // 刷新缓冲的输入
    if (inputBuffer.length > 0) {
      ws.send(JSON.stringify({ type: 'input', data: inputBuffer }));
      inputBuffer = '';
    }
    // 启动客户端心跳
    startPing();
  };

  ws.onmessage = (evt) => {
    if (evt.data instanceof ArrayBuffer) {
      term.write(new Uint8Array(evt.data));
    } else {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === 'ping') return;
        if (msg.type === 'pong') { resetPongTimeout(); return; }
        if (msg.type === 'forbidden') {
          denied.value = true;
          connected.value = false;
          term.write(`\r\n\x1b[31m[${msg.message}]\x1b[0m\r\n`);
          closeWs();
          return;
        }
        if (msg.type === 'session_busy') {
          busyClient.value = msg.client || '';
          busyDialogShown = true;
          dialog.warning({
            title: '终端被占用',
            content: msg.message || '此终端正在另一个界面使用中',
            positiveText: '确认抢占',
            negativeText: '取消',
            closable: false,
            closeOnEsc: false,
            maskClosable: false,
            onPositiveClick: () => {
              if (wsRef && wsRef.readyState === WebSocket.OPEN) {
                wsRef.send(JSON.stringify({ type: 'supplant' }));
              }
            },
            onNegativeClick: () => {
              busy.value = true;
              busyDialogShown = false;
              closeWs();
              connected.value = false;
            },
          });
          return;
        }
        if (msg.type === 'supplanted') {
          connected.value = false;
          term.write(`\r\n\x1b[33m[${msg.message}]\x1b[0m\r\n`);
          closeWs();
          return;
        }
        if (msg.type === 'disconnected') {
          busyDialogShown = false;
          connected.value = false;
          term.write('\r\n\x1b[33m[进程已退出]\x1b[0m\r\n');
        }
      } catch {
        term.write(evt.data);
      }
    }
  };

  ws.onclose = (evt) => {
    stopPing();
    wsRef = null;
    if (denied.value) return;
    if (evt.code === 4403) {
      denied.value = true;
      connected.value = false;
      term.write('\r\n\x1b[31m[访问被拒绝：仅允许本机访问]\x1b[0m\r\n');
      return;
    }
    console.log(`[WebShell] disconnected, reconnecting in ${reconnectDelay}ms...`);
    connected.value = false;
    reconnectTimer = setTimeout(() => {
      connect();
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
    }, reconnectDelay);
  };
}

function closeWs() {
  stopPing();
  if (wsRef) {
    wsRef.onclose = null;
    wsRef.close();
    wsRef = null;
  }
}

// ---- 客户端心跳：每 20s ping，pong 超时 10s 则重连 ----
function startPing() {
  stopPing();
  pingTimer = setInterval(() => {
    if (wsRef && wsRef.readyState === WebSocket.OPEN) {
      wsRef.send(JSON.stringify({ type: 'ping' }));
      // pong 超时 → 断开重连
      pongTimeout = setTimeout(() => {
        console.log('[WebShell] pong timeout, reconnecting...');
        closeWs();
        connected.value = false;
        connect();
      }, 10000);
    }
  }, 20000);
}

function resetPongTimeout() {
  if (pongTimeout) { clearTimeout(pongTimeout); pongTimeout = null; }
}

function stopPing() {
  if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
  resetPongTimeout();
}

// ---------------------------------------------------------------------------
// 键盘输入 — PTY 原生处理所有按键，前端只负责透传
// ---------------------------------------------------------------------------
function setupInput() {
  term.onData((data) => {
    if (denied.value) return;
    if (wsRef && wsRef.readyState === WebSocket.OPEN) {
      wsRef.send(JSON.stringify({ type: 'input', data }));
    } else {
      // 缓冲输入，限制上限防止内存泄漏
      if (inputBuffer.length < MAX_INPUT_BUFFER) {
        inputBuffer += data;
      }
      if (!wsRef || wsRef.readyState > WebSocket.OPEN) {
        connect();
      }
    }
  });

  // Ctrl+Shift+C 复制
  term.attachCustomKeyEventHandler((e) => {
    if (e.ctrlKey && e.shiftKey && (e.key === 'C' || e.key === 'c')) {
      const sel = term.getSelection();
      if (sel) {
        navigator.clipboard.writeText(sel).catch(() => {});
        term.clearSelection();
      }
      return false;
    }
    // Ctrl+Shift+V 粘贴
    if (e.ctrlKey && e.shiftKey && (e.key === 'V' || e.key === 'v')) {
      navigator.clipboard.readText().then((text) => {
        if (wsRef && wsRef.readyState === WebSocket.OPEN) {
          wsRef.send(JSON.stringify({ type: 'input', data: text }));
        }
      }).catch(() => {});
      return false;
    }
    return true;
  });

  // 右键：选中时复制，未选中时粘贴
  term.element.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    const sel = term.getSelection();
    if (sel) {
      navigator.clipboard.writeText(sel).catch(() => {});
      term.clearSelection();
    } else {
      navigator.clipboard.readText().then((text) => {
        if (wsRef && wsRef.readyState === WebSocket.OPEN) {
          wsRef.send(JSON.stringify({ type: 'input', data: text }));
        }
      }).catch(() => {});
    }
  });
}

// ---------------------------------------------------------------------------
// 聚焦
// ---------------------------------------------------------------------------
function focusTerminal() {
  term?.focus();
}

function supplant() {
  busy.value = false;
  busyDialogShown = false;
  connect();
}

// 窗口自适应
let _fitTimer = null;

function doFit() {
  const el = terminalContainer.value;
  if (!el || el.clientWidth === 0 || el.clientHeight === 0) return;
  fitAddon?.fit();
  term?.scrollToBottom();
  if (term && term.rows > 0) term.refresh(0, term.rows - 1);
  _notifyResize();
}

// 仅防抖服务端 resize 通知
function _notifyResize() {
  if (_fitTimer) clearTimeout(_fitTimer);
  _fitTimer = setTimeout(() => {
    if (wsRef && wsRef.readyState === WebSocket.OPEN && term) {
      wsRef.send(JSON.stringify({ type: 'resize', rows: term.rows, cols: term.cols }));
    }
  }, 150);
}

function setupResize() {
  resizeObserver = new ResizeObserver(() => {
    const el = terminalContainer.value;
    if (!el || el.clientWidth === 0 || el.clientHeight === 0) return;
    fitAddon?.fit();
    term?.scrollToBottom();
    if (term && term.rows > 0) term.refresh(0, term.rows - 1);
    _notifyResize();
  });
  resizeObserver.observe(terminalContainer.value);
}

// 父组件触发：打开面板、切换 tab 时重新适配
watch(() => props.fitTrigger, () => {
  setTimeout(() => doFit(), props.embedded ? 150 : 0);
});

// ---------------------------------------------------------------------------
// 生命周期
// ---------------------------------------------------------------------------
// 父组件触发断开连接（保留 PTY，停止重连）
watch(() => props.disconnectVer, () => {
  busyDialogShown = true;
  closeWs();
  connected.value = false;
});

// 状态变化通知父组件
watch([connected, denied], () => {
  emit('status-change', {
    sessionId: props.sessionId,
    connected: connected.value,
    denied: denied.value,
  });
});

onMounted(() => {
  initTerminal();
  setupInput();
  setupResize();
  connect();
});

onBeforeUnmount(() => {
  if (_fitTimer) clearTimeout(_fitTimer);
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  if (resizeObserver) {
    try { resizeObserver.disconnect(); } catch (e) { /* ignore */ }
    resizeObserver = null;
  }
  stopPing();
  if (wsRef) {
    try { wsRef.onclose = null; wsRef.close(); } catch (e) { /* ignore */ }
    wsRef = null;
  }
  if (term) {
    try { term.dispose(); } catch (e) { /* ignore */ }
    term = null;
  }
});
</script>

<style scoped>
.webshell-wrapper {
  position: relative;
}
.webshell-wrapper.embedded {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.webshell-container {
  width: 100%;
  height: calc(100vh - 13px);
  min-height: 400px;
  overflow: hidden;
  border-radius: 6px;
}
.webshell-container.embedded {
  flex: 1;
  min-height: 0;
  border-radius: 0;
}
.webshell-status {
  position: absolute;
  top: 4px;
  right: 8px;
  z-index: 10;
  padding: 2px 10px;
  font-size: 12px;
  font-family: monospace;
  border-radius: 0 0 0 6px;
  transition: all .3s;
  pointer-events: none;
}
.webshell-inner {
  position: relative;
  flex: 1;
  min-height: 0;
}
/* 嵌入模式：inner 变成 flex 容器 + terminalContainer 用 flex:1 撑满 */
.webshell-wrapper.embedded .webshell-inner {
  display: flex;
  flex-direction: column;
}
.busy-overlay {
  position: absolute; inset: 0; z-index: 5;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px;
  background: rgba(0,0,0,.65);
  color: #8b949e; font-size: 14px;
}
.busy-client {
  font-size: 12px; color: #484f58; font-family: monospace;
}
.busy-actions {
  display: flex; gap: 12px; margin-top: 8px;
}
.busy-btn {
  padding: 6px 18px;
  background: #238636; color: #fff;
  border-radius: 6px;
  font-size: 13px; cursor: pointer;
  transition: background .15s;
}
.busy-btn:hover { background: #2ea043; }

.reconnect-badge {
  position: absolute; top: 8px; right: 8px; z-index: 5;
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  background: #21262d; color: #8b949e;
  border: 1px solid #30363d;
  border-radius: 50%;
  font-size: 14px; cursor: pointer;
  transition: all .15s;
}
.reconnect-badge:hover {
  background: #238636; color: #fff;
  border-color: #238636;
}

.webshell-status.connected {
  background: #1a3a1a;
  color: #4f4;
}
.webshell-status:not(.connected):not(.denied) {
  background: #3a1a1a;
  color: #f44;
}
.webshell-status.denied {
  background: #3a1a00;
  color: #fa0;
}
</style>
