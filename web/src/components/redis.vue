<template>
  <n-spin :show="loading" size="large" style="width:100%; display:flex; justify-content:center; padding:24px 0">
    <div style="width:100%">
      <div style="margin-top:12px; display:flex; gap:12px; align-items:flex-start; flex-wrap:wrap;">
        <n-card title="Redis 概览" style="flex:1; min-width:320px; margin-bottom: 10px;">
          <n-descriptions :column="2" size="small">
            <n-descriptions-item label="Redis 版本">{{ info?.redis_version ?? '-' }}</n-descriptions-item>
            <n-descriptions-item label="运行模式">{{ info?.redis_mode ?? '-' }}</n-descriptions-item>
            <n-descriptions-item label="启动时间">{{ info?.rdb_last_save_time ? formatDate(info.rdb_last_save_time * 1000) :
              '-' }}</n-descriptions-item>
            <n-descriptions-item label="运行天数">{{ info?.uptime_in_days ?? '-' }}</n-descriptions-item>
          </n-descriptions>
        </n-card>
      </div>
      <n-grid :x-gap="12" :y-gap="12" :cols="cols">
        <n-grid-item v-for="metric in metrics" :key="metric.key">
          <n-card size="small" :style="{ height: '100%', min_width: '220px' }">
            <div style="display:flex;flex-direction:column;gap:2px">
              <div style="font-size:12px;color:var(--n-typography-1)">{{ metric.label }}</div>
              <div style="font-size:18px;font-weight:600">{{ metric.value }}</div>
              <div style="font-size:12px;color:var(--n-typography-3)">{{ metric.hint }}</div>
            </div>
          </n-card>
        </n-grid-item>
      </n-grid>
      <n-alert v-if="err" type="error" :title="String(err)" style="margin-top:12px" />
    </div>
  </n-spin>
</template>

<script setup>
import axios from "axios";
import { NAlert, NCard, NDescriptions, NDescriptionsItem, NGrid, NGridItem, NSpin } from "naive-ui";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

const info = ref(null);
const loading = ref(true);
const err = ref("");
const cols = ref(3);
const get_redis = () => {
  return axios.get("/util/redis")
    .then((res) => res.data);
};
function updateCols() {
  const w = window.innerWidth;
  if (w < 300) cols.value = 1;
  else if (w < 600) cols.value = 2;
  else if (w < 1000) cols.value = 3;
  else if (w < 1200) cols.value = 4;
  else cols.value = 5;
}

onMounted(() => {
  updateCols();
  window.addEventListener("resize", updateCols);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", updateCols);
});
onMounted(async () => {
  try {
    info.value = await get_redis();
  } catch (e) {
    err.value = e?.message || e || "获取 Redis 信息失败";
  } finally {
    loading.value = false;
  }
});

