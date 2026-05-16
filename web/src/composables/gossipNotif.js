import { ref } from 'vue';

export const gossipNotifications = ref([]);
export const gossipBssidMap = ref([]);
export const gossipPeers = ref([]);
export const gossipLocalInfo = ref({ hostname: '', ip: '', ssid: '', bssid: '', rx_rate: 0, tx_rate: 0, signal: 0, rssi: 0, web_port: 0, version: '', build_time: '', git_hash: '', node_id: '' });
export let gossipWs = null;

export function connectGossipWs(onNew) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/gossip`;
  gossipWs = new WebSocket(wsUrl);
  gossipWs.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'gossip_notification' && msg.data) {
        if (!gossipNotifications.value.some(n => n.id === msg.data.id)) {
          gossipNotifications.value.unshift(msg.data);
          if (gossipNotifications.value.length > 50) {
            gossipNotifications.value = gossipNotifications.value.slice(0, 50);
          }
          if (onNew) onNew(msg.data);
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
  gossipWs.onclose = () => {
    setTimeout(() => connectGossipWs(onNew), 5000);
  };
}

export function disconnectGossipWs() {
  if (gossipWs) {
    gossipWs.close();
    gossipWs = null;
  }
}
