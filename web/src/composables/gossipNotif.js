import { ref } from 'vue';

export const gossipNotifications = ref([]);
export const gossipBssidMap = ref([]);
export const gossipPeers = ref([]);
export const gossipLocalInfo = ref({ hostname: '', ip: '', ssid: '', bssid: '', rx_rate: 0, tx_rate: 0, signal: 0, rssi: 0, web_port: 0, version: '', build_time: '', git_hash: '', node_id: '' });
export const gossipWsStatus = ref('disconnected'); // 'connecting' | 'connected' | 'disconnected'
export const pagePaths = ref([]); // [{ip, client_id, path, sender, timestamp}]
export let gossipWs = null;
let _manualDisconnect = false;
let _onNewCallback = null;
let _pendingMessages = []; // WebSocket 未就绪时暂存的消息

// 每个标签页唯一 ID，用于区分同 IP 的不同 tab
const _clientId = crypto.randomUUID?.() || Math.random().toString(36).substr(2, 9);

export function connectGossipWs(onNew) {
  if (onNew) _onNewCallback = onNew;

  // 避免重复创建连接
  if (gossipWs) {
    if (gossipWs.readyState === WebSocket.OPEN || gossipWs.readyState === WebSocket.CONNECTING) {
      gossipWsStatus.value = 'connected';
      return;
    }
    // 旧连接已失效，清理后重新创建
    gossipWs = null;
  }

  _manualDisconnect = false;
  gossipWsStatus.value = 'connecting';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/gossip`;
  gossipWs = new WebSocket(wsUrl);
  gossipWs.onopen = () => {
    gossipWsStatus.value = 'connected';
    // 发送积压消息
    for (const msg of _pendingMessages) {
      gossipWs.send(msg);
    }
    _pendingMessages = [];
  };
  gossipWs.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'gossip_notification' && msg.data) {
        if (!gossipNotifications.value.some(n => n.id === msg.data.id)) {
          gossipNotifications.value.unshift(msg.data);
          if (gossipNotifications.value.length > 50) {
            gossipNotifications.value = gossipNotifications.value.slice(0, 50);
          }
          if (_onNewCallback) _onNewCallback(msg.data);
        }
      } else if (msg.type === 'page_path_update' && msg.data) {
        const { ip, client_id, path, sender, timestamp } = msg.data;
        // 用 client_id 区分同 IP 的不同标签页
        const key = client_id || ip;
        const idx = pagePaths.value.findIndex(p => (p.client_id || p.ip) === key && p.sender === sender);
        if (idx >= 0) {
          pagePaths.value[idx] = { ip, client_id, path, sender, timestamp };
        } else {
          pagePaths.value.push({ ip, client_id, path, sender, timestamp });
        }
      } else if (msg.type === 'bssid_map_update' && msg.data) {
        gossipBssidMap.value = msg.data.entries || [];
      } else if (msg.type === 'peer_list_update' && msg.data) {
        gossipPeers.value = msg.data.peers || [];
      } else if (msg.type === 'local_info_update' && msg.data) {
        gossipLocalInfo.value = msg.data;
      }
    } catch {}
  };
  gossipWs.onerror = () => {
    gossipWsStatus.value = 'disconnected';
  };
  gossipWs.onclose = () => {
    gossipWsStatus.value = 'disconnected';
    if (!_manualDisconnect) {
      setTimeout(() => connectGossipWs(), 5000);
    }
  };
}

// 页面可见性变化时自动重连（解决后台标签页 WebSocket 断连后重连不及时的问题）
function _onVisibilityChange() {
  if (document.visibilityState === 'visible') {
    const needReconnect = !gossipWs || gossipWs.readyState === WebSocket.CLOSED || gossipWs.readyState === WebSocket.CLOSING
    if (needReconnect) {
      connectGossipWs()
    }
  }
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', _onVisibilityChange)
}

export function disconnectGossipWs() {
  _manualDisconnect = true;
  if (gossipWs) {
    gossipWs.close();
    gossipWs = null;
  }
}

export function reconnectGossipWs() {
  _manualDisconnect = false;
  if (gossipWs) {
    gossipWs.close();
    gossipWs = null;
  }
  connectGossipWs();
}

export function sendPagePath(path) {
  const msg = JSON.stringify({ type: 'page_path', path, client_id: _clientId });
  if (gossipWs && gossipWs.readyState === WebSocket.OPEN) {
    gossipWs.send(msg);
  } else {
    // WebSocket 未就绪，暂存起来等 onopen 时发送
    _pendingMessages.push(msg);
  }
}
