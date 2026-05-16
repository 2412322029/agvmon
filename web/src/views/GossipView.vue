<script setup>
import {
  NBadge,
  NButton,
  NCard,
  NDataTable,
  NDivider,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NPopconfirm,
  NSpace,
  NTag,
  NText,
  useMessage
} from 'naive-ui';
import { UAParser } from 'ua-parser-js';
import { computed, h, ref } from 'vue';
import { gossipBssidMap, gossipLocalInfo, gossipNotifications, gossipPeers } from '../composables/gossipNotif';
const parseUA = (uaString) => {
  if (!uaString) return { browser: '未知', os: '未知', device: '未知' }
  const parser = new UAParser(uaString)
  const browser = parser.getBrowser()
  const os = parser.getOS()
  const device = parser.getDevice()
  let browser_str = browser.name ? `${browser.name} ${browser.version}` : '未知'
  let os_str = os.name ? `${os.name} ${os.version}` : '未知'
  return `${os_str} | ${browser_str}`
}
const message = useMessage();
const localInfo = gossipLocalInfo;
const peers = gossipPeers;
const count = computed(() => peers.value.length);

// ---- 通知广播 ----
const notifyMessage = ref('');

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString();
}

function sendNotification() {
  const text = notifyMessage.value.trim();
  if (!text) return;
  fetch('/api/gossip/notify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text }),
  }).catch(() => { });
  notifyMessage.value = '';
}

// ---- 对等节点表格列 ----
const peerColumns = [
  {
    title: '主机名/IP', key: 'hostname', width: 170,
    render(row) {
      if (row.ip && row.web_port) {
        const url = `http://${row.ip}:${row.web_port}`;
        return h('a', {
          href: url,
          target: '_blank',
          style: { color: '#1890ff', textDecoration: 'none', fontSize: '12px' },
          title: `打开 ${row.hostname} 的 Web 界面`,
        }, `${row.hostname} (${row.ip})`);
      }
      return h('span', { style: { fontSize: '12px' } }, `${row.hostname} (${row.ip})`);
    }
  },
  { title: 'SSID', key: 'ssid', width: 130 },
  { title: 'BSSID', key: 'bssid', width: 150, render(row) { return h('code', { style: { fontSize: '11px' } }, row.bssid); } },
  { title: '位置', key: 'signal', width: 125, render(row) { return bssidLabel(row.bssid) ? `${bssidLabel(row.bssid)}` : '-'; } },
  { title: 'RSSI', key: 'rssi', width: 80, render(row) { return row.rssi ? `${row.rssi} dBm` : '-'; } },
  { title: '速率', key: 'rate', width: 85, render(row) { return `rx${row.rx_rate} tx${row.tx_rate}`; } },
  { title: '版本', key: 'version', width: 75 },
  { title: '构建时间', key: 'build_time', width: 130, render(row) { return row.build_time ? h('span', { style: { fontSize: '11px' } }, row.build_time) : '-'; } },
  { title: '延迟', key: 'age', width: 60, render(row) { return h(NTag, { type: row.age < 6 ? 'success' : row.age < 12 ? 'warning' : 'error', size: 'small', round: true }, { default: () => `${row.age}s` }); } },
];

// ---- BSSID 位置映射 ----
const showBssidModal = ref(false);
const bssidForm = ref({ bssid: '', location: '', notes: '' });

const bssidColumns = [
  {
    title: 'BSSID', key: 'bssid', width: 160,
    render(row) { return h('code', { style: { fontSize: '11px' } }, row.bssid); }
  },
  { title: '楼层/位置', key: 'location', width: 150 },
  { title: '备注', key: 'notes', width: 200 },
  { title: '更新者', key: 'updated_by', width: 100 },
  {
    title: '更新时间', key: 'updated_at', width: 160,
    render(row) { return row.updated_at ? new Date(row.updated_at * 1000).toLocaleString() : '-'; }
  },
  {
    title: '操作', key: 'actions', width: 140,
    render(row) {
      return h('div', { style: { display: 'flex', gap: '4px' } }, [
        h(NButton, { size: 'tiny', onClick: () => editBssidEntry(row) }, { default: () => '编辑' }),
        h(NPopconfirm, { onPositiveClick: () => deleteBssidEntry(row.bssid) }, {
          default: () => '确认删除?',
          trigger: () => h(NButton, { size: 'tiny', type: 'error' }, { default: () => '删除' }),
        }),
      ]);
    }
  },
];

function editBssidEntry(row) {
  bssidForm.value = { bssid: row.bssid, location: row.location, notes: row.notes };
  showBssidModal.value = true;
}

async function saveBssidEntry() {
  if (!bssidForm.value.bssid.trim() || !bssidForm.value.location.trim()) return;
  try {
    await fetch('/api/gossip/bssid-map', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bssidForm.value),
    });
    showBssidModal.value = false;
    bssidForm.value = { bssid: '', location: '', notes: '' };
  } catch { }
}

