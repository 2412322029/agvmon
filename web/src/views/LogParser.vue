<script setup>
import {
  NAutoComplete, NButton, NCard, NCheckbox, NCollapse, NCollapseItem, NDataTable,
  NDivider, NForm, NFormItem, NInput,
  NModal, NPopconfirm, NPagination, NRadioButton, NRadioGroup, NSelect, NSpace, NSpin, NTabPane,
  NTabs, NTag, NText, useMessage
} from 'naive-ui';
import { h, ref, watch } from 'vue';
import AGVProtocolParser from './AGVProtocolParser.js';

const message = useMessage();
const apiBase = '/api/log_parser';
const agvParser = new AGVProtocolParser();

// ── URL hash 同步（刷新保持当前 tab）─────────────────────────────────
import { useRoute, useRouter } from 'vue-router';
const route = useRoute();
const router = useRouter();

function parseHash() {
  const h = (route.hash || '#agv-download').replace('#', '');
  const [main, ...sub] = h.split('-');
  return { main: main || 'agv', sub: sub.join('-') || '' };
}
function updateHash(main, sub) {
  const h = sub ? `#${main}-${sub}` : `#${main}`;
  if (route.hash !== h) router.replace({ hash: h });
}

const { main: initMain, sub: initSub } = parseHash();
const mainTab = ref(initMain === 'clean' ? 'clean' : initMain === 'wcs' ? 'wcs' : 'agv');
const agvTab = ref(initMain === 'agv' ? (initSub || 'download') : 'download');
const wcsTab = ref(initMain === 'wcs' ? (initSub || 'local') : 'local');
const wcsRemoteSubTab = ref((initMain === 'wcs' && initSub === 'logbak') ? 'logbak' :
                              (initMain === 'wcs' && initSub === 'remote') ? 'remote' : 'default');

watch(mainTab, (v) => {
  if (v === 'agv') updateHash('agv', agvTab.value);
  else if (v === 'wcs') updateHash('wcs', wcsTab.value === 'logbak' ? 'logbak' : wcsTab.value === 'remote' ? 'remote' : 'local');
  else updateHash('clean', '');
});
watch(agvTab, (v) => { if (mainTab.value === 'agv') updateHash('agv', v); });
watch(wcsTab, (v) => {
  if (mainTab.value === 'wcs') {
    const sub = v === 'logbak' ? 'logbak' : v === 'remote' ? 'remote' : 'local';
    updateHash('wcs', sub);
  }
});

// ── AGV Logs state ────────────────────────────────────────────────────
const agvLocalFiles = ref([]);
const agvLocalLoading = ref(false);
const agvDownloading = ref(false);
const agvDownloadLogs = ref([]);
const agvDownloadFiles = ref([]);
const agvForm = ref({ ip_or_carid: '', count: 1, filenames: '', prefix: '/mnt/agv_log/' });
const agvRemoteFiles = ref([]);
const agvRemoteLoading = ref(false);
const agvSelectedFiles = ref([]);

// ── PIO 分析 state ────────────────────────────────────────────────────
const pioResult = ref(null);
const pioLoading = ref(false);
const pioDetailModal = ref(false);
const pioCurrentGroup = ref(null);
const pioSource = ref('remote');
const pioInfoMap = ['正常状态', '上仓位', '下仓位', '上料请求', '下料请求', '滚动信号', '完成信号', 'tray盘大小'];

// ── WCS Logs state ────────────────────────────────────────────────────
const wcsFiles = ref([]);
const wcsFilesLoading = ref(false);
const wcsParseResult = ref(null);
const wcsParsing = ref(false);
const wcsForm = ref({ filenames: [], shortcode: '', trayid: '', taskid: '', device_type: '' });
const deviceTypeOptions = ['Detector', 'Rotate', 'Pallet', 'Cargo', 'Lift', 'Door'];
const wcsDetailModal = ref(false);
const wcsDetailRow = ref(null);
const wcsDetailReq = ref(null);
const wcsDetailResp = ref(null);
const wcsDetailCollapse = ref(['resp']);
const wcsResultTab = ref('');

// ── WCS Remote state ───────────────────────────────────────────────────
const wcsRemoteFiles = ref([]);
const wcsRemoteLoading = ref(false);
const wcsRemotePage = ref(1);
const wcsRemotePageSize = ref(20);
const wcsRemoteTotal = ref(0);
const wcsRemoteSearch = ref('');
const wcsDownloading = ref(false);
const wcsDownloadLogs = ref([]);
const wcsDownloadFiles = ref([]);
const wcsSelectAll = ref(false);
const wcsProgress = ref({ filename: '', percentage: 0, downloaded_str: '', total_str: '' });

// log_bak remote (same download pipeline, separate list state)
const bakRemoteFiles = ref([]);
const bakRemoteLoading = ref(false);
const bakRemotePage = ref(1);
const bakRemotePageSize = ref(9);
const bakRemoteTotal = ref(0);
const bakRemoteSearch = ref('');
const bakSelectAll = ref(false);
const bakProgress = ref({ filename: '', percentage: 0, downloaded_str: '', total_str: '' });

// ── log_bak 本地解压 ─────────────────────────────────────────────────
const logbakLocalFiles = ref([]);
const logbakLocalLoading = ref(false);
const extractingFile = ref(null);       // currently extracting filename
const extractingLogs = ref([]);         // SSE log lines
const extractingProgress = ref({ current: 0, total: 0, percentage: 0 });

async function loadLocalLogbak() {
  logbakLocalLoading.value = true;
  try {
    const res = await fetch(`${apiBase}/clean/logbak`);
    const data = await res.json();
    logbakLocalFiles.value = (data.files || []).filter(f =>
      f.filename.endsWith('.tar.bz2') || f.filename.endsWith('.tar.gz') || f.filename.endsWith('.zip')
    );
  } catch (e) {
    message.error('加载 log_bak 文件列表失败');
  } finally {
    logbakLocalLoading.value = false;
  }
}

async function extractLogbak(filename) {
  extractingFile.value = filename;
  extractingLogs.value = [];
  extractingProgress.value = { current: 0, total: 0, percentage: 0 };
  const addLog = (text, type = 'info') => extractingLogs.value.push({ text, type, time: Date.now() });

  try {
    const res = await fetch(`${apiBase}/wcs_logs/logbak/extract`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(filename),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));
          if (event.type === 'status') {
            addLog(event.message);
            extractingProgress.value.total = event.total || 0;
          } else if (event.type === 'progress') {
            addLog(event.message, 'progress');
            extractingProgress.value = {
              current: event.current,
              total: event.total,
              percentage: event.percentage,
            };
          } else if (event.type === 'done') {
            addLog(event.message || `完成，共 ${event.count} 个文件`, 'success');
            message.success(`解压完成: ${event.count} 个文件 → wcslog/`);
            loadWcsFiles();
            loadCleanUsage();
          } else if (event.type === 'error') {
            addLog(event.message, 'error');
            message.error(event.message);
          }
        } catch (e) { /* ignore parse errors */ }
      }
    }
  } catch (e) {
    message.error('解压请求失败: ' + e.message);
  } finally {
    extractingFile.value = null;
  }
}

// ── Clean state ────────────────────────────────────────────────────────
const cleanTarget = ref('agvlog');
const cleanFiles = ref([]);
const cleanLoading = ref(false);
const cleanSelected = ref([]);

// ── AGV Local ─────────────────────────────────────────────────────────
async function loadAgvLocalFiles() {
  agvLocalLoading.value = true;
  try {
    const res = await fetch(`${apiBase}/agv_logs`);
    agvLocalFiles.value = await res.json();
  } catch (e) {
    message.error('加载AGV日志列表失败');
  } finally {
    agvLocalLoading.value = false;
  }
}

