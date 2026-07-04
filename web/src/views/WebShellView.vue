<template>
  <div class="mgmt-page">
    <div class="mgmt-header">
      <span class="mgmt-title">终端管理</span>
      <n-tag type="info" size="small">仅本机</n-tag>
      <span style="flex:1"></span>
      <n-button size="small" type="primary" @click="store.create()">
        <template #icon><AddOutline /></template>
        新建终端
      </n-button>
    </div>

    <!-- 按窗口分组 -->
    <template v-for="(group, gid) in groups" :key="gid">
      <div class="group-label">{{ gid === store.winId ? '本窗口' : gid === '?' ? '其他' : '窗口 ' + gid }}</div>
      <div class="mgmt-grid">
        <div
          v-for="s in group"
          :key="s.id"
          class="mgmt-card"
          :class="{ active: s.id === store.activeId.value }"
        >
          <div class="card-head">
            <span class="card-dot" :class="s.connected ? 'on' : (s.alive ? 'alive' : 'off')"></span>
            <code class="card-id">{{ s.id }}</code>
            <n-button size="tiny" quaternary type="error" @click="store.remove(s.id)">删除</n-button>
          </div>
          <div class="card-body">
            <div class="card-row">
              <span class="lbl">状态</span>
              <span :class="s.connected ? 'green' : (s.alive ? 'yellow' : 'gray')">
                {{ s.connected ? '已连接' : (s.alive ? '进程存活' : '已断开') }}
              </span>
            </div>
            <div class="card-row" v-if="s.client">
              <span class="lbl">客户端</span>
              <span>{{ s.client }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <div class="mgmt-empty" v-if="store.sessions.value.length === 0">
      暂无终端会话
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue';
import { NButton, NTag } from 'naive-ui';
import { AddOutline } from '@vicons/ionicons5';
import { useShellStore } from '@/composables/useShellStore';

const store = useShellStore();

// 按窗口分组
const groups = computed(() => {
  const map = {};
  for (const s of store.sessions.value) {
    const wid = s._win || '?';
    if (!map[wid]) map[wid] = [];
    map[wid].push(s);
  }
  return map;
});

onMounted(() => {
  store.restore();
});
</script>

<style scoped>
.mgmt-page { min-height: calc(100vh - 120px); }
.mgmt-header { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.mgmt-title { font-size: 18px; font-weight: 600; color: #e6edf3; }
.group-label {
  font-size: 12px; color: #484f58;
  padding: 4px 0; margin: 8px 0 4px;
  border-bottom: 1px solid #21262d;
}
.mgmt-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 8px; margin-bottom: 12px; }
.mgmt-card {
  background: #161b22; border: 1px solid #21262d; border-radius: 6px;
  padding: 10px; transition: border-color .15s;
}
.mgmt-card:hover { border-color: #30363d; }
.mgmt-card.active { border-color: #1f6feb; }
.card-head { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.card-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.card-dot.on    { background: #3fb950; box-shadow: 0 0 5px #3fb95088; }
.card-dot.alive { background: #d29922; box-shadow: 0 0 5px #d2992288; }
.card-dot.off   { background: #6e7681; }
.card-id { font-size: 11px; color: #58a6ff; flex: 1; font-family: monospace; }
.card-body { font-size: 12px; }
.card-row { display: flex; gap: 8px; line-height: 1.6; }
.card-row .lbl { color: #484f58; width: 40px; flex-shrink: 0; }
.green  { color: #3fb950; }
.yellow { color: #d29922; }
.gray   { color: #6e7681; }
.mgmt-empty { text-align: center; padding: 48px; color: #8b949e; }
</style>