async function deleteBssidEntry(bssid) {
  try {
    await fetch(`/api/gossip/bssid-map/${encodeURIComponent(bssid)}`, { method: 'DELETE' });
  } catch { }
}

// ---- 拓扑数据 ----
const localClients = computed(() => localInfo.value.extra?.clients || []);

// BSSID → 位置/备注 快速查找
const bssidLookup = computed(() => {
  const m = {};
  for (const e of gossipBssidMap.value) {
    m[e.bssid] = e;
  }
  return m;
});

function bssidLabel(bssid) {
  const e = bssidLookup.value[bssid];
  if (!e) return '';
  return e.notes ? `${e.location} — ${e.notes}` : e.location;
}
</script>

<template>
  <div class="gossip-container">
    <div class="hero">
      <h2>局域网</h2>
      <n-text depth="2" class="subtitle">
        Gossip(流言传播)基于 UDP 广播的局域网节点自动发现 — 每 3 秒广播自身信息，无中心服务器依赖
      </n-text>
    </div>

    <n-divider />

    <!-- 本机信息 -->
    <n-card size="small">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>本机</span>
          <n-tag size="tiny" type="info" round>{{ localInfo.version || '-' }}</n-tag>
        </div>
      </template>
      <div class="local-info-inline">
        <span class="li-item"><strong>{{ localInfo.hostname }}</strong></span>
        <span class="li-sep"> | </span>
        <span class="li-item"><code>{{ localInfo.ip }}:{{ localInfo.web_port }}</code></span>
        <span class="li-sep"> | </span>
        <span class="li-item">SSID {{ localInfo.ssid || '-' }}</span>
        <span class="li-sep"> | </span>
        <span class="li-item" :title="bssidLabel(localInfo.bssid) || undefined">
          BSSID <code>{{ localInfo.bssid || '-' }}</code>
          <template v-if="bssidLabel(localInfo.bssid)"><span class="li-loc">({{ bssidLabel(localInfo.bssid)
              }})</span></template>
        </span>
        <span class="li-sep"> | </span>
        <span class="li-item">{{ localInfo.signal ? `信号 ${localInfo.signal}%` : '-' }}</span>
        <span class="li-sep"> | </span>
        <span class="li-item">{{ localInfo.rssi ? `${localInfo.rssi} dBm` : '-' }}</span>
        <span class="li-sep"> | </span>
        <span class="li-item">rx{{ localInfo.rx_rate }} tx{{ localInfo.tx_rate }}</span>
        <span class="li-sep"> | </span>
        <span class="li-item"
          :title="`节点ID: ${localInfo.node_id}\n构建: ${localInfo.build_time || '-'}\nGit: ${localInfo.git_hash || '-'}`">
          版本 {{ localInfo.version || '-' }}
        </span>
      </div>
    </n-card>

    <n-divider />

    <!-- 在线节点 -->
    <n-card size="small">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>在线节点</span>
          <n-badge :value="count" :max="99" type="success" />
        </div>
      </template>
      <n-dataTable v-if="peers.length" :columns="peerColumns" :data="peers" size="small" :bordered="false"
        :row-key="(row) => row.node_id" max-height="500" />
      <n-text v-else depth="3" style="padding: 24px; display: block; text-align: center;">
        暂无其他节点，等待广播...
      </n-text>
    </n-card>

    <n-divider />





    <!-- 完整拓扑（树形图） -->
    <n-card size="small" title="完整拓扑">
      <div class="topology-tree">
        <!-- 本机 -->
        <div class="tree-branch">
          <div class="tree-node-head">
            <n-tag type="info" size="small" round>本机</n-tag>
            <strong>{{ localInfo.hostname }}</strong>
            <code class="tree-addr">{{ localInfo.ip }}{{ localInfo.web_port ? ':' + localInfo.web_port : '' }}</code>
            [位于 {{ bssidLabel(localInfo.bssid) || '-' }}]
          </div>
          <div v-if="localClients.length" class="tree-children">
            <div v-for="(c, i) in localClients" :key="'lc-' + i" class="tree-item">
              <n-tag size="tiny" type="warning" round>客户端</n-tag>
              <code>{{ c.ip }}</code>
              <span class="tree-ua" :title="c.ua || '-'">
                {{ parseUA(c.ua) || '-' }}
              </span>
              <span class="tree-time">{{ formatTime(c.connected_at) }}</span>
            </div>
          </div>
        </div>
        <!-- 对等节点（平级） -->
        <div v-for="p in peers" :key="p.node_id" class="tree-branch">
          <div class="tree-node-head">
            <n-tag type="success" size="small" round>节点</n-tag>
            <strong>{{ p.hostname }}</strong>
            <code class="tree-addr">{{ p.ip }}{{ p.web_port ? ':' + p.web_port : '' }}</code>
            [位于 {{ bssidLabel(localInfo.bssid) || '-' }}]
            <n-tag :type="p.age < 6 ? 'success' : p.age < 12 ? 'warning' : 'error'" size="tiny" round>{{ p.age
              }}s</n-tag>
          </div>
          <div v-if="(p.extra?.clients || []).length" class="tree-children">
            <div v-for="(c, i) in (p.extra?.clients || [])" :key="'pc-' + i" class="tree-item">
              <n-tag size="tiny" type="warning" round>客户端</n-tag>
              <code>{{ c.ip }}</code>
              <span class="tree-ua" :title="c.ua || '-'">
                {{ parseUA(c.ua) || '-' }}
              </span>
              <span class="tree-time">{{ formatTime(c.connected_at) }}</span>
            </div>
          </div>
        </div>
      </div>
      <n-text v-if="!localInfo.hostname && !peers.length" depth="3"
        style="text-align: center; display: block; padding: 16px;">
        等待节点数据...
      </n-text>
    </n-card>

    <n-divider />

    <!-- BSSID 位置映射 -->
    <n-card size="small" title="BSSID 位置映射">
      <n-button size="small" type="primary"
        @click="showBssidModal = true; bssidForm = { bssid: '', location: '', notes: '' };" style="margin-bottom: 8px;">
        添加映射
      </n-button>
      <n-dataTable v-if="gossipBssidMap.length" :columns="bssidColumns" :data="gossipBssidMap" size="small"
        :bordered="false" :row-key="(row) => row.bssid" max-height="400" />
      <n-text v-else depth="3" style="text-align: center; display: block; padding: 16px;">
        暂无映射，点击"添加映射"开始 — 数据会自动同步到其他节点
      </n-text>
    </n-card>

    <!-- 添加/编辑 BSSID 映射对话框 -->
    <n-modal v-model:show="showBssidModal" preset="card" title="BSSID 位置映射" style="width: 500px;">
      <n-form>
        <n-form-item label="BSSID" required>
          <n-input v-model:value="bssidForm.bssid" placeholder="例如: EA:4D:F5:A0:8B:E5" />
        </n-form-item>
        <n-form-item label="楼层/位置" required>
          <n-input v-model:value="bssidForm.location" placeholder="例如: L10, 3楼仓库" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="bssidForm.notes" placeholder="可选备注信息" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showBssidModal = false">取消</n-button>
          <n-button type="primary" @click="saveBssidEntry">保存</n-button>
        </n-space>
      </template>
    </n-modal>
    <n-divider />
    <!-- 通知广播 -->
    <n-card size="small" title="通知广播">
      <div style="display: flex; gap: 8px; margin-bottom: 8px;">
        <n-input v-model:value="notifyMessage" placeholder="输入通知消息，将广播到所有节点..." @keydown.enter="sendNotification"
          style="flex: 1;" />
        <n-button type="primary" @click="sendNotification" :disabled="!notifyMessage.trim()">
          发送广播
        </n-button>
      </div>
      <n-text v-if="gossipNotifications.length === 0" depth="3"
        style="text-align: center; display: block; padding: 8px;">
        暂无通知
      </n-text>
      <div v-for="n in gossipNotifications.slice(0, 20)" :key="n.id"
        style="padding: 6px 8px; border-bottom: 1px solid var(--n-border-color); display: flex; justify-content: space-between; align-items: center;">
        <span><strong>{{ n.sender }}:</strong> {{ n.message }}</span>
        <span style="font-size: 11px; color: var(--n-text-3); flex-shrink: 0; margin-left: 12px;">{{
          formatTime(n.timestamp)
          }}</span>
      </div>
    </n-card>
  </div>
</template>

<style scoped>
.gossip-container {
  padding: 12px;
  max-width: 1100px;
}

.hero {
  margin-bottom: 8px;
}

.hero h2 {
  margin-bottom: 4px;
  font-size: 28px;
}

.hero .subtitle {
  display: block;
  font-size: 14px;
  line-height: 1.6;
}

/* ---- 拓扑树形图 ---- */
.topology-tree {
  font-size: 13px;
}

.tree-branch {
  margin: 0 0 10px;
}

.tree-node-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.tree-addr {
  font-size: 11px;
  color: var(--n-text-3);
}

.tree-children {
  margin-left: 14px;
  padding-left: 18px;
  border-left: 1px solid var(--n-border-color, #d0d0d0);
}

.tree-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  position: relative;
  font-size: 12px;
}

.tree-item::before {
  content: '';
  position: absolute;
  left: -18px;
  top: 50%;
  width: 14px;
  border-top: 1px solid var(--n-border-color, #d0d0d0);
}

.tree-ua {
  font-size: 11px;
  color: var(--n-text-3);
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-time {
  font-size: 10px;
  color: var(--n-text-3);
  flex-shrink: 0;
  margin-left: auto;
}
</style>