const metrics = computed(() => {
  if (!info.value) return [];
  const i = info.value;
  const hitRate =
    (i.keyspace_hits && i.keyspace_misses)
      ? `${Math.round((i.keyspace_hits / (i.keyspace_hits + i.keyspace_misses)) * 10000) / 100}%`
      : "-";
  return [
    { key: "redis_version", label: "版本", value: i.redis_version ?? "-", hint: i.redis_git_sha1 ? `git: ${i.redis_git_sha1}` : "" },
    { key: "redis_mode", label: "运行模式", value: i.redis_mode ?? "-", hint: i.role ? `role: ${i.role}` : "" },
    { key: "arch_bits", label: "架构 (bits)", value: i.arch_bits ?? "-", hint: "" },
    { key: "os", label: "操作系统", value: i.os ?? "-", hint: "" },
    { key: "process_id", label: "进程 ID", value: i.process_id ?? "-", hint: "" },
    { key: "tcp_port", label: "端口", value: i.tcp_port ?? "-", hint: "" },
    { key: "configured_hz", label: "配置 HZ", value: i.configured_hz ?? i.hz ?? "-", hint: "" },

    { key: "uptime_days", label: "运行天数", value: i.uptime_in_days ?? "-", hint: `${i.uptime_in_seconds ?? 0}s` },
    { key: "rdb_last_save", label: "最近 RDB 保存", value: i.rdb_last_save_time ? formatDate(i.rdb_last_save_time * 1000) : "-", hint: `status: ${i.rdb_last_bgsave_status ?? '-'}` },

    { key: "aof", label: "AOF", value: i.aof_enabled ? "开启" : "关闭", hint: i.aof_enabled ? `last_rewrite: ${i.aof_last_rewrite_time_sec ?? '-'}` : "" },
    { key: "maxmemory", label: "最大内存", value: i.maxmemory_human ?? (i.maxmemory ? String(i.maxmemory) : "-"), hint: i.maxmemory ? `策略: ${i.maxmemory_policy}` : "" },
    { key: "total_system_memory", label: "系统内存", value: i.total_system_memory_human ?? (i.total_system_memory ?? "-"), hint: "" },

    { key: "used_memory", label: "使用内存", value: i.used_memory_human ?? i.used_memory ?? "-", hint: "" },
    { key: "used_memory_rss", label: "RSS 内存", value: i.used_memory_rss_human ?? i.used_memory_rss ?? "-", hint: `rss_overhead_ratio: ${i.rss_overhead_ratio ?? '-'}` },
    { key: "used_memory_peak", label: "内存峰值", value: i.used_memory_peak_human ?? i.used_memory_peak ?? "-", hint: "" },
    { key: "used_memory_lua", label: "Lua 内存", value: i.used_memory_lua_human ?? i.used_memory_lua ?? "-", hint: "" },
    { key: "used_memory_dataset", label: "数据集内存", value: i.used_memory_dataset ? `${i.used_memory_dataset} (${i.used_memory_dataset_perc ?? '-'})` : (i.used_memory_dataset_perc ?? "-"), hint: "" },

    { key: "mem_allocator", label: "内存分配器", value: i.mem_allocator ?? i.allocator ?? "-", hint: `allocator_resident: ${i.allocator_resident ?? '-'}` },
    { key: "mem_fragmentation", label: "内存碎片比率", value: i.mem_fragmentation_ratio ?? i.allocator_frag_ratio ?? "-", hint: i.mem_fragmentation_bytes ? `${i.mem_fragmentation_bytes} B` : "" },
    { key: "rss_overhead", label: "RSS 开销", value: i.rss_overhead_bytes ?? "-", hint: `ratio: ${i.rss_overhead_ratio ?? '-'}` },
    { key: "allocator_active", label: "分配器 active", value: i.allocator_active ?? "-", hint: `allocated: ${i.allocator_allocated ?? '-'}` },

    { key: "clients", label: "连接数", value: i.connected_clients ?? "-", hint: `blocked: ${i.blocked_clients ?? 0}` },
    { key: "connected_slaves", label: "从节点数", value: i.connected_slaves ?? "-", hint: "" },

    { key: "commands", label: "命令总数", value: i.total_commands_processed ?? "-", hint: "" },
    { key: "connections", label: "总连接数", value: i.total_connections_received ?? "-", hint: "" },
    { key: "instant_ops", label: "实时 OPS", value: i.instantaneous_ops_per_sec ?? "-", hint: "" },
    { key: "net_io", label: "网络 I/O", value: `${i.total_net_input_bytes ?? 0} / ${i.total_net_output_bytes ?? 0}`, hint: `in_kbps: ${i.instantaneous_input_kbps ?? 0}, out_kbps: ${i.instantaneous_output_kbps ?? 0}` },

    { key: "keys_db0", label: "DB0 Keys", value: (i.db0 && i.db0.keys) ? i.db0.keys : 0, hint: `expires: ${i.db0?.expires ?? 0}` },
    { key: "expired_keys", label: "过期 Keys", value: i.expired_keys ?? "-", hint: `expired_stale_perc: ${i.expired_stale_perc ?? '-'}` },
    { key: "evicted_keys", label: "驱逐 Keys", value: i.evicted_keys ?? "-", hint: "" },

    { key: "keyspace_hits", label: "Key 命中", value: i.keyspace_hits ?? 0, hint: "" },
    { key: "keyspace_misses", label: "Key 未命中", value: i.keyspace_misses ?? 0, hint: "" },
    { key: "hit_rate", label: "Key 命中率", value: hitRate, hint: `${i.keyspace_hits ?? 0} / ${i.keyspace_misses ?? 0}` },

    { key: "pubsub", label: "Pub/Sub", value: `${i.pubsub_channels ?? 0} chans / ${i.pubsub_patterns ?? 0} patterns`, hint: "" },
    { key: "scripts_cached", label: "缓存脚本数", value: i.number_of_cached_scripts ?? 0, hint: "" },

    { key: "fork_usec", label: "最近 Fork (usec)", value: i.latest_fork_usec ?? "-", hint: "" },

  ];
});

const prettyJson = computed(() => (info.value ? JSON.stringify(info.value, null, 2) : ""));

function formatDate(timestamp) {
  if (!timestamp) return "";
  const d = new Date(Number(timestamp));
  const pad = (n) => (n < 10 ? `0${n}` : n);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
</script>

<style scoped>
.json-pre {
  max-height: 420px;
  overflow: auto;
  background: var(--n-embedded-scrollbar-color, #f7f7f7);
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 适配暗色模式： */
:root {
  --card-bg: rgba(255, 255, 255, 0.6);
}
</style>