async function deleteLocalFile(filename) {
  try {
    const res = await fetch(`${apiBase}/agv_logs`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify([filename]),
    });
    const data = await res.json();
    if (res.ok) {
      message.success(`已删除 ${data.count} 个文件`);
      loadAgvLocalFiles();
    } else {
      message.error(data.detail || '删除失败');
    }
  } catch (e) {
    message.error('删除失败');
  }
}

async function deleteAllLocalFiles() {
  try {
    const res = await fetch(`${apiBase}/agv_logs`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: 'null',
    });
    const data = await res.json();
    if (res.ok) {
      message.success(`已删除 ${data.count} 个文件`);
      loadAgvLocalFiles();
    } else {
      message.error(data.detail || '删除失败');
    }
  } catch (e) {
    message.error('删除失败');
  }
}

// ── AGV Remote Files ─────────────────────────────────────────────────
async function loadAgvRemoteFiles() {
  if (!agvForm.value.ip_or_carid) {
    message.warning('请先输入AGV IP或carid');
    return;
  }
  agvRemoteLoading.value = true;
  agvSelectedFiles.value = [];
  try {
    const res = await fetch(`${apiBase}/agv_logs/remote_files`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(agvForm.value.ip_or_carid),
    });
    const data = await res.json();
    if (res.ok) {
      agvRemoteFiles.value = data.files || [];
      if (!agvRemoteFiles.value.length) message.warning('未找到AGV日志文件');
    } else {
      message.error(data.detail || '获取远程文件列表失败');
    }
  } catch (e) {
    message.error('获取远程文件列表失败: ' + e.message);
  } finally {
    agvRemoteLoading.value = false;
  }
}

// ── AGV Download (SSE) ─────────────────────────────────────────────────
async function downloadAgvLogs() {
  if (!agvForm.value.ip_or_carid) {
    message.warning('请输入AGV IP或carid');
    return;
  }
  if (!agvSelectedFiles.value.length) {
    message.warning('请选择要下载的文件');
    return;
  }
  agvDownloading.value = true;
  agvDownloadLogs.value = [];
  agvDownloadFiles.value = [];

  const filenames = [...agvSelectedFiles.value];

  const addLog = (text, type = 'info') => agvDownloadLogs.value.push({ text, type, time: Date.now() });

  try {
    const res = await fetch(`${apiBase}/agv_logs/download`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ip_or_carid: agvForm.value.ip_or_carid,
        filenames,
        prefix: '/mnt/agv_log/',
        count: filenames.length,
      }),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));
          if (event.type === 'status') {
            addLog(event.message);
          } else if (event.type === 'progress') {
            addLog(`${event.filename}: ${event.percentage}% (${event.downloaded_str}/${event.total_str})`, 'progress');
          } else if (event.type === 'done') {
            agvDownloadFiles.value = event.files || [];
            addLog(`完成，共下载 ${event.count} 个文件`, 'success');
            message.success(`下载完成: ${event.count} 个文件`);
          } else if (event.type === 'error') {
            addLog(event.message, 'error');
            message.error(event.message);
          }
        } catch (e) { /* ignore parse errors */ }
      }
    }
  } catch (e) {
    message.error('下载请求失败: ' + e.message);
  } finally {
    agvDownloading.value = false;
    loadAgvLocalFiles();
  }
}

// ── PIO 分析 (SSE) ────────────────────────────────────────────────────
async function runPioAnalysis() {
  if (!agvSelectedFiles.value.length) {
    message.warning('请选择要分析的文件');
    return;
  }
  pioLoading.value = true;
  pioResult.value = null;
  agvDownloadLogs.value = [];

  const filenames = [...agvSelectedFiles.value];

  const addLog = (text, type = 'info') => agvDownloadLogs.value.push({ text, type, time: Date.now() });

  const isLocal = pioSource.value === 'local';

  try {
    if (isLocal) {
      addLog('开始本地PIO分析 ...');
      const res = await fetch(`${apiBase}/agv_logs/pio_local`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(filenames),
      });
      const data = await res.json();
      if (res.ok) {
        if (data.pio_groups?.length) {
          pioResult.value = data.pio_groups;
          message.success(`PIO分析完成，共 ${data.count} 组`);
        }
        addLog(`分析完成，共 ${data.count} 组`, 'success');
      } else {
        message.error(data.detail || 'PIO分析失败');
        addLog(data.detail || 'PIO分析失败', 'error');
      }
    } else {
      const res = await fetch(`${apiBase}/agv_logs/pio`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ip_or_carid: agvForm.value.ip_or_carid,
          filenames,
          count: filenames.length,
        }),
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === 'status') {
              addLog(event.message);
            } else if (event.type === 'progress') {
              addLog(`${event.filename}: ${event.percentage}%`, 'progress');
            } else if (event.type === 'done') {
              if (event.pio_groups) {
                pioResult.value = event.pio_groups;
                message.success(`PIO分析完成，共 ${event.count} 组`);
              }
              addLog('分析完成', 'success');
            } else if (event.type === 'error') {
              addLog(event.message, 'error');
              message.error(event.message);
            }
          } catch (e) { /* ignore */ }
        }
      }
    }
  } catch (e) {
    message.error('PIO分析请求失败: ' + e.message);
  } finally {
    pioLoading.value = false;
    loadAgvLocalFiles();
  }
}

function formatSize(size) {
  if (!size && size !== 0) return '-';
  for (const unit of ['B', 'KB', 'MB', 'GB']) {
    if (size < 1024) return `${size.toFixed(1)} ${unit}`;
    size /= 1024;
  }
  return `${size.toFixed(1)} TB`;
}

function showPioDetail(group) {
  pioCurrentGroup.value = group;
  pioDetailModal.value = true;
}

function compareBits(resultBin, valueBin) {
  const r = resultBin.padStart(8, '0');
  const v = valueBin.padStart(8, '0');
  const rows = [];
  for (let i = 0; i < 8; i++) {
    const pos = 7 - i;
    rows.push({
      bit: pos,
      name: pioInfoMap[pos],
      result: r[i],
      value: v[i],
      match: r[i] === v[i],
    });
  }
  return rows.reverse();
}

// ── WCS ────────────────────────────────────────────────────────────────
async function loadWcsFiles() {
  wcsFilesLoading.value = true;
  try {
    const res = await fetch(`${apiBase}/wcs_logs/files`);
    if (!res.ok) throw new Error('请求失败');
    wcsFiles.value = await res.json();
  } catch (e) {
    message.error('加载WCS日志文件列表失败');
  } finally {
    wcsFilesLoading.value = false;
  }
}

