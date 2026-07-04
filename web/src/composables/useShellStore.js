/**
 * 全局终端会话状态
 * - 管理页 (/shell): 显示全部会话
 * - 浮窗 (ShellPanel): 只显示本窗口创建的会话
 *
 * 窗口归属：每个 tab 生成唯一 winId，创建的会话记录在 sessionStorage
 * 刷新页面后 winId 不变（同一 tab），可认领自己的会话
 */
import { ref } from 'vue';

// 窗口唯一 ID — 同一 tab 内刷新保持不变（sessionStorage）
const _storKey = 'webshell_win_id';
let _winId = sessionStorage.getItem(_storKey);
if (!_winId) {
  _winId = Math.random().toString(36).slice(2, 8);
  sessionStorage.setItem(_storKey, _winId);
}

// 本窗口创建的会话 ID 集合（刷新后从 sessionStorage 恢复）
const _myIdsKey = 'webshell_my_ids';
function _loadMyIds() {
  try { return new Set(JSON.parse(sessionStorage.getItem(_myIdsKey)) || []); } catch { return new Set(); }
}
function _saveMyIds() {
  try { sessionStorage.setItem(_myIdsKey, JSON.stringify([..._myIds])); } catch { /* */ }
}
const _myIds = _loadMyIds();

// 模块级状态
const sessions = ref([]);
const activeId = ref(null);
const panelOpen = ref(false);
const enabled = ref(true);
let _creating = false;
let _monitorWs = null;
let _statusChecked = false;
let _reconnectTimer = null;
let _reconnectDelay = 1000;  // 指数退避
const MAX_RECONNECT_DELAY = 15000;

function _filterMine(list) {
  return list.filter(s => _myIds.has(s.id));
}

export function useShellStore() {
  // ---- 监控 WebSocket — 指数退避重连 ----
  function _connectMonitor() {
    if (_monitorWs && (_monitorWs.readyState === WebSocket.OPEN || _monitorWs.readyState === WebSocket.CONNECTING)) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    _monitorWs = new WebSocket(`${proto}://${location.host}/ws/shell-monitor`);
    _monitorWs.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === 'sessions') {
          const oldMap = {};
          for (const s of sessions.value) { oldMap[s.id] = s; }
          const newList = (msg.sessions || []).map(s => {
            const old = oldMap[s.session_id];
            return {
              id: s.session_id,
              connected: s.connected || false,
              alive: s.alive,
              client: s.client || '',
              _win: old?._win || (_myIds.has(s.session_id) ? _winId : ''),
            };
          });
          // 补回本地已创建但后端广播还没来得及包含的
          for (const sid of _myIds) {
            if (!newList.find(s => s.id === sid)) {
              const old = oldMap[sid];
              if (old) newList.push({ ...old, alive: old.alive, connected: false });
            }
          }
          sessions.value = newList;
          // 保持活跃选中
          if (activeId.value && !sessions.value.find(s => s.id === activeId.value)) {
            const mine = _filterMine(sessions.value);
            activeId.value = mine.length > 0 ? mine[0].id : null;
          }
        }
      } catch { /* */ }
    };
    _monitorWs.onopen = () => {
      _reconnectDelay = 1000;  // 重置退避
    };
    _monitorWs.onclose = () => {
      _monitorWs = null;
      _reconnectTimer = setTimeout(() => {
        _connectMonitor();
        _reconnectDelay = Math.min(_reconnectDelay * 1.5, MAX_RECONNECT_DELAY);
      }, _reconnectDelay);
    };
  }

  async function checkEnabled() {
    if (_statusChecked) return;
    try {
      const resp = await fetch('/api/shell/status');
      const data = await resp.json();
      enabled.value = data.enabled !== false;
    } catch { enabled.value = false; }
    _statusChecked = true;
  }

  async function restore() {
    if (!enabled.value) return;
    // 从后端获取全量会话，仅用于显示，不篡改 _myIds
    try {
      const resp = await fetch('/api/shell/sessions');
      const data = await resp.json();
      const oldMap = {};
      for (const s of sessions.value) { oldMap[s.id] = s; }
      sessions.value = (data.sessions || []).map(s => ({
        id: s.session_id,
        connected: s.connected || false,
        alive: s.alive,
        client: s.client || '',
        _win: oldMap[s.session_id]?._win || (_myIds.has(s.session_id) ? _winId : ''),
      }));
      // 清理本地无主会话：_myIds 中的 ID 若在后端已不存在，移除
      const serverIds = new Set((data.sessions || []).map(s => s.session_id));
      let changed = false;
      for (const sid of [..._myIds]) {
        if (!serverIds.has(sid)) { _myIds.delete(sid); changed = true; }
      }
      if (changed) _saveMyIds();
    } catch { /* */ }
    _connectMonitor();
  }

  // ---- 创建（标记为本窗口所有，持久化到 sessionStorage） ----
  async function create() {
    if (!enabled.value || _creating) return;
    _creating = true;
    try {
      const resp = await fetch('/api/shell/sessions', { method: 'POST' });
      if (!resp.ok) return;
      const data = await resp.json();
      _myIds.add(data.session_id);
      _saveMyIds();
      // 乐观添加到本地列表
      const s = { id: data.session_id, connected: false, alive: true, client: '', _win: _winId };
      if (!sessions.value.find(x => x.id === s.id)) sessions.value.push(s);
      activeId.value = data.session_id;
      panelOpen.value = true;
    } finally { _creating = false; }
  }

  // ---- 删除 ----
  async function remove(sid) {
    const idx = sessions.value.findIndex(s => s.id === sid);
    if (idx !== -1 && activeId.value === sid) {
      const mine = _filterMine(sessions.value.filter((_, i) => i !== idx));
      activeId.value = mine.length > 0 ? mine[0].id : sessions.value.filter((_, i) => i !== idx)[0]?.id ?? null;
    }
    sessions.value = sessions.value.filter(s => s.id !== sid);
    _myIds.delete(sid);
    _saveMyIds();
    fetch(`/api/shell/sessions/${sid}`, { method: 'DELETE' }).catch(() => {});
  }

  function activate(sid) {
    activeId.value = sid;
    panelOpen.value = true;
  }

  function updateStatus(sid, status) {
    const s = sessions.value.find(s => s.id === sid);
    if (s) s.connected = status.connected && !status.denied;
  }

  async function toggle() {
    if (!panelOpen.value) {
      _connectMonitor();
      if (_creating) { await new Promise(r => setTimeout(r, 100)); }
      let mine = _filterMine(sessions.value);
      if (mine.length === 0 && !_creating) {
        await create();
        mine = _filterMine(sessions.value);
      }
      if (mine.length > 0) { activeId.value = mine[0].id; panelOpen.value = true; }
    } else {
      panelOpen.value = false;
    }
  }
  function open()  { panelOpen.value = true; }
  function close() { panelOpen.value = false; }

  return {
    sessions, activeId, panelOpen, enabled,
    winId: _winId,
    restore, checkEnabled, create, remove, activate, updateStatus,
    toggle, open, close,
  };
}