async function parseWcsLog() {
  if (!wcsForm.value.filenames.length) {
    message.warning('请选择WCS日志文件');
    return;
  }
  wcsParsing.value = true;
  wcsParseResult.value = null;
  try {
    const body = { filenames: wcsForm.value.filenames };
    if (wcsForm.value.shortcode) body.shortcode = wcsForm.value.shortcode;
    if (wcsForm.value.trayid) body.trayid = wcsForm.value.trayid;
    if (wcsForm.value.taskid) body.taskid = wcsForm.value.taskid;
    if (wcsForm.value.device_type) body.device_type = wcsForm.value.device_type;
    const res = await fetch(`${apiBase}/wcs_logs/batch_parse`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (res.ok) {
      wcsParseResult.value = data;
      const files = Object.keys(data.results || {});
      if (files.length) wcsResultTab.value = files[0];
      const total = Object.values(data.results || {}).reduce((s, r) => s + (r.count || 0), 0);
      message.success(`解析完成，${files.length} 个文件，共 ${total} 条记录`);
    } else {
      message.error(data.detail || '解析失败');
    }
  } catch (e) {
    message.error('解析请求失败');
  } finally {
    wcsParsing.value = false;
  }
}

// ── WCS Remote (paginated) ─────────────────────────────────────────────
async function loadWcsRemoteFiles() {
  wcsRemoteLoading.value = true;
  try {
    const params = new URLSearchParams({
      page: wcsRemotePage.value,
      page_size: wcsRemotePageSize.value,
    });
    if (wcsRemoteSearch.value) params.set('search', wcsRemoteSearch.value);
    const res = await fetch(`${apiBase}/wcs_logs/remote?${params}`);
    if (!res.ok) throw new Error((await res.json()).detail || '请求失败');
    const data = await res.json();
    wcsRemoteTotal.value = data.total;
    wcsRemoteFiles.value = (data.items || []).map((f, i) => ({ ...f, _checked: false, _idx: i }));
    wcsSelectAll.value = false;
  } catch (e) {
    message.error('加载远程WCS文件列表失败: ' + e.message);
  } finally {
    wcsRemoteLoading.value = false;
  }
}

async function loadBakRemoteFiles() {
  bakRemoteLoading.value = true;
  try {
    const params = new URLSearchParams({
      page: bakRemotePage.value,
      page_size: bakRemotePageSize.value,
    });
    if (bakRemoteSearch.value) params.set('search', bakRemoteSearch.value);
    const res = await fetch(`${apiBase}/wcs_logs/logbak/remote?${params}`);
    if (!res.ok) throw new Error((await res.json()).detail || '请求失败');
    const data = await res.json();
    bakRemoteTotal.value = data.total;
    bakRemoteFiles.value = (data.items || []).map((f, i) => ({ ...f, _checked: false, _idx: i }));
    bakSelectAll.value = false;
  } catch (e) {
    message.error('加载log_bak文件列表失败: ' + e.message);
  } finally {
    bakRemoteLoading.value = false;
  }
}

function toggleWcsSelectAll(val) {
  wcsRemoteFiles.value.forEach(f => f._checked = val);
}

function toggleBakSelectAll(val) {
  bakRemoteFiles.value.forEach(f => f._checked = val);
}

function onWcsCheckChange() {
  const checked = wcsRemoteFiles.value.filter(f => f._checked);
  wcsSelectAll.value = checked.length === wcsRemoteFiles.value.length && wcsRemoteFiles.value.length > 0;
}

function onBakCheckChange() {
  const checked = bakRemoteFiles.value.filter(f => f._checked);
  bakSelectAll.value = checked.length === bakRemoteFiles.value.length && bakRemoteFiles.value.length > 0;
}

function onWcsRemotePageChange(page) {
  wcsRemotePage.value = page;
  loadWcsRemoteFiles();
}

function onBakRemotePageChange(page) {
  bakRemotePage.value = page;
  loadBakRemoteFiles();
}

async function downloadWcsLogs() {
  const isBak = wcsRemoteSubTab.value === 'logbak';
  const files = isBak ? bakRemoteFiles.value : wcsRemoteFiles.value;
  const selected = files.filter(f => f._checked);
  if (!selected.length) {
    message.warning('请先选择要下载的文件');
    return;
  }
  wcsDownloading.value = true;
  wcsDownloadLogs.value = [];
  wcsDownloadFiles.value = [];

  const addLog = (text, type = 'info') => wcsDownloadLogs.value.push({ text, type, time: Date.now() });
  const filenames = selected.map(f => f.filename);
  const progressRef = isBak ? bakProgress : wcsProgress;
  progressRef.value = { filename: '', percentage: 0, downloaded_str: '', total_str: '' };

  try {
    const res = await fetch(`${apiBase}/wcs_logs/download`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(filenames),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));
          if (event.type === 'status') {
            addLog(event.message);
            progressRef.value.filename = event.filename || progressRef.value.filename;
          } else if (event.type === 'progress') {
            progressRef.value = {
              filename: progressRef.value.filename,
              percentage: event.percentage,
              downloaded_str: event.downloaded_str,
              total_str: event.total_str,
            };
          } else if (event.type === 'done') {
            wcsDownloadFiles.value = event.success || [];
            const msg = `完成，成功 ${event.success?.length || 0} 个`;
            addLog(event.failed?.length ? `${msg}，失败 ${event.failed.length} 个` : msg, 'success');
            message.success(msg);
          } else if (event.type === 'error') {
            addLog(event.message, 'error');
            message.error(event.message);
          }
        } catch (e) { /* ignore parse errors */ }
      }
    }
  } catch (e) {
    message.error('下载请求失败: ' + e.message);
  } finally {
    wcsDownloading.value = false;
    files.forEach(f => f._checked = false);
    if (isBak) {
      bakSelectAll.value = false;
      loadBakRemoteFiles();
    } else {
      wcsSelectAll.value = false;
      loadWcsRemoteFiles();
    }
    loadWcsFiles();
  }
}

// ── 解析缓存 + 共享 hover 提示 (避免 virtual-scroll + NPopover 冲突) ──
const _parseCache = new Map();
function cachedParseAGV(hex) {
  if (!hex) return null;
  if (_parseCache.has(hex)) return _parseCache.get(hex);
  const r = agvParser.parseAGVCommand(hex);
  _parseCache.set(hex, r);
  return r;
}
function cachedParseEQ(hex) {
  if (!hex) return null;
  const key = 'eq:' + hex;
  if (_parseCache.has(key)) return _parseCache.get(key);
  const r = agvParser.parseEQStatus(hex);
  _parseCache.set(key, r);
  return r;
}

const hoverTip = ref({ show: false, raw: '', title: '', lines: [], highlight: '' });
let _hideTimer = null;

function _showTip(_e, raw, title, lines, highlight = '') {
  clearTimeout(_hideTimer);
  hoverTip.value = { show: true, raw, title, lines, highlight };
}
function _hideTip() {
  _hideTimer = setTimeout(() => { hoverTip.value.show = false; }, 500);
}

function _cellSpan(raw, color) {
  return h('span', {
    style: `color:${color};cursor:default;font-size:12px`,
    onMouseenter: null,
    onMouseleave: null,
  }, raw.slice(0, 16) + '…');
}

function renderReqCell(row) {
  const raw = row.request || '';
  const isEqQuery = raw.toUpperCase().startsWith('0506E002');
  const p = cachedParseAGV(raw);
  if (!p?.isValid) {
    return h('span', {
      style: `color:${isEqQuery ? '#e6a23c' : 'var(--n-text-color-3)'};cursor:default;font-size:12px`,
      onMouseenter: (e) => _showTip(e, raw, '原始数据', []),
      onMouseleave: _hideTip,
    }, raw.slice(0, 16) + '…');
  }
  const trayLabel = p.command.traySize === 1 ? '小' : p.command.traySize === 2 ? '大' : p.command.traySize;
  const lines = [
    `${p.command.commandTypeText} | ${p.command.layerText}`,
    `Port1: ${p.command.port1 ? '✓' : '✗'}  Port2: ${p.command.port2 ? '✓' : '✗'}`,
    `到位: ${p.command.agvArrived ? '✓' : '✗'}  Tray: ${trayLabel}  ID: ${p.trayId || '-'}`,
  ];
  return h('span', {
    style: `color:${isEqQuery ? '#e6a23c' : 'var(--n-primary-color)'};cursor:default;font-size:12px`,
    onMouseenter: (e) => _showTip(e, raw, 'AGV 控制指令', lines),
    onMouseleave: _hideTip,
  }, raw.slice(0, 16) + '…');
}

function renderRespCell(row) {
  const raw = row.response || '';
  const ok = row.result?.toLowerCase() === 'yes';
  const p = cachedParseEQ(raw);
  if (!p?.isValid) {
    return h('span', {
      style: 'color:var(--n-text-color-3);cursor:default;font-size:12px',
      onMouseenter: (e) => _showTip(e, raw, '解析失败', []),
      onMouseleave: _hideTip,
    }, raw.slice(0, 16) + '…');
  }
  const lo = p.gratingStatus?.lowerGrating?.text || '?';
  const up = p.gratingStatus?.upperGrating?.text || '?';
  const tid = wcsForm.value.trayid || '';
  const half = Math.ceil(p.ports.length / 2);
  const lines = [{ t: `${p.portCount} 个Port | 光栅: ${lo} / ${up}` }];
  if (p.ports.length) {
    const lowerIds = p.ports.slice(0, half).map(po => po.trayId).filter(Boolean).join(' ');
    const upperIds = p.ports.slice(half).map(po => po.trayId).filter(Boolean).join(' ');
    if (lowerIds) lines.push({ t: `下层: ${lowerIds}` });
    if (upperIds) lines.push({ t: `上层: ${upperIds}` });
  }
  return h('span', {
    style: `color:${ok ? 'var(--n-success-color)' : 'var(--n-warning-color)'};cursor:default;font-size:12px`,
    onMouseenter: (e) => _showTip(e, raw, `EQ 状态${ok ? '' : ' (result!=yes)'}`, lines, tid),
    onMouseleave: _hideTip,
  }, raw.slice(0, 16) + '…');
}

function fmtLogLabel(f) {
  const name = f.filename;
  const m = name.match(/^(\d{2})\.(\d{2})\.(\d{2})—(\d{2})\.(\d{2})\.(\d{2})_default\.log/);
  const label = m ? `${m[1]}:${m[2]} — ${m[4]}:${m[5]}  default.log` : name;
  return `${label}  (${(f.mtime || '').replace('T', ' ').slice(0, 19)})`;
}

function showWcsDetail(row) {
  wcsDetailRow.value = row;
  try { wcsDetailReq.value = agvParser.parseAGVCommand(row.request); } catch (e) { wcsDetailReq.value = { error: e.message }; }
  try { wcsDetailResp.value = agvParser.parseEQStatus(row.response); } catch (e) { wcsDetailResp.value = { error: e.message }; }
  wcsDetailModal.value = true;
}

// ── Clean ──────────────────────────────────────────────────────────────
const cleanUsage = ref({});

async function loadCleanUsage() {
  try {
    const res = await fetch(`${apiBase}/clean/usage`);
    if (res.ok) cleanUsage.value = await res.json();
  } catch (e) { /* ignore */ }
}

const cleanTargetOptions = [
  { label: 'AGV 日志目录', value: 'agvlog' },
  { label: 'WCS 日志目录', value: 'wcslog' },
  { label: 'WCS log_bak 压缩包', value: 'logbak' },
];

const cleanTargetLabel = {
  agvlog: 'AGV',
  wcslog: 'WCS',
  logbak: 'log_bak',
};

async function loadCleanFiles() {
  cleanLoading.value = true;
  cleanSelected.value = [];
  try {
    const res = await fetch(`${apiBase}/clean/${cleanTarget.value}`);
    cleanFiles.value = (await res.json()).files || [];
  } catch (e) {
    message.error('加载文件列表失败');
  } finally {
    cleanLoading.value = false;
  }
}

async function deleteCleanFiles() {
  if (cleanSelected.value.length === 0) {
    message.warning('请选择要删除的文件');
    return;
  }
  try {
    const res = await fetch(`${apiBase}/clean/${cleanTarget.value}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cleanSelected.value),
    });
    const data = await res.json();
    if (res.ok) {
      message.success(`已删除 ${data.count} 个文件`);
      loadCleanFiles();
      loadCleanUsage();
    } else {
      message.error(data.detail || '删除失败');
    }
  } catch (e) {
    message.error('删除请求失败');
  }
}

// ── Watch ──────────────────────────────────────────────────────────────
watch(wcsRemoteSubTab, (val) => {
  if (val === 'logbak' && !bakRemoteFiles.value.length) loadBakRemoteFiles();
});
watch(wcsTab, (val) => {
  if (val === 'remote') {
    if (wcsRemoteSubTab.value === 'logbak') {
      if (!bakRemoteFiles.value.length) loadBakRemoteFiles();
    } else {
      if (!wcsRemoteFiles.value.length) loadWcsRemoteFiles();
    }
  } else if (val === 'logbak') {
    if (!logbakLocalFiles.value.length) loadLocalLogbak();
  }
});

// ── Mount ──────────────────────────────────────────────────────────────
loadAgvLocalFiles();
loadWcsFiles();
loadCleanUsage();
</script>

<template>
  <div class="log-parser-container">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
      <h2 style="margin:0">日志分析</h2>
      <div v-if="Object.keys(cleanUsage).length" style="display:flex;align-items:center;gap:8px;font-size:12px">
        <span style="color:var(--n-text-color-3);white-space:nowrap">
          {{ Object.values(cleanUsage).reduce((s,i) => s + (i.total_size||0), 0) > 1073741824 ? '🔴' : Object.values(cleanUsage).reduce((s,i) => s + (i.total_size||0), 0) > 524288000 ? '🟡' : Object.values(cleanUsage).reduce((s,i) => s + (i.total_size||0), 0) > 209715200 ? '🔵' : '🟢' }}
          日志文件磁盘占用 {{ ['wcslog','logbak','agvlog'].map(k => cleanUsage[k]?.total_size_str).filter(Boolean).join(' + ') }}
        </span>
        <div class="progress-track" style="width:80px;height:6px;flex-shrink:0">
          <div class="progress-fill" :style="{
            width: Math.min(100, (Object.values(cleanUsage).reduce((s,i) => s + (i.total_size||0), 0) / 1073741824) * 100) + '%',
            background: Object.values(cleanUsage).reduce((s,i) => s + (i.total_size||0), 0) > 1073741824 ? '#d03050' : Object.values(cleanUsage).reduce((s,i) => s + (i.total_size||0), 0) > 524288000 ? '#f0a020' : Object.values(cleanUsage).reduce((s,i) => s + (i.total_size||0), 0) > 209715200 ? '#2080f0' : '#18a058'
          }"></div>
        </div>
      </div>
    </div>

    <n-tabs type="line" size="large" v-model:value="mainTab">
      <!-- ═══ AGV 日志 ═══ -->
      <n-tab-pane name="agv" tab="AGV 日志">
        <n-tabs type="card" size="medium" v-model:value="agvTab">
          <!-- 从AGV下载 -->
          <n-tab-pane name="download" tab="下载日志">
            <n-card size="small" title="从AGV下载日志文件">
              <n-form :model="agvForm" label-placement="left" label-width="100">
                <n-form-item label="IP / CarID" required>
                  <n-space>
                    <n-input v-model:value="agvForm.ip_or_carid" placeholder="172.26.126.120 或 carid" style="width:240px" />
                    <n-button @click="loadAgvRemoteFiles" :loading="agvRemoteLoading" size="small" secondary>
                      获取文件列表
                    </n-button>
                  </n-space>
                </n-form-item>
                <n-form-item v-if="agvRemoteFiles.length" label="选择文件">
                  <n-select multiple v-model:value="agvSelectedFiles"
                    :options="agvRemoteFiles.map(f => ({ label: `${f.name}  (${f.size_str}  ${f.mtime})`, value: f.name }))"
                    placeholder="选择要下载的AGV日志文件" filterable clearable style="min-width:500px" />
                </n-form-item>
                <n-form-item v-if="agvRemoteFiles.length">
                  <n-space>
                    <n-text depth="3">{{ agvSelectedFiles.length }} / {{ agvRemoteFiles.length }} 个文件</n-text>
                    <n-button type="primary" @click="downloadAgvLogs" :loading="agvDownloading"
                      :disabled="!agvSelectedFiles.length">
                      开始下载
                    </n-button>
                  </n-space>
                </n-form-item>
              </n-form>
              <div v-if="agvDownloadLogs.length" class="progress-area">
                <n-spin v-if="agvDownloading" size="small" />
                <div class="log-lines">
                  <div v-for="(entry, i) in agvDownloadLogs" :key="i"
                    :class="['log-line', entry.type]">
                    <n-text :depth="entry.type === 'error' ? undefined : entry.type === 'success' ? undefined : 2"
                      :type="entry.type === 'error' ? 'error' : entry.type === 'success' ? 'success' : undefined">
                      {{ entry.text }}
                    </n-text>
                  </div>
                </div>
              </div>
              <div v-if="agvDownloadFiles.length" class="download-result">
                <n-tag v-for="f in agvDownloadFiles" :key="f" type="success" size="small">{{ f }}</n-tag>
              </div>
            </n-card>
          </n-tab-pane>

          <!-- PIO 分析 -->
          <n-tab-pane name="pio" tab="PIO 分析">
            <n-card size="small" title="PIO 信号分析">
              <n-form :model="agvForm" label-placement="left" label-width="100">
                <n-form-item label="文件来源">
                  <n-radio-group v-model:value="pioSource" name="pioSource">
                    <n-radio-button value="remote">远程AGV</n-radio-button>
                    <n-radio-button value="local">本地文件</n-radio-button>
                  </n-radio-group>
                </n-form-item>

                <!-- 远程模式 -->
                <template v-if="pioSource === 'remote'">
                  <n-form-item label="IP / CarID" required>
                    <n-space>
                      <n-input v-model:value="agvForm.ip_or_carid" placeholder="172.26.126.120 或 carid" style="width:240px" />
                      <n-button @click="loadAgvRemoteFiles" :loading="agvRemoteLoading" size="small" secondary>
                        获取文件列表
                      </n-button>
                    </n-space>
                  </n-form-item>
                  <n-form-item v-if="agvRemoteFiles.length" label="选择文件">
                    <n-select multiple v-model:value="agvSelectedFiles"
                      :options="agvRemoteFiles.map(f => ({ label: `${f.name}  (${f.size_str}  ${f.mtime})`, value: f.name }))"
                      placeholder="选择要分析的AGV日志文件" filterable clearable style="min-width:500px" />
                  </n-form-item>
                </template>

                <!-- 本地模式 -->
                <template v-if="pioSource === 'local'">
                  <n-form-item label="选择文件">
                    <n-space>
                      <n-select multiple v-model:value="agvSelectedFiles"
                        :options="agvLocalFiles.filter(f => f.filename.startsWith('AGV_')).map(f => ({ label: `${f.filename}  (${formatSize(f.size)}  ${(f.mtime||'').replace('T',' ').slice(0,19)})`, value: f.filename }))"
                        placeholder="选择本地AGV日志文件（仅原始 AGV_ 文件）" filterable clearable style="min-width:500px" />
                      <n-button @click="loadAgvLocalFiles" :loading="agvLocalLoading" size="small" secondary>刷新</n-button>
                    </n-space>
                  </n-form-item>
                </template>

                <n-form-item v-if="agvSelectedFiles.length">
                  <n-space>
                    <n-text depth="3">{{ agvSelectedFiles.length }} 个文件</n-text>
                    <n-button type="primary" @click="runPioAnalysis" :loading="pioLoading"
                      :disabled="!agvSelectedFiles.length">
                      开始分析
                    </n-button>
                  </n-space>
                </n-form-item>
              </n-form>
              <div v-if="agvDownloadLogs.length" class="progress-area">
                <n-spin v-if="pioLoading" size="small" />
                <div class="log-lines">
                  <div v-for="(entry, i) in agvDownloadLogs" :key="i"
                    :class="['log-line', entry.type]">
                    <n-text :depth="entry.type === 'error' ? undefined : entry.type === 'success' ? undefined : 2"
                      :type="entry.type === 'error' ? 'error' : entry.type === 'success' ? 'success' : undefined">
                      {{ entry.text }}
                    </n-text>
                  </div>
                </div>
              </div>

              <!-- PIO 结果 -->
              <div v-if="pioResult && pioResult.length" class="pio-result">
                <n-divider>PIO 分析结果（{{ pioResult.length }} 组）</n-divider>
                <n-dataTable
                  :columns="[
                    { title: '#', key: 'index', width: 50, render: (_, i) => i + 1 },
                    { title: '时间段', key: 'time', render: (r) => `${r.start_time} ~ ${r.end_time}` },
                    { title: 'PIO Result', key: 'pio_result', width: 100, render: (r) => '0x' + r.pio_result.toString(16).toUpperCase() },
                    { title: 'PIO Value', key: 'pio_value', width: 100, render: (r) => '0x' + r.pio_value.toString(16).toUpperCase() },
                    { title: '合并行数', key: 'count', width: 80 },
                    { title: '操作', key: 'actions', width: 80, render: (r) => h(NButton, { size: 'tiny', onClick: () => showPioDetail(r) }, { default: () => '详情' }) },
                  ]"
                  :data="pioResult" size="small" :bordered="false" max-height="500" />
              </div>
            </n-card>
          </n-tab-pane>

          <!-- 本地文件 -->
          <n-tab-pane name="local" tab="本地文件">
            <n-card size="small" title="已下载的AGV日志">
              <n-space style="margin-bottom:12px">
                <n-button @click="loadAgvLocalFiles" :loading="agvLocalLoading" size="small">刷新</n-button>
                <n-popconfirm @positive-click="deleteAllLocalFiles">
                  <template #trigger>
                    <n-button type="error" size="small" secondary>清空全部</n-button>
                  </template>
                  确定要删除所有AGV日志文件吗？
                </n-popconfirm>
              </n-space>
              <n-dataTable
                :columns="[
                  { title: '文件名', key: 'filename', ellipsis: { tooltip: true } },
                  { title: '大小', key: 'size', width: 100, render: (row) => formatSize(row.size) },
                  { title: '修改时间', key: 'mtime', width: 180, render: (row) => row.mtime?.replace('T', ' ').slice(0, 19) },
                  { title: '操作', key: 'actions', width: 80, render: (row) => h(NPopconfirm, { onPositiveClick: () => deleteLocalFile(row.filename) }, { trigger: () => h(NButton, { size: 'tiny', type: 'error', secondary: true }, { default: () => '删除' }), default: () => '确定删除?' }) },
                ]"
                :data="agvLocalFiles" :loading="agvLocalLoading" size="small" :bordered="false"
                :row-key="(r) => r.filename" max-height="400" />
            </n-card>
          </n-tab-pane>
        </n-tabs>
      </n-tab-pane>

      <!-- ═══ WCS 日志 ═══ -->
      <n-tab-pane name="wcs" tab="WCS 日志">
        <n-tabs type="card" size="medium" v-model:value="wcsTab">
          <!-- 本地解析 -->
          <n-tab-pane name="local" tab="本地解析">
            <n-card size="small" title="WCS 日志解析">
              <n-form :model="wcsForm" label-placement="left" label-width="100">
                <n-form-item label="日志文件">
                  <n-select v-model:value="wcsForm.filenames" multiple :options="wcsFiles.map(f => ({ label: fmtLogLabel(f), value: f.filename }))"
                    placeholder="选择WCS日志文件（可多选）" filterable clearable />
                </n-form-item>
                <n-form-item label="过滤条件">
                  <n-space>
                    <n-auto-complete v-model:value="wcsForm.device_type" :options="deviceTypeOptions" placeholder="设备类型" style="width:130px" clearable />
                    <n-input v-model:value="wcsForm.shortcode" placeholder="外设编号: 528000" style="width:160px" clearable />
                    <n-input v-model:value="wcsForm.taskid" placeholder="任务ID" style="width:320px" clearable />
                    <n-input v-model:value="wcsForm.trayid" placeholder="TrayID" style="width:210px" clearable />
                  </n-space>
                </n-form-item>
                <n-form-item>
                  <n-space>
                    <n-button type="primary" @click="parseWcsLog" :loading="wcsParsing">开始解析</n-button>
                    <n-button @click="loadWcsFiles" :loading="wcsFilesLoading" secondary>刷新文件列表</n-button>
                  </n-space>
                </n-form-item>
              </n-form>

              <div v-if="wcsParseResult" class="wcs-result">
                <n-divider>解析结果（{{ Object.values(wcsParseResult.results||{}).reduce((s,r) => s + (r.count||0), 0) }} 条，{{ Object.keys(wcsParseResult.results||{}).length }} 个文件）</n-divider>
                <div class="hover-bar" :class="{ on: hoverTip.show }">
                  <span v-if="hoverTip.show">
                    <span class="hover-bar-title">{{ hoverTip.title }}</span>
                    <span v-for="(l, i) in hoverTip.lines" :key="i" class="hover-bar-line"
                      :class="{ 'hl-match': l.hl, 'hl-normal': l.hl === false }">{{ l.t ?? l }}</span>
                    <span class="hover-bar-raw" v-if="hoverTip.raw">{{ hoverTip.raw.slice(0, 80) }}…</span>
                  </span>
                  <span v-else>鼠标悬停在 Request/Response 字段查看解析详情</span>
                </div>

                <n-tabs v-model:value="wcsResultTab" type="card" size="small" style="margin-top:8px">
                  <n-tab-pane v-for="(r, fn) in wcsParseResult.results" :key="fn" :name="fn" :tab="fn.length > 50 ? fn.slice(0,47)+'...' : fn">
                    <n-text v-if="r.error" type="error">{{ r.error }}</n-text>
                    <n-dataTable v-else
                    :columns="[
                      { title: '时间', key: 'time', width: 130 },
                      { title: 'Task Key', key: 'task_key', width: 150, ellipsis: { tooltip: true } },
                      { title: 'Action', key: 'action_type', width: 100 },
                      { title: 'Step', key: 'task_step', width: 120 },
                      { title: 'Request', key: 'request', width: 90, render: (r) => renderReqCell(r) },
                      { title: 'Response', key: 'response', width: 90, render: (r) => renderRespCell(r) },
                      { title: 'Result', key: 'result', width: 45, render: (r) => h(NTag, { type: r.result?.toLowerCase() === 'yes' ? 'success' : 'error', size: 'small' }, { default: () => r.result }) },
                      { title: '操作', key: 'actions', width: 45, render: (r) => h(NButton, { size: 'tiny', onClick: () => showWcsDetail(r) }, { default: () => '详情' }) },
                    ]"
                    :data="r.rows" size="small" :bordered="false" max-height="450" virtual-scroll
                    :row-key="(_, i) => i" />
                  </n-tab-pane>
                </n-tabs>
              </div>
            </n-card>
          </n-tab-pane>

          <!-- 远程下载 -->
          <n-tab-pane name="remote" tab="远程下载">
            <n-card size="small" title="从WCS服务器下载日志">
              <n-space style="margin-bottom:12px" align="center">
                <n-radio-group v-model:value="wcsRemoteSubTab" name="wcsRemoteSubTab" size="small">
                  <n-radio-button value="default">default.log</n-radio-button>
                  <n-radio-button value="logbak">log_bak 压缩包</n-radio-button>
                </n-radio-group>
              </n-space>

              <!-- default.log view -->
              <template v-if="wcsRemoteSubTab === 'default'">
                <n-space style="margin-bottom:8px" align="center" justify="space-between">
                  <n-space align="center">
                    <n-input v-model:value="wcsRemoteSearch" placeholder="搜索文件名..." clearable style="width:200px"
                      @keyup.enter="wcsRemotePage=1;loadWcsRemoteFiles()" />
                    <n-button size="small" @click="wcsRemotePage=1;loadWcsRemoteFiles()">搜索</n-button>
                    <n-button size="small" @click="loadWcsRemoteFiles" :loading="wcsRemoteLoading" secondary>刷新</n-button>
                    <n-checkbox v-model:checked="wcsSelectAll" @update:checked="toggleWcsSelectAll"
                      :disabled="!wcsRemoteFiles.length">全选</n-checkbox>
                    <n-text depth="3">{{ wcsRemoteFiles.filter(f => f._checked).length }} / {{ wcsRemoteFiles.length }} 选中</n-text>
                  </n-space>
                  <n-button type="primary" @click="downloadWcsLogs" :loading="wcsDownloading"
                    :disabled="!wcsRemoteFiles.filter(f => f._checked).length">
                    下载选中
                  </n-button>
                </n-space>

                <!-- 卡片网格 -->
                <n-spin :show="wcsRemoteLoading">
                  <div class="log-grid">
                    <div v-for="f in wcsRemoteFiles" :key="f._idx"
                      :class="['log-card', { checked: f._checked }]"
                      @click="f._checked = !f._checked; onWcsCheckChange()">
                      <n-checkbox :checked="f._checked" @click.stop @update:checked="v => { f._checked = v; onWcsCheckChange(); }" />
                      <div class="log-card-body">
                        <span class="log-card-name">{{ f.filename }}</span>
                        <span class="log-card-time">{{ (f.time||'').replace('T',' ').slice(0,19) }}</span>
                      </div>
                    </div>
                  </div>
                  <n-text v-if="!wcsRemoteFiles.length && !wcsRemoteLoading" depth="3" style="text-align:center;display:block;padding:20px">
                    暂无文件
                  </n-text>
                </n-spin>

                <n-space v-if="wcsRemoteTotal > wcsRemotePageSize" justify="center" style="margin-top:12px">
                  <n-pagination v-model:page="wcsRemotePage" :page-size="wcsRemotePageSize"
                    :item-count="wcsRemoteTotal" :page-slot="5" size="small"
                    @update:page="onWcsRemotePageChange" />
                </n-space>
              </template>

              <!-- log_bak view -->
              <template v-if="wcsRemoteSubTab === 'logbak'">
                <n-space style="margin-bottom:8px" align="center" justify="space-between">
                  <n-space align="center">
                    <n-input v-model:value="bakRemoteSearch" placeholder="搜索文件名..." clearable style="width:200px"
                      @keyup.enter="bakRemotePage=1;loadBakRemoteFiles()" />
                    <n-button size="small" @click="bakRemotePage=1;loadBakRemoteFiles()">搜索</n-button>
                    <n-button size="small" @click="loadBakRemoteFiles" :loading="bakRemoteLoading" secondary>刷新</n-button>
                    <n-checkbox v-model:checked="bakSelectAll" @update:checked="toggleBakSelectAll"
                      :disabled="!bakRemoteFiles.length">全选</n-checkbox>
                    <n-text depth="3">{{ bakRemoteFiles.filter(f => f._checked).length }} / {{ bakRemoteFiles.length }} 选中</n-text>
                  </n-space>
                  <n-button type="primary" @click="downloadWcsLogs" :loading="wcsDownloading"
                    :disabled="!bakRemoteFiles.filter(f => f._checked).length">
                    下载选中
                  </n-button>
                </n-space>

                <n-spin :show="bakRemoteLoading">
                  <div class="log-grid">
                    <div v-for="f in bakRemoteFiles" :key="f._idx"
                      :class="['log-card', { checked: f._checked }]"
                      @click="f._checked = !f._checked; onBakCheckChange()">
                      <n-checkbox :checked="f._checked" @click.stop @update:checked="v => { f._checked = v; onBakCheckChange(); }" />
                      <div class="log-card-body">
                        <span class="log-card-name">{{ f.filename }}</span>
                        <span class="log-card-time">{{ (f.time||'').replace('T',' ').slice(0,19) }}</span>
                      </div>
                    </div>
                  </div>
                  <n-text v-if="!bakRemoteFiles.length && !bakRemoteLoading" depth="3" style="text-align:center;display:block;padding:20px">
                    暂无文件
                  </n-text>
                </n-spin>

                <n-space v-if="bakRemoteTotal > bakRemotePageSize" justify="center" style="margin-top:12px">
                  <n-pagination v-model:page="bakRemotePage" :page-size="bakRemotePageSize"
                    :item-count="bakRemoteTotal" :page-slot="5" size="small"
                    @update:page="onBakRemotePageChange" />
                </n-space>
              </template>

              <!-- 下载进度 + 结果（公共） -->

              <div v-if="wcsDownloading && (wcsProgress.filename || bakProgress.filename)" class="wcs-progress-bar" style="margin-top:12px">
                <n-text depth="3" style="font-size:12px">{{ (wcsRemoteSubTab === 'logbak' ? bakProgress : wcsProgress).filename }}</n-text>
                <div class="progress-track">
                  <div class="progress-fill"
                    :style="{ width: ((wcsRemoteSubTab === 'logbak' ? bakProgress : wcsProgress).percentage || 0) + '%' }"></div>
                </div>
                <n-text depth="3" style="font-size:12px">
                  {{ (wcsRemoteSubTab === 'logbak' ? bakProgress : wcsProgress).percentage }}%
                  ({{ (wcsRemoteSubTab === 'logbak' ? bakProgress : wcsProgress).downloaded_str }}
                  / {{ (wcsRemoteSubTab === 'logbak' ? bakProgress : wcsProgress).total_str }})
                </n-text>
              </div>

              <div v-if="wcsDownloadLogs.length" class="progress-area" style="margin-top:12px">
                <n-spin v-if="wcsDownloading" size="small" />
                <div class="log-lines">
                  <div v-for="(entry, i) in wcsDownloadLogs" :key="i"
                    :class="['log-line', entry.type]">
                    <n-text :depth="entry.type === 'error' ? undefined : entry.type === 'success' ? undefined : 2"
                      :type="entry.type === 'error' ? 'error' : entry.type === 'success' ? 'success' : undefined">
                      {{ entry.text }}
                    </n-text>
                  </div>
                </div>
              </div>

              <div v-if="wcsDownloadFiles.length" class="download-result">
                <n-tag v-for="f in wcsDownloadFiles" :key="f" type="success" size="small">{{ f }}</n-tag>
              </div>
            </n-card>
          </n-tab-pane>
          <!-- log_bak 解压 -->
          <n-tab-pane name="logbak" tab="logbak 解压">
            <n-card size="small" title="解压 log_bak 压缩包 → wcslog/">
              <n-space style="margin-bottom:12px">
                <n-button @click="loadLocalLogbak" :loading="logbakLocalLoading" size="small">刷新</n-button>
              </n-space>

              <n-dataTable
                :columns="[
                  { title: '压缩包', key: 'filename', ellipsis: { tooltip: true } },
                  { title: '大小', key: 'size_str', width: 100 },
                  { title: '修改时间', key: 'mtime', width: 170 },
                  { title: '操作', key: 'actions', width: 90,
                    render: (row) => h(NButton, {
                      size: 'tiny', type: 'warning', secondary: true,
                      loading: extractingFile === row.filename,
                      disabled: extractingFile !== null && extractingFile !== row.filename,
                      onClick: () => extractLogbak(row.filename),
                    }, { default: () => '解压' }) },
                ]"
                :data="logbakLocalFiles" :loading="logbakLocalLoading" size="small" :bordered="false"
                :row-key="(r) => r.filename" max-height="400" />

              <!-- 解压进度 -->
              <div v-if="extractingFile" class="wcs-progress-bar" style="margin-top:12px">
                <n-text depth="3" style="font-size:12px">{{ extractingFile }}</n-text>
                <div class="progress-track">
                  <div class="progress-fill" :style="{ width: (extractingProgress.percentage || 0) + '%' }"></div>
                </div>
                <n-text depth="3" style="font-size:12px">
                  {{ extractingProgress.total > 1000 ? (extractingProgress.current / 1048576).toFixed(1) + '/' + (extractingProgress.total / 1048576).toFixed(1) + ' MB' : extractingProgress.current + '/' + extractingProgress.total }}
                  ({{ extractingProgress.percentage }}%)
                </n-text>
              </div>

              <div v-if="extractingLogs.length" class="progress-area" style="margin-top:12px">
                <n-spin v-if="extractingFile" size="small" />
                <div class="log-lines">
                  <div v-for="(entry, i) in extractingLogs" :key="i"
                    :class="['log-line', entry.type]">
                    <n-text :depth="entry.type === 'error' ? undefined : entry.type === 'success' ? undefined : 2"
                      :type="entry.type === 'error' ? 'error' : entry.type === 'success' ? 'success' : undefined">
                      {{ entry.text }}
                    </n-text>
                  </div>
                </div>
              </div>

              <n-text v-if="!logbakLocalLoading && !logbakLocalFiles.length" depth="3" style="margin-top:12px;display:block">
                暂无本地 log_bak 压缩包。请先在「远程下载」中下载。
              </n-text>
            </n-card>
          </n-tab-pane>
        </n-tabs>

        <!-- WCS 详情弹窗 -->
        <n-modal v-model:show="wcsDetailModal" title="WCS 指令详情" preset="card" style="width:1200px;max-width:98vw">
          <div v-if="wcsDetailRow">
            <n-text depth="2">
              {{ wcsDetailRow.time }} | {{ wcsDetailRow.task_key }} | {{ wcsDetailRow.action_type }} | {{ wcsDetailRow.task_step }}
            </n-text>
            <n-collapse v-model="wcsDetailCollapse" :default-expanded-names="['req']" style="margin-top:8px">
              <n-collapse-item title="Request (AGV 控制指令)" name="req">
                <div v-if="wcsDetailReq?.isValid" style="font-size:12px;line-height:1.8">
                  <n-text>
                    指令类型: {{ wcsDetailReq.command.commandTypeText }} |
                    层级: {{ wcsDetailReq.command.layerText }} |
                    Port1: <n-tag :type="wcsDetailReq.command.port1 ? 'info' : 'default'" size="tiny">{{ wcsDetailReq.command.port1 ? '是' : '否' }}</n-tag>
                    Port2: <n-tag :type="wcsDetailReq.command.port2 ? 'info' : 'default'" size="tiny">{{ wcsDetailReq.command.port2 ? '是' : '否' }}</n-tag>
                    到位: {{ wcsDetailReq.command.agvArrived ? '✓' : '✗' }}
                    滚动: {{ wcsDetailReq.command.rollerAction ? '✓' : '✗' }}
                    TrayOk: {{ wcsDetailReq.command.agvTrayOk ? '✓' : '✗' }}
                    离开: {{ wcsDetailReq.command.agvLeave ? '✓' : '✗' }}
                    Tray: {{ wcsDetailReq.command.traySize === 1 ? '小' : wcsDetailReq.command.traySize === 2 ? '大' : wcsDetailReq.command.traySize }}
                    TrayID: {{ wcsDetailReq.trayId || '无' }}
                  </n-text>
                </div>
                <n-text v-else type="error" depth="3">{{ wcsDetailReq?.error || '解析失败' }}</n-text>
              </n-collapse-item>
              <hr>
            </n-collapse>

            <n-collapse v-model="wcsDetailCollapse">
              <n-collapse-item title="Response (EQ 状态)" name="resp" style="">
                <div v-if="wcsDetailResp?.isValid">
                    下层光栅：{{ wcsDetailResp.gratingStatus.lowerGrating.text }} ； 
                    上层光栅：{{ wcsDetailResp.gratingStatus.upperGrating.text }}
                  <n-dataTable
                    :columns="[
                      { title: '层', key: 'layer', width: 20, render: (_, i) => i < Math.ceil(wcsDetailResp.ports.length / 2) ? '下' : '上' },
                      { title: '位置', key: 'portPosition', width: 80 },
                      { title: '就绪', key: 'ready', width: 60, render: (r) => r.status.readyStatus.text },
                      { title: 'TrayOk', key: 'trayOk', width: 80, render: (r) => r.status.trayOkStatus.text },
                      { title: '在线', key: 'online', width: 120, render: (r) => r.status.onlineStatus.text },
                      { title: 'Tray盘', key: 'present', width: 120, render: (r) => r.status.trayPresentStatus.text },
                      { title: '滚动', key: 'roller', width: 80, render: (r) => r.status.rollerStartStatus.text },
                      { title: '尺寸', key: 'size', width: 60, render: (r) => r.status.traySize.text },
                      { title: 'TrayID', key: 'trayId', width: 140 },
                    ]"
                    :data="wcsDetailResp.ports" size="small" :bordered="false" style="margin-top:4px;" />
                </div>
                <n-text v-else-if="wcsDetailResp" type="error" depth="3">{{ wcsDetailResp.error || '解析失败' }}</n-text>
              </n-collapse-item>
            </n-collapse>

            <div style="font-family:monospace;font-size:11px;word-break:break-all;margin-top:8px">
              <span style="color:var(--n-primary-color);font-weight:600">RAW Request:</span>
              <n-text depth="3"> {{ wcsDetailRow.request }}</n-text>
            </div>
            <div style="font-family:monospace;font-size:11px;word-break:break-all;margin-top:4px">
              <span style="color:var(--n-success-color);font-weight:600">RAW Response:</span>
              <n-text depth="3"> {{ wcsDetailRow.response }}</n-text>
            </div>
          </div>
        </n-modal>
      </n-tab-pane>

      <!-- ═══ 清理 ═══ -->
      <n-tab-pane name="clean" tab="清理日志">
        <n-card size="small" title="清理日志文件">
          <n-space v-if="Object.keys(cleanUsage).length" style="margin-bottom:12px">
            <n-tag v-for="(info, key) in cleanUsage" :key="key" :type="key === cleanTarget ? 'info' : 'default'" size="small">
              {{ cleanTargetLabel[key] || key }}: {{ info.total_size_str }} ({{ info.file_count }} 个文件)
            </n-tag>
            <n-button text size="tiny" @click="loadCleanUsage">↻</n-button>
          </n-space>
          <n-space align="center" style="margin-bottom:12px">
            <n-text>目标目录：</n-text>
            <n-select v-model:value="cleanTarget" :options="cleanTargetOptions" style="width:180px"
              @update:value="loadCleanFiles" />
            <n-button @click="loadCleanFiles" :loading="cleanLoading" size="small">刷新</n-button>
          </n-space>

          <n-dataTable
            :columns="[
              { type: 'selection' },
              { title: '文件名', key: 'filename', ellipsis: { tooltip: true } },
              { title: '大小', key: 'size_str', width: 100 },
              { title: '修改时间', key: 'mtime', width: 180, render: (row) => row.mtime?.replace('T', ' ').slice(0, 19) },
            ]"
            :data="cleanFiles" :loading="cleanLoading" size="small" :bordered="false"
            :row-key="(r) => r.index" max-height="400"
            v-model:checked-row-keys="cleanSelected" />

          <n-space style="margin-top:12px">
            <n-text>已选 {{ cleanSelected.length }} / {{ cleanFiles.length }} 个文件</n-text>
            <n-popconfirm @positive-click="deleteCleanFiles">
              <template #trigger>
                <n-button type="error" :disabled="cleanSelected.length === 0">删除选中</n-button>
              </template>
              确定要删除选中的 {{ cleanSelected.length }} 个文件吗？
            </n-popconfirm>
          </n-space>
        </n-card>
      </n-tab-pane>
    </n-tabs>

    <!-- PIO 详情弹窗 -->
    <n-modal v-model:show="pioDetailModal" title="PIO 位对比详情" preset="card" style="width:520px">
      <div v-if="pioCurrentGroup">
        <n-text depth="2">
          {{ pioCurrentGroup.start_time }} ~ {{ pioCurrentGroup.end_time }}<br />
          PIO Result: 0x{{ pioCurrentGroup.pio_result.toString(16).toUpperCase() }}
          &nbsp;|&nbsp; PIO Value: 0x{{ pioCurrentGroup.pio_value.toString(16).toUpperCase() }}
          &nbsp;|&nbsp; 合并 {{ pioCurrentGroup.count }} 行
        </n-text>
        <n-divider />
        <n-dataTable
          :columns="[
            { title: '位', key: 'bit', width: 50 },
            { title: '含义', key: 'name', width: 100 },
            { title: 'Result', key: 'result', width: 70 },
            { title: 'Value', key: 'value', width: 70 },
            { title: '状态', key: 'match', width: 80, render: (r) => h(NTag, { type: r.match ? 'success' : 'error', size: 'small' }, { default: () => r.match ? '√ 匹配' : 'X 不匹配' }) },
          ]"
          :data="compareBits(pioCurrentGroup.pio_result_bin, pioCurrentGroup.pio_value_bin)"
          size="small" :bordered="false" />
      </div>
    </n-modal>

  </div>
</template>

<style scoped>
.log-parser-container {
  padding: 8px 12px;
  max-width: 1200px;
  margin: 0 auto;
}
.log-parser-container :deep(.n-data-table td) {
  white-space: nowrap;
}
.progress-area {
  margin-top: 12px;
  padding: 8px 12px;
  background: var(--n-color-embedded);
  border-radius: 6px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}
.log-lines {
  flex: 1;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.7;
}
.log-line.error {
  color: var(--n-error-color);
}
.log-line.success {
  color: var(--n-success-color);
}
.log-line.progress {
  color: var(--n-primary-color);
}
.download-result {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.pio-result, .wcs-result {
  margin-top: 8px;
}
.hover-bar {
  height: 28px;
  padding: 3px 10px;
  margin-bottom: 4px;
  border-radius: 4px;
  font-size: 12px;
  /* line-height: 20px; */
  /* border: 1px solid transparent; */
  background: transparent;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hover-bar.on {
  background: var(--n-info-color-suppl);
  border-color: var(--n-info-color);
}
.hover-bar-title {
  font-weight: 600;
  margin-right: 10px;
}
.hover-bar-line {
  color: var(--n-text-color-2);
  margin-right: 8px;
}
.hover-bar-line.hl-match {
  color: #e6a23c;
  font-weight: 600;
}
.hover-bar-line.hl-normal {
  color: #67c23a;
}
.hover-bar-raw {
  color: var(--n-text-color-3);
  font-family: monospace;
  font-size: 11px;
}
.wcs-progress-bar {
  padding: 8px 12px;
  background: var(--n-color-embedded);
  border-radius: 6px;
}
.progress-track {
  margin: 6px 0;
  height: 8px;
  background: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
}
[data-theme="dark"] .progress-track {
  background: #444;
}
.progress-fill {
  height: 100%;
  background: #2080f0;
  border-radius: 4px;
  transition: width 0.3s ease;
  min-width: 2px;
}

/* log 卡片网格 */
.log-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 8px;
  max-height: 400px;
  overflow-y: auto;
}
.log-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--n-border-color, #e0e0e0);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.log-card:hover {
  border-color: #2080f0;
}
.log-card.checked {
  border-color: #2080f0;
  background: rgba(32, 128, 240, 0.06);
}
.log-card-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
  font-size: 12px;
}
.log-card-name {
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.log-card-time {
  color: var(--n-text-color-3);
  font-size: 11px;
  margin-top: 2px;
}
</style>
