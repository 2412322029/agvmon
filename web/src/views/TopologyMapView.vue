<script setup>
/**
 * AGV 拓扑地图（MapCfg XML）查看 / 框选 / 地码生成
 *
 * 数据来源：
 *   - 后端 ``GET /api/map_topology/list`` / ``GET /api/map_topology/raw/{name}``（默认扫描 util/data 下的地图 XML）
 *   - 本地文件选择 / 拖拽 XML（纯前端解析，无需后端）
 *
 * 坐标单位为米（m，显示 3 位小数），地码 = {x_mm}{地图代码}{y_mm}（mm，6 位补零）
 */
import {
  NAlert, NButton, NCard, NCheckbox, NDataTable, NDescriptions, NDescriptionsItem,
  NDivider, NInput, NInputNumber, NRadioButton, NRadioGroup, NSelect, NSlider, NSpace,
  NSpin, NSwitch, NTabPane, NTabs, NTag, NText, useMessage,
} from 'naive-ui'
import { computed, h, inject, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import {
  buildCodesCsv, distanceToPolyline, formatMeters, formatMillimeters, makeGroundCode, matchFieldRule,
  parseGroundCode, parseTopologyXml, pointInRect, pointOnPolylineAt,
  polylineIntersectsRect, polylineLength, splitFilterValues,
} from '../composables/agvTopology.js'

const message = useMessage()
const darkMode = inject('darkMode', ref(false))

/* ─────────────────────────── 基础状态 ─────────────────────────── */

const wrapRef = ref(null)
const canvasRef = ref(null)
const fileInputRef = ref(null)

const topo = shallowRef(null)
const loading = ref(false)
const fileLabel = ref('')
const serverFiles = ref([])
const serverOk = ref(true)
const currentFile = ref(null)

const size = reactive({ w: 960, h: 620, dpr: 1 })
const view = reactive({ cx: 0, cy: 0, scale: 4 })
const MIN_SCALE = 0.05
const MAX_SCALE = 800

const opt = reactive({
  showNodes: true,
  showLinks: true,
  showArrows: true,
  /* ── 地图标签：批量显示点 / 线属性（不显示 ID，便于快速排查没配属性处） ── */
  nodeLabel: 'coord', // none | coord | code | value | roadProperty | allDir | eleDir | robottype | neighbors | size
  linkLabel: 'none', // none | distance | speed | revert | directed | geometry | robottype | carryType
  labelZoomGate: true, // 缩小后隐藏标签（放大到阈值以上才显示）
  labelMinZoom: 12, // px/m：缩放小于该值时不画标签
  onlyAbnormal: false, // 只标注属性缺失 / 为 0 的点线
  onlySelected: false, // 只标注已选中的点线
  onlyMatched: true, // 有筛选时只标注命中的点线（筛选后画布只看结果）
  dimUnmatched: true, // 有筛选时，未命中的点线淡化显示
  hideUnmatched: false, // 有筛选时，直接隐藏未命中的点线
  nodeRadius: 3.5,
  markRoadProperty: true,
  highlightRelated: true,
  panMode: false, // false = 左键框选, true = 左键平移
  pickMode: 'node', // node = 分点选择模式 | link = 线选择模式 | both = 点线同选
  nodeRule: 'inside', // inside | touch
  linkRule: 'both', // both | cross | endpoints
})

const selectedNodes = reactive(new Set())
const selectedLinks = reactive(new Set())
const primary = ref(null) // { type: 'node' | 'link', key: number|string }
const hover = ref(null) // { type, key } 悬停高亮用
const marquee = ref(null) // { x0, y0, x1, y1 } 屏幕坐标
const cursorWorld = ref(null)
const lastBox = ref(null) // 最近一次框选的世界矩形

/** 全屏 / 侧栏 / 右键菜单（操作优化） */
const pageRef = ref(null)
const isFullscreen = ref(false)
const showSide = ref(true)
const ctxMenu = ref(null)

const mapCode = ref('')
const padDigits = ref(6)
const sortMode = ref('xy') // id | xy | yx
const dedupeCodes = ref(true)
const nodeRemarkTpl = ref('节点{id}')

const stats = computed(() => {
  const t = topo.value
  const base = t
    ? t.stats
    : { nodeCount: 0, linkCount: 0, directedCount: 0, curvedCount: 0, isolatedCount: 0 }
  return {
    ...base,
    selectedNodeCount: selectedNodes.size,
    selectedLinkCount: selectedLinks.size,
  }
})

const meta = computed(() => topo.value?.meta ?? null)

/* ─────────────────────────── 坐标变换 ─────────────────────────── */

function toScreen(x, y) {
  return {
    x: (x - view.cx) * view.scale + size.w / 2,
    y: size.h / 2 - (y - view.cy) * view.scale,
  }
}

function toWorld(sx, sy) {
  return {
    x: (sx - size.w / 2) / view.scale + view.cx,
    y: (size.h / 2 - sy) / view.scale + view.cy,
  }
}

function viewBounds() {
  const tl = toWorld(0, 0)
  const br = toWorld(size.w, size.h)
  return { minX: tl.x, maxX: br.x, minY: br.y, maxY: tl.y }
}

function clampScale(value) {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value))
}

function fitView() {
  const t = topo.value
  if (!t || !size.w) return
  const { minX, maxX, minY, maxY } = t.bounds
  const pad = 28
  const sx = (size.w - pad * 2) / Math.max(1e-6, maxX - minX)
  const sy = (size.h - pad * 2) / Math.max(1e-6, maxY - minY)
  view.scale = clampScale(Math.min(sx, sy))
  view.cx = (minX + maxX) / 2
  view.cy = (minY + maxY) / 2
  scheduleDraw()
}

function zoomBy(factor, anchor) {
  const ax = anchor?.x ?? size.w / 2
  const ay = anchor?.y ?? size.h / 2
  const before = toWorld(ax, ay)
  const next = clampScale(view.scale * factor)
  if (next === view.scale) return
  view.scale = next
  view.cx = before.x - (ax - size.w / 2) / view.scale
  view.cy = before.y + (ay - size.h / 2) / view.scale
  scheduleDraw()
}

function centerOn(x, y, scale) {
  view.cx = x
  view.cy = y
  if (scale) view.scale = clampScale(scale)
  scheduleDraw()
}

function zoomToSelection() {
  const t = topo.value
  if (!t) return
  const pts = []
  for (const id of selectedNodes) {
    const n = t.nodeById.get(id)
    if (n) pts.push(n)
  }
  for (const key of selectedLinks) {
    const link = t.linkByKey.get(key)
    if (link) pts.push({ x: link.ax, y: link.ay }, { x: link.bx, y: link.by })
  }
  if (!pts.length) {
    const b = lastBox.value
    if (!b) return
    const sx = (size.w - 60) / Math.max(1e-6, b.maxX - b.minX)
    const sy = (size.h - 60) / Math.max(1e-6, b.maxY - b.minY)
    centerOn((b.minX + b.maxX) / 2, (b.minY + b.maxY) / 2, Math.min(sx, sy))
    return
  }
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const p of pts) {
    minX = Math.min(minX, p.x)
    maxX = Math.max(maxX, p.x)
    minY = Math.min(minY, p.y)
    maxY = Math.max(maxY, p.y)
  }
  const sx = (size.w - 80) / Math.max(0.2, maxX - minX)
  const sy = (size.h - 80) / Math.max(0.2, maxY - minY)
  centerOn((minX + maxX) / 2, (minY + maxY) / 2, Math.min(sx, sy))
}

/* ─────────────────────────── 绘制 ─────────────────────────── */

const palette = computed(() =>
  darkMode.value
    ? {
        bg: '#101418', grid: 'rgba(255,255,255,0.055)', axis: 'rgba(255,255,255,0.32)',
        node: '#60a5fa', nodeRoad: '#fbbf24', link: 'rgba(148,163,184,0.5)',
        linkHover: '#38bdf8', selNode: '#fb7185', selLink: '#f59e0b', related: '#34d399',
        label: '#e2e8f0', labelBg: 'rgba(2,6,23,0.72)', marquee: 'rgba(56,189,248,0.16)',
        marqueeBorder: '#38bdf8', hint: '#94a3b8', warn: '#f87171', linkLabel: '#facc15',
        match: '#4ade80', matchRing: '#86efac', dim: 'rgba(148,163,184,0.16)',
      }
    : {
        bg: '#ffffff', grid: 'rgba(15,23,42,0.06)', axis: 'rgba(15,23,42,0.3)',
        node: '#1d4ed8', nodeRoad: '#d97706', link: 'rgba(100,116,139,0.6)',
        linkHover: '#0284c7', selNode: '#e11d48', selLink: '#d97706', related: '#059669',
        label: '#0f172a', labelBg: 'rgba(255,255,255,0.78)', marquee: 'rgba(2,132,199,0.12)',
        marqueeBorder: '#0284c7', hint: '#64748b', warn: '#dc2626', linkLabel: '#a16207',
        match: '#16a34a', matchRing: '#15803d', dim: 'rgba(100,116,139,0.18)',
      },
)

/* ── 点 / 线属性：同一套属性同时用于「地图批量标注」与「筛选」 ── */

function linkSpeed(link) {
  return Math.max(0, ...Object.values(link.dirs).map((d) => d.speed || 0))
}

/**
 * 点属性：返回 { raw, text, abnormal }
 *   raw  = 参与筛选比较的原始值（数字或字符串）
 *   text = 画在地图上的标注文本
 *   abnormal = 属性缺失 / 为 0（用于「只标注异常」与红字提示）
 */
function nodeProp(node, key) {
  switch (key) {
    case 'coord':
      return { raw: `${formatMeters(node.x)},${formatMeters(node.y)}`, text: `${formatMeters(node.x)}, ${formatMeters(node.y)}`, abnormal: false }
    case 'code': {
      const code = makeGroundCode(node.x, node.y, mapCode.value.trim(), { pad: padDigits.value })
      return { raw: code, text: code, abnormal: false }
    }
    case 'id':
      return { raw: node.id, text: `#${node.id}`, abnormal: false }
    case 'x':
      return { raw: node.x, text: `X:${formatMeters(node.x)}`, abnormal: false }
    case 'y':
      return { raw: node.y, text: `Y:${formatMeters(node.y)}`, abnormal: false }
    case 'value':
      return { raw: node.value, text: `v:${node.value}`, abnormal: !node.value }
    case 'roadProperty':
      return { raw: node.roadProperty, text: `RP:${node.roadProperty}`, abnormal: !node.roadProperty }
    case 'allDir':
      return { raw: node.allDir, text: `dir:${node.allDir}`, abnormal: !node.allDir }
    case 'eleDir':
      return { raw: node.eleDir, text: `e:${node.eleDir === '' ? '空' : node.eleDir}`, abnormal: node.eleDir === '' }
    case 'elePre':
      return { raw: node.elePre, text: `ep:${node.elePre}`, abnormal: !node.elePre }
    case 'rotRad':
      return { raw: node.rotRad, text: `rot:${node.rotRad}`, abnormal: false }
    case 'robotType':
      return { raw: node.robotType, text: `rb:${node.robotType === '' ? '空' : node.robotType}`, abnormal: node.robotType === '' }
    case 'rotarySwitch':
      return { raw: node.rotarySwitch, text: `rs:${node.rotarySwitch}`, abnormal: false }
    case 'sensorSwitch':
      return { raw: node.sensorswitchPoint, text: `ss:${node.sensorswitchPoint}`, abnormal: false }
    case 'pioPoint':
      return { raw: node.pioPoint, text: `pio:${node.pioPoint}`, abnormal: node.pioPoint < 0 }
    case 'ctuStance':
      return { raw: node.ctuStance, text: `ctu:${node.ctuStance}`, abnormal: false }
    case 'tranZoneType':
      return { raw: node.tranZoneType, text: `tz:${node.tranZoneType}`, abnormal: false }
    case 'width':
      return { raw: node.width, text: `w:${formatMeters(node.width)}`, abnormal: !node.width }
    case 'height':
      return { raw: node.height, text: `h:${formatMeters(node.height)}`, abnormal: !node.height }
    case 'neighbors':
      return { raw: node.neighbors.length, text: `邻:${node.neighbors.length}`, abnormal: node.neighbors.length === 0 }
    case 'size':
      return {
        raw: `${formatMeters(node.width)}x${formatMeters(node.height)}`,
        text: `${formatMeters(node.width)}×${formatMeters(node.height)}`,
        abnormal: !node.width && !node.height,
      }
    default:
      return null
  }
}

const NODE_PROPS = [
  { value: 'coord', label: '坐标（m）', kind: 'text' },
  { value: 'code', label: '地码', kind: 'text' },
  { value: 'id', label: 'ID', kind: 'number' },
  { value: 'x', label: 'X（m）', kind: 'number' },
  { value: 'y', label: 'Y（m）', kind: 'number' },
  { value: 'value', label: 'value', kind: 'number' },
  { value: 'roadProperty', label: 'RoadProperty', kind: 'number' },
  { value: 'allDir', label: 'allDir', kind: 'number' },
  { value: 'eleDir', label: 'EleDir', kind: 'text' },
  { value: 'elePre', label: 'ElePre', kind: 'number' },
  { value: 'rotRad', label: 'RotRad', kind: 'number' },
  { value: 'robotType', label: 'robottype', kind: 'text' },
  { value: 'rotarySwitch', label: 'RotarySwitch', kind: 'number' },
  { value: 'sensorSwitch', label: 'sensorswitchPoint', kind: 'number' },
  { value: 'pioPoint', label: 'PioPoint', kind: 'number' },
  { value: 'ctuStance', label: 'CtuStance', kind: 'number' },
  { value: 'tranZoneType', label: 'TranZoneType', kind: 'number' },
  { value: 'width', label: 'width（m）', kind: 'number' },
  { value: 'height', label: 'height（m）', kind: 'number' },
  { value: 'neighbors', label: '邻接数', kind: 'number' },
  { value: 'size', label: '尺寸（m）', kind: 'text' },
]

/** 线属性：raw 用于筛选，text 用于地图标注 */
function linkProp(link, key) {
  const dirs = Object.values(link.dirs)
  const uniq = (picker) => [...new Set(dirs.map(picker).filter((v) => v !== undefined && v !== ''))]
  switch (key) {
    case 'distance': {
      const curved = polylineLength(link.path)
      return { raw: link.distance, text: `${formatMeters(link.distance)}m`, abnormal: !link.distance }
    }
    case 'speed': {
      const speed = linkSpeed(link)
      return { raw: speed, text: `S:${speed || '空'}`, abnormal: !speed }
    }
    case 'speedAB': {
      const s = link.dirs[link.a]?.speed ?? null
      return { raw: s ?? 0, text: `AB:${s || '空'}`, abnormal: !s }
    }
    case 'speedBA': {
      const s = link.dirs[link.b]?.speed ?? null
      return { raw: s ?? 0, text: `BA:${s || '空'}`, abnormal: !s }
    }
    case 'revert': {
      const reverts = dirs.map((d) => d.revert)
      const max = reverts.length ? Math.max(...reverts.map((r) => Number(r) || 0)) : 0
      const missing = reverts.length < 2 || reverts.some((r) => r === undefined)
      return { raw: max, text: `Rev:${reverts.join('/')}`, abnormal: missing }
    }
    case 'emptyCantRun': {
      const list = dirs.map((d) => d.emptyCantRun)
      const max = list.length ? Math.max(...list.map((v) => Number(v) || 0)) : 0
      return { raw: max, text: `ecr:${list.join('/')}`, abnormal: false }
    }
    case 'podDir': {
      const list = dirs.map((d) => d.podDir)
      const max = list.length ? Math.max(...list.map((v) => Number(v))) : -1
      return { raw: max, text: `pod:${max}`, abnormal: max < 0 }
    }
    case 'laserType': {
      const list = dirs.map((d) => d.laserType)
      const max = list.length ? Math.max(...list.map((v) => Number(v) || 0)) : 0
      return { raw: max, text: `laser:${max}`, abnormal: false }
    }
    case 'robottype': {
      const types = uniq((d) => d.robotType)
      const empty = types.length === 0
      return { raw: types.join(','), text: `rb:${empty ? '空' : types.join('/')}`, abnormal: empty }
    }
    case 'carryType': {
      const types = uniq((d) => d.carryType)
      const empty = types.length === 0
      return { raw: types.join(','), text: `carry:${empty ? '空' : types.join('/')}`, abnormal: empty }
    }
    case 'ctnrtype': {
      const types = uniq((d) => d.ctnrtype)
      const empty = types.length === 0
      return { raw: types.join(','), text: `ctnr:${empty ? '空' : types.join('/')}`, abnormal: empty }
    }
    case 'startDir': {
      const list = uniq((d) => d.startDir)
      return { raw: list.join(','), text: `st:${list.length ? list.join('/') : '空'}`, abnormal: list.length === 0 }
    }
    case 'stopDir': {
      const list = uniq((d) => d.stopDir)
      return { raw: list.join(','), text: `sp:${list.length ? list.join('/') : '空'}`, abnormal: list.length === 0 }
    }
    case 'directed':
      return { raw: link.directed ? 1 : 0, text: link.directed ? '双向' : '单向', abnormal: !link.directed }
    case 'geometry':
      return { raw: link.curved ? 1 : 0, text: link.curved ? `曲线${link.path.length}` : '直线', abnormal: false }
    case 'ctrlCount': {
      const n = Math.max(0, link.path.length - 2)
      return { raw: n, text: `cp:${n}`, abnormal: n === 0 }
    }
    case 'length': {
      const n = polylineLength(link.path)
      return { raw: n, text: `${formatMeters(n)}m`, abnormal: !n }
    }
    case 'midCode': {
      const mid = pointOnPolylineAt(link.path, 0.5)
      const code = mid ? makeGroundCode(mid.x, mid.y, mapCode.value.trim(), { pad: padDigits.value }) : ''
      return { raw: code, text: code, abnormal: false }
    }
    default:
      return null
  }
}

const LINK_PROPS = [
  { value: 'speed', label: '限速 Speed（两向取最大）', kind: 'number' },
  { value: 'speedAB', label: 'A→B 限速', kind: 'number' },
  { value: 'speedBA', label: 'B→A 限速', kind: 'number' },
  { value: 'distance', label: '长度 distance（m）', kind: 'number' },
  { value: 'length', label: '折线长度（m）', kind: 'number' },
  { value: 'revert', label: 'Rever', kind: 'number' },
  { value: 'emptyCantRun', label: 'EmptyCantRun', kind: 'number' },
  { value: 'podDir', label: 'PodDir', kind: 'number' },
  { value: 'laserType', label: 'LaserType', kind: 'number' },
  { value: 'directed', label: '是否双向（1/0）', kind: 'number' },
  { value: 'geometry', label: '是否曲线（1/0）', kind: 'number' },
  { value: 'ctrlCount', label: '控制点数', kind: 'number' },
  { value: 'robottype', label: 'robottype', kind: 'text' },
  { value: 'carryType', label: 'carryType', kind: 'text' },
  { value: 'ctnrtype', label: 'ctnrtype', kind: 'text' },
  { value: 'startDir', label: 'StartDir', kind: 'text' },
  { value: 'stopDir', label: 'StopDir', kind: 'text' },
  { value: 'midCode', label: '中点地码', kind: 'text' },
]

const nodeLabelOptions = [{ label: '不显示', value: 'none' }, ...NODE_PROPS.map((p) => ({ label: p.label, value: p.value }))]
const linkLabelOptions = [{ label: '不显示', value: 'none' }, ...LINK_PROPS.map((p) => ({ label: p.label, value: p.value }))]
const nodeFilterOptions = NODE_PROPS.map((p) => ({ label: p.label, value: p.value }))
const linkFilterOptions = LINK_PROPS.map((p) => ({ label: p.label, value: p.value }))

/* ── 筛选：点筛选 / 线筛选（= 支持多值，其余为数值比较） ── */

const OP_OPTIONS = [
  { label: '=', value: '=' },
  { label: '≠', value: '!=' },
  { label: '>', value: '>' },
  { label: '>=', value: '>=' },
  { label: '<', value: '<' },
  { label: '<=', value: '<=' },
]

const nodeFilter = reactive({ key: 'roadProperty', op: '=', value: '' })
const linkFilter = reactive({ key: 'speed', op: '=', value: '' })

const isEqualityOp = (op) => op === '=' || op === '!='

/**
 * 统计某个属性在图上「出现过的所有值」及数量，供筛选下拉直接勾选：
 *   options 形如 [{ label: '1（285）', value: '1' }]，空值显示为「空（992）」
 */
function buildValueStats(items, getter) {
  const map = new Map()
  if (items) {
    for (const item of items) {
      const prop = getter(item)
      if (!prop) continue
      const raw = prop.raw
      const label = raw === '' || raw === null || raw === undefined ? '空' : String(raw)
      const hit = map.get(label)
      if (hit) hit.count += 1
      else map.set(label, { value: label, count: 1, num: Number(raw) })
    }
  }
  const list = [...map.values()]
  const allNumeric = list.length > 0 && list.every((v) => v.value === '空' || Number.isFinite(v.num))
  if (allNumeric) {
    list.sort((a, b) => (a.value === '空' ? -1 : b.value === '空' ? 1 : a.num - b.num))
  } else {
    list.sort((a, b) => b.count - a.count || String(a.value).localeCompare(String(b.value)))
  }
  const numbers = list.filter((v) => v.value !== '空' && Number.isFinite(v.num)).map((v) => v.num)
  return {
    options: list.slice(0, 400).map((v) => ({ label: `${v.value}（${v.count}）`, value: v.value })),
    distinct: list.length,
    min: numbers.length ? Math.min(...numbers) : null,
    max: numbers.length ? Math.max(...numbers) : null,
  }
}

const nodeValueStats = computed(() => buildValueStats(topo.value?.nodes, (n) => nodeProp(n, nodeFilter.key)))
const linkValueStats = computed(() => buildValueStats(topo.value?.links, (l) => linkProp(l, linkFilter.key)))

/** 值的多选 ↔ 逗号字符串（= / ≠ 支持多值） */
const nodeFilterValues = computed({
  get: () => splitFilterValues(nodeFilter.value),
  set: (list) => {
    nodeFilter.value = Array.isArray(list) ? list.join(',') : String(list ?? '')
  },
})

const linkFilterValues = computed({
  get: () => splitFilterValues(linkFilter.value),
  set: (list) => {
    linkFilter.value = Array.isArray(list) ? list.join(',') : String(list ?? '')
  },
})

const nodeMatches = computed(() => {
  const t = topo.value
  if (!t || !splitFilterValues(nodeFilter.value).length) return null
  const hit = new Set()
  for (const node of t.nodes) {
    const prop = nodeProp(node, nodeFilter.key)
    if (prop && matchFieldRule(prop.raw, nodeFilter.op, nodeFilter.value)) hit.add(node.id)
  }
  return hit
})

const linkMatches = computed(() => {
  const t = topo.value
  if (!t || !splitFilterValues(linkFilter.value).length) return null
  const hit = new Set()
  for (const link of t.links) {
    const prop = linkProp(link, linkFilter.key)
    if (prop && matchFieldRule(prop.raw, linkFilter.op, linkFilter.value)) hit.add(link.key)
  }
  return hit
})

const filterCounts = computed(() => ({
  nodes: nodeMatches.value?.size ?? 0,
  links: linkMatches.value?.size ?? 0,
}))

const filterActive = computed(() => Boolean(nodeMatches.value || linkMatches.value))

const filterSummary = computed(() => {
  if (!filterActive.value) return ''
  const parts = []
  if (nodeMatches.value) parts.push(`点 ${filterCounts.value.nodes}/${stats.value.nodeCount}`)
  if (linkMatches.value) parts.push(`线 ${filterCounts.value.links}/${stats.value.linkCount}`)
  return parts.join(' · ')
})

/** 把筛选命中的点 / 线全部选中 */
function selectMatches() {
  if (!filterActive.value) {
    message.warning('请先填写筛选条件（属性 + 运算符 + 值）')
    return
  }
  selectedNodes.clear()
  selectedLinks.clear()
  if (nodeMatches.value) for (const id of nodeMatches.value) selectedNodes.add(id)
  if (linkMatches.value) for (const key of linkMatches.value) selectedLinks.add(key)
  message.info(`已选中筛选命中：点 ${selectedNodes.size} 个，线 ${selectedLinks.size} 条`)
  scheduleDraw()
}

/** 缩放到筛选命中结果 */
function zoomToMatches() {
  const t = topo.value
  if (!t || !filterActive.value) {
    message.warning('请先填写筛选条件（属性 + 运算符 + 值）')
    return
  }
  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  const push = (x, y) => {
    minX = Math.min(minX, x)
    maxX = Math.max(maxX, x)
    minY = Math.min(minY, y)
    maxY = Math.max(maxY, y)
  }
  if (nodeMatches.value) {
    for (const id of nodeMatches.value) {
      const node = t.nodeById.get(id)
      if (node) push(node.x, node.y)
    }
  }
  if (linkMatches.value) {
    for (const key of linkMatches.value) {
      const link = t.linkByKey.get(key)
      if (link) {
        push(link.ax, link.ay)
        push(link.bx, link.by)
      }
    }
  }
  if (minX === Infinity) {
    message.warning('筛选结果为空')
    return
  }
  const sx = (size.w - 80) / Math.max(0.2, maxX - minX)
  const sy = (size.h - 80) / Math.max(0.2, maxY - minY)
  centerOn((minX + maxX) / 2, (minY + maxY) / 2, Math.min(sx, sy))
}

function clearFilters() {
  nodeFilter.value = ''
  linkFilter.value = ''
  scheduleDraw()
}

/** 常用排查预设：一键设好属性 / 运算符 / 值 / 标注 */
function applyPreset(name) {
  if (name === 'noSpeed') {
    linkFilter.key = 'speed'
    linkFilter.op = '='
    linkFilter.value = '空'
    opt.linkLabel = 'speed'
  } else if (name === 'noRoad') {
    nodeFilter.key = 'roadProperty'
    nodeFilter.op = '='
    nodeFilter.value = '空'
    opt.nodeLabel = 'roadProperty'
  } else if (name === 'noRobotType') {
    linkFilter.key = 'robottype'
    linkFilter.op = '='
    linkFilter.value = '空'
    opt.linkLabel = 'robottype'
  } else {
    clearFilters()
    opt.nodeLabel = 'coord'
    opt.linkLabel = 'none'
    opt.onlyAbnormal = false
    opt.onlySelected = false
    opt.onlyMatched = true
    opt.dimUnmatched = true
    opt.hideUnmatched = false
    message.info('已恢复默认显示：点标签=坐标，无筛选')
    return
  }
  opt.onlyMatched = true
  scheduleDraw()
}

/** 用筛选属性做地图标注（点 / 线各自一键切换） */
function labelNodeFilterProp() {
  opt.nodeLabel = opt.nodeLabel === nodeFilter.key ? 'none' : nodeFilter.key
  message.info(`点标签：${opt.nodeLabel === 'none' ? '不显示' : nodeFilter.key}`)
}

function labelLinkFilterProp() {
  opt.linkLabel = opt.linkLabel === linkFilter.key ? 'none' : linkFilter.key
  message.info(`线标签：${opt.linkLabel === 'none' ? '不显示' : linkFilter.key}`)
}

/**
 * 标签可见性：默认「缩小隐藏」——缩得太小时只看点线本体（避免密密麻麻互相压字），
 * 放大到 labelMinZoom 以上才显示标签。
 */
const labelShown = computed(() => {
  if (!opt.labelZoomGate) return true
  return view.scale >= opt.labelMinZoom
})

/** 地图标签模式说明（状态栏用） */
const labelModeLabel = computed(() => {
  const node = nodeLabelOptions.find((o) => o.value === opt.nodeLabel)?.label ?? opt.nodeLabel
  const link = linkLabelOptions.find((o) => o.value === opt.linkLabel)?.label ?? opt.linkLabel
  const filters = []
  if (opt.onlyAbnormal) filters.push('仅异常')
  if (opt.onlySelected) filters.push('仅选中')
  if (opt.onlyMatched) filters.push('仅命中')
  return `点 ${node} / 线 ${link}${filters.length ? `（${filters.join('·')}）` : ''}`
})

const pickModeLabel = computed(() =>
  opt.pickMode === 'node' ? '分点' : opt.pickMode === 'link' ? '线' : '点线同选',
)

let rafId = 0
function scheduleDraw() {
  if (rafId) return
  rafId = requestAnimationFrame(() => {
    rafId = 0
    draw()
  })
}

function gridStep() {
  const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200]
  for (const step of steps) {
    if (step * view.scale >= 70) return step
  }
  return 500
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const { w, h, dpr } = size
  const c = palette.value
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.fillStyle = c.bg
  ctx.fillRect(0, 0, w, h)

  const t = topo.value
  if (!t) {
    ctx.fillStyle = c.hint
    ctx.font = '14px system-ui, -apple-system, Segoe UI, sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('请选择服务器地图 XML，或打开/拖入本地拓扑地图 XML', w / 2, h / 2)
    return
  }

  drawGrid(ctx, w, h)

  const vb = viewBounds()
  const matchedNodes = nodeMatches.value
  const matchedLinks = linkMatches.value
  const filtering = filterActive.value
  const dimUnmatched = filtering && opt.dimUnmatched
  const primaryNode = primary.value?.type === 'node' ? primary.value.key : null
  const relatedLinks = new Set()
  const relatedNodes = new Set()
  if (opt.highlightRelated && primaryNode !== null) {
    const node = t.nodeById.get(primaryNode)
    if (node) {
      relatedNodes.add(node.id)
      for (const nb of node.neighbors) {
        const key = node.id < nb.targetId ? `${node.id}_${nb.targetId}` : `${nb.targetId}_${node.id}`
        relatedLinks.add(key)
        relatedNodes.add(nb.targetId)
      }
    }
  }

  // ── 线段 ──
  if (opt.showLinks) {
    const hoverLink = hover.value?.type === 'link' ? hover.value.key : null
    ctx.lineJoin = 'round'
    ctx.lineCap = 'round'
    let arrowBudget = 1500
    for (const link of t.links) {
      if (link.ax < vb.minX - 2 && link.bx < vb.minX - 2) continue
      if (link.ax > vb.maxX + 2 && link.bx > vb.maxX + 2) continue
      if (link.ay < vb.minY - 2 && link.by < vb.minY - 2) continue
      if (link.ay > vb.maxY + 2 && link.by > vb.maxY + 2) continue
      const selected = selectedLinks.has(link.key)
      const isHover = hoverLink === link.key
      const related = relatedLinks.has(link.key)
      const matched = matchedLinks ? matchedLinks.has(link.key) : false
      if (dimUnmatched && opt.hideUnmatched && !matched) continue
      ctx.strokeStyle = matched
        ? c.match
        : dimUnmatched
          ? c.dim
          : selected
            ? c.selLink
            : isHover
              ? c.linkHover
              : related
                ? c.related
                : c.link
      ctx.lineWidth = matched ? 2.8 : selected ? 2.4 : isHover || related ? 1.8 : 1
      for (const poly of link.polylines) {
        if (poly.points.length === 2 && poly.points[0].x === poly.points[1].x && poly.points[0].y === poly.points[1].y) {
          continue
        }
        ctx.beginPath()
        const p0 = toScreen(poly.points[0].x, poly.points[0].y)
        ctx.moveTo(p0.x, p0.y)
        for (let i = 1; i < poly.points.length; i += 1) {
          const p = toScreen(poly.points[i].x, poly.points[i].y)
          ctx.lineTo(p.x, p.y)
        }
        ctx.stroke()
      }
      if (opt.showArrows && view.scale >= 6 && arrowBudget > 0) {
        const color = selected ? c.selLink : isHover ? c.linkHover : c.link
        for (const [srcId, dir] of Object.entries(link.dirs)) {
          const from = t.nodeById.get(Number(srcId))
          const to = t.nodeById.get(dir.targetId)
          if (!from || !to) continue
          drawArrow(ctx, from, to, color)
          arrowBudget -= 1
          if (arrowBudget <= 0) break
        }
      }
    }
  }

  // ── 节点 ──
  if (opt.showNodes) {
    const r = opt.nodeRadius
    const hoverNode = hover.value?.type === 'node' ? hover.value.key : null
    for (const node of t.nodes) {
      const p = toScreen(node.x, node.y)
      if (p.x < -r - 2 || p.x > w + r + 2 || p.y < -r - 2 || p.y > h + r + 2) continue
      const selected = selectedNodes.has(node.id)
      const isPrimary = primaryNode === node.id
      const isHover = hoverNode === node.id
      const related = relatedNodes.has(node.id)
      const road = opt.markRoadProperty && node.roadProperty === 1
      const matched = matchedNodes ? matchedNodes.has(node.id) : false
      if (dimUnmatched && opt.hideUnmatched && !matched) continue

      ctx.beginPath()
      if (road) {
        ctx.rect(p.x - r * 1.15, p.y - r * 1.15, r * 2.3, r * 2.3)
      } else {
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2)
      }
      ctx.fillStyle = matched
        ? c.match
        : dimUnmatched
          ? c.dim
          : selected
            ? c.selNode
            : isHover
              ? c.linkHover
              : road
                ? c.nodeRoad
                : related
                  ? c.related
                  : c.node
      ctx.fill()
      if (matched) {
        ctx.lineWidth = 1.6
        ctx.strokeStyle = c.matchRing
        ctx.beginPath()
        ctx.arc(p.x, p.y, r + 2.5, 0, Math.PI * 2)
        ctx.stroke()
      }
      if (isPrimary) {
        ctx.lineWidth = 2
        ctx.strokeStyle = c.selNode
        ctx.beginPath()
        ctx.arc(p.x, p.y, r + 3.5, 0, Math.PI * 2)
        ctx.stroke()
      }
    }
  }

  // ── 标签（批量属性） ──
  drawLabels(ctx, t)

  // ── 框选矩形 ──
  if (marquee.value) {
    const { x0, y0, x1, y1 } = marquee.value
    const left = Math.min(x0, x1)
    const top = Math.min(y0, y1)
    const width = Math.abs(x1 - x0)
    const height = Math.abs(y1 - y0)
    ctx.fillStyle = c.marquee
    ctx.fillRect(left, top, width, height)
    ctx.strokeStyle = c.marqueeBorder
    ctx.lineWidth = 1
    ctx.setLineDash([5, 4])
    ctx.strokeRect(left + 0.5, top + 0.5, width, height)
    ctx.setLineDash([])

    const world = marqueeWorld()
    if (world) {
      ctx.fillStyle = c.labelBg
      ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, monospace'
      ctx.textAlign = 'left'
      ctx.textBaseline = 'bottom'
      const counts = marqueeCounts(world)
      const hit = counts
        ? `   框内：点 ${counts.nodes} / 线 ${counts.links}`
        : ''
      const text = `X ${formatMeters(world.minX)} ~ ${formatMeters(world.maxX)} m   Y ${formatMeters(world.minY)} ~ ${formatMeters(world.maxY)} m${hit}`
      const tw = ctx.measureText(text).width
      ctx.fillRect(left, top - 20, tw + 10, 18)
      ctx.fillStyle = c.label
      ctx.fillText(text, left + 5, top - 4)
    }
  }
}

function drawArrow(ctx, from, to, color) {
  const p1 = toScreen(from.x, from.y)
  const p2 = toScreen(to.x, to.y)
  const dx = p2.x - p1.x
  const dy = p2.y - p1.y
  const len = Math.hypot(dx, dy)
  if (len < 26) return
  const midX = (p1.x + p2.x) / 2
  const midY = (p1.y + p2.y) / 2
  const ux = dx / len
  const uy = dy / len
  const size = 5.5
  ctx.beginPath()
  ctx.moveTo(midX + ux * size, midY + uy * size)
  ctx.lineTo(midX - ux * size - uy * size * 0.7, midY - uy * size + ux * size * 0.7)
  ctx.lineTo(midX - ux * size + uy * size * 0.7, midY - uy * size - ux * size * 0.7)
  ctx.closePath()
  ctx.fillStyle = color
  ctx.fill()
}

function drawGrid(ctx, w, h) {
  const c = palette.value
  const step = gridStep()
  const vb = viewBounds()
  ctx.strokeStyle = c.grid
  ctx.lineWidth = 1
  ctx.beginPath()
  for (let x = Math.ceil(vb.minX / step) * step; x <= vb.maxX; x += step) {
    const p = toScreen(x, 0)
    ctx.moveTo(Math.round(p.x) + 0.5, 0)
    ctx.lineTo(Math.round(p.x) + 0.5, h)
  }
  for (let y = Math.ceil(vb.minY / step) * step; y <= vb.maxY; y += step) {
    const p = toScreen(0, y)
    ctx.moveTo(0, Math.round(p.y) + 0.5)
    ctx.lineTo(w, Math.round(p.y) + 0.5)
  }
  ctx.stroke()

  ctx.fillStyle = c.axis
  ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'top'
  for (let x = Math.ceil(vb.minX / step) * step; x <= vb.maxX; x += step) {
    const p = toScreen(x, 0)
    ctx.fillText(`${x.toFixed(step < 1 ? 1 : 0)}`, p.x + 3, 3)
  }
  ctx.textAlign = 'left'
  ctx.textBaseline = 'bottom'
  for (let y = Math.ceil(vb.minY / step) * step; y <= vb.maxY; y += step) {
    const p = toScreen(0, y)
    ctx.fillText(`${y.toFixed(step < 1 ? 1 : 0)}`, 3, p.y - 3)
  }
}

function drawLabels(ctx, t) {
  const showAll = labelShown.value
  const nodeKey = opt.nodeLabel
  const linkKey = opt.linkLabel
  const wantNodes = nodeKey !== 'none'
  const wantLinks = linkKey !== 'none'
  if (!wantNodes && !wantLinks) return
  const c = palette.value
  const w = size.w
  const h = size.h
  const occupied = []
  let count = 0

  /** 与已画标签重叠就不再画，避免密集点位上标签重复叠字 */
  const overlaps = (x, y, tw, th) => {
    const start = Math.max(0, occupied.length - 220)
    for (let i = start; i < occupied.length; i += 1) {
      const r = occupied[i]
      if (x < r.x + r.w && x + tw > r.x && y < r.y + r.h && y + th > r.y) return true
    }
    return false
  }

  /** 统一的标签绘制：选中项带底色，异常属性用红字 */
  const paint = (x, y, text, { selected, abnormal }) => {
    if (count > 1500) return
    ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, monospace'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    const tw = ctx.measureText(text).width
    const box = { x: x - 2, y: y - 8, w: tw + 5, h: 15 }
    if (overlaps(box.x, box.y, box.w, box.h)) return
    count += 1
    occupied.push(box)
    if (selected) {
      ctx.fillStyle = c.labelBg
      ctx.fillRect(box.x, box.y, box.w, box.h)
    }
    ctx.fillStyle = abnormal ? c.warn : selected ? c.label : c.hint
    ctx.fillText(text, x, y)
  }

  const matchedNodes = nodeMatches.value
  const matchedLinks = linkMatches.value
  const filtering = filterActive.value
  // 有筛选且开启「只标注命中项」时：画布只标筛选出来的点 / 线（不再标全部）
  const restrictMatch = filtering && opt.onlyMatched
  const gateOpen = showAll || opt.onlySelected || restrictMatch

  if (wantNodes && gateOpen) {
    for (const node of t.nodes) {
      const selected = selectedNodes.has(node.id)
      if (opt.onlySelected && !selected) continue
      if (restrictMatch && matchedNodes && !matchedNodes.has(node.id)) continue
      if (restrictMatch && !matchedNodes) continue
      const value = nodeProp(node, nodeKey)
      if (!value) break
      if (opt.onlyAbnormal && !value.abnormal && !selected) continue
      const p = toScreen(node.x, node.y)
      if (p.x < -60 || p.x > w + 60 || p.y < -20 || p.y > h + 20) continue
      paint(p.x + opt.nodeRadius + 4, p.y, value.text, { selected, abnormal: value.abnormal })
    }
  }

  if (wantLinks && gateOpen) {
    for (const link of t.links) {
      const selected = selectedLinks.has(link.key)
      if (opt.onlySelected && !selected) continue
      if (restrictMatch && matchedLinks && !matchedLinks.has(link.key)) continue
      if (restrictMatch && !matchedLinks) continue
      const value = linkProp(link, linkKey)
      if (!value) break
      if (opt.onlyAbnormal && !value.abnormal && !selected) continue
      const mid = pointOnPolylineAt(link.path, 0.5)
      if (!mid) continue
      const p = toScreen(mid.x, mid.y)
      if (p.x < -60 || p.x > w + 60 || p.y < -20 || p.y > h + 20) continue
      paint(p.x + 4, p.y - 8, value.text, { selected, abnormal: value.abnormal })
    }
  }
}

/* ─────────────────────────── 拾取 / 选择 ─────────────────────────── */

function canvasPos(event) {
  const canvas = canvasRef.value
  const rect = canvas.getBoundingClientRect()
  return { x: event.clientX - rect.left, y: event.clientY - rect.top }
}

function hitTest(sx, sy) {
  const t = topo.value
  if (!t) return null

  const wantNode = opt.pickMode !== 'link'
  const wantLink = opt.pickMode !== 'node'

  // 1) 节点
  const nodeTol = Math.max(7, opt.nodeRadius + 5)
  let bestNode = null
  let bestDist = Infinity
  if (opt.showNodes && wantNode) {
    for (const node of t.nodes) {
      const p = toScreen(node.x, node.y)
      if (Math.abs(p.x - sx) > nodeTol || Math.abs(p.y - sy) > nodeTol) continue
      const d = Math.hypot(p.x - sx, p.y - sy)
      if (d <= nodeTol && d < bestDist) {
        bestDist = d
        bestNode = node
      }
    }
  }
  if (bestNode) return { type: 'node', node: bestNode }

  // 2) 线段
  if (opt.showLinks && wantLink) {
    const world = toWorld(sx, sy)
    const worldTol = 6 / view.scale
    let bestLink = null
    let bestWorld = Infinity
    for (const link of t.links) {
      let d = Infinity
      for (const poly of link.polylines) {
        const local = distanceToPolyline(world.x, world.y, poly.points)
        if (local < d) d = local
      }
      if (d < bestWorld) {
        bestWorld = d
        bestLink = link
      }
    }
    if (bestLink && bestWorld <= worldTol) return { type: 'link', link: bestLink }
  }
  return null
}

function marqueeWorld() {
  if (!marquee.value) return null
  const a = toWorld(marquee.value.x0, marquee.value.y0)
  const b = toWorld(marquee.value.x1, marquee.value.y1)
  return {
    minX: Math.min(a.x, b.x),
    maxX: Math.max(a.x, b.x),
    minY: Math.min(a.y, b.y),
    maxY: Math.max(a.y, b.y),
  }
}

function nodeMatched(node, rect) {
  if (opt.nodeRule === 'inside') return pointInRect(node.x, node.y, rect)
  const pad = opt.nodeRadius / view.scale + 0.05
  return (
    node.x >= rect.minX - pad &&
    node.x <= rect.maxX + pad &&
    node.y >= rect.minY - pad &&
    node.y <= rect.maxY + pad
  )
}

function linkMatched(link, rect) {
  const t = topo.value
  if (opt.linkRule === 'endpoints') {
    const a = t.nodeById.get(link.a)
    const b = t.nodeById.get(link.b)
    return Boolean(a && b && nodeMatched(a, rect) && nodeMatched(b, rect))
  }
  if (opt.linkRule === 'cross') {
    return link.polylines.some((poly) => polylineIntersectsRect(poly.points, rect))
  }
  // both：两端点都在框内，或折线与框相交
  const a = t.nodeById.get(link.a)
  const b = t.nodeById.get(link.b)
  if (a && b && nodeMatched(a, rect) && nodeMatched(b, rect)) return true
  return link.polylines.some((poly) => polylineIntersectsRect(poly.points, rect))
}

/** 框选过程中实时预览将命中的点 / 线数量（按当前判定规则） */
function marqueeCounts(rect) {
  const t = topo.value
  if (!t || !rect) return null
  const wantNodes = opt.pickMode !== 'link'
  const wantLinks = opt.pickMode !== 'node'
  let nodes = 0
  let links = 0
  if (wantNodes) {
    for (const node of t.nodes) if (nodeMatched(node, rect)) nodes += 1
  }
  if (wantLinks) {
    for (const link of t.links) if (linkMatched(link, rect)) links += 1
  }
  return { nodes, links }
}

/** 框选提交：画布上已实时显示框内点/线数量，这里不再弹消息提示 */
function commitMarquee(additive) {
  const t = topo.value
  const rect = marqueeWorld()
  if (!t || !rect) return
  const wantNodes = opt.pickMode !== 'link'
  const wantLinks = opt.pickMode !== 'node'
  if (!additive) {
    if (wantNodes) selectedNodes.clear()
    if (wantLinks) selectedLinks.clear()
  }
  if (wantNodes) {
    for (const node of t.nodes) {
      if (nodeMatched(node, rect)) selectedNodes.add(node.id)
    }
  }
  if (wantLinks) {
    for (const link of t.links) {
      if (linkMatched(link, rect)) selectedLinks.add(link.key)
    }
  }
  lastBox.value = rect
  scheduleDraw()
}

function handlePick(hit, additive) {
  if (!hit) {
    if (!additive) {
      selectedNodes.clear()
      selectedLinks.clear()
      primary.value = null
    }
    scheduleDraw()
    return
  }
  if (hit.type === 'node') {
    const id = hit.node.id
    if (additive) {
      if (selectedNodes.has(id)) selectedNodes.delete(id)
      else selectedNodes.add(id)
    } else {
      selectedNodes.clear()
      selectedLinks.clear()
      selectedNodes.add(id)
    }
    primary.value = { type: 'node', key: id }
  } else {
    const key = hit.link.key
    if (additive) {
      if (selectedLinks.has(key)) selectedLinks.delete(key)
      else selectedLinks.add(key)
    } else {
      selectedNodes.clear()
      selectedLinks.clear()
      selectedLinks.add(key)
    }
    primary.value = { type: 'link', key }
  }
  scheduleDraw()
}

/* ─────────────────────────── 交互事件 ─────────────────────────── */

const drag = {
  mode: null,
  startX: 0,
  startY: 0,
  lastX: 0,
  lastY: 0,
  moved: false,
  additive: false,
}
const pointers = new Map()
let pinch = null

function onPointerDown(event) {
  const canvas = canvasRef.value
  if (!canvas || !topo.value) return
  const p = canvasPos(event)
  pointers.set(event.pointerId, { x: p.x, y: p.y })
  if (pointers.size === 2) {
    const [a, b] = [...pointers.values()]
    pinch = {
      dist: Math.hypot(a.x - b.x, a.y - b.y),
      center: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
      scale: view.scale,
    }
    drag.mode = 'pinch'
    marquee.value = null
    return
  }
  const additive = event.ctrlKey || event.metaKey || event.shiftKey
  const wantPan = event.button !== 0 || opt.panMode || event.altKey || event.shiftKey
  try {
    canvas.setPointerCapture?.(event.pointerId)
  } catch {
    /* 合成事件 / 无效 pointerId 时忽略 */
  }
  drag.moved = false
  drag.additive = additive
  drag.startX = p.x
  drag.startY = p.y
  drag.lastX = p.x
  drag.lastY = p.y
  if (wantPan) {
    drag.mode = 'pan'
    canvas.style.cursor = 'grabbing'
  } else {
    drag.mode = 'box'
    marquee.value = { x0: p.x, y0: p.y, x1: p.x, y1: p.y }
  }
}

function onPointerMove(event) {
  const canvas = canvasRef.value
  if (!canvas || !topo.value) return
  const p = canvasPos(event)
  if (pointers.has(event.pointerId)) pointers.set(event.pointerId, { x: p.x, y: p.y })

  if (drag.mode === 'pinch' && pinch && pointers.size >= 2) {
    const [a, b] = [...pointers.values()]
    const dist = Math.hypot(a.x - b.x, a.y - b.y)
    const center = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
    if (pinch.dist > 0) {
      const before = toWorld(pinch.center.x, pinch.center.y)
      view.scale = clampScale((pinch.scale * dist) / pinch.dist)
      view.cx = before.x - (center.x - size.w / 2) / view.scale
      view.cy = before.y + (center.y - size.h / 2) / view.scale
      scheduleDraw()
    }
    return
  }

  cursorWorld.value = toWorld(p.x, p.y)

  if (drag.mode === 'pan') {
    const dx = p.x - drag.lastX
    const dy = p.y - drag.lastY
    if (Math.abs(p.x - drag.startX) + Math.abs(p.y - drag.startY) > 3) drag.moved = true
    drag.lastX = p.x
    drag.lastY = p.y
    view.cx -= dx / view.scale
    view.cy += dy / view.scale
    hover.value = null
    scheduleDraw()
    return
  }

  if (drag.mode === 'box') {
    if (Math.abs(p.x - drag.startX) + Math.abs(p.y - drag.startY) > 3) drag.moved = true
    marquee.value = { x0: drag.startX, y0: drag.startY, x1: p.x, y1: p.y }
    scheduleDraw()
    return
  }

  // hover：只记录命中对象用于高亮，属性统一在「属性」页签查看
  const hit = hitTest(p.x, p.y)
  if (hit) {
    const key = hit.type === 'node' ? hit.node.id : hit.link.key
    hover.value = { type: hit.type, key }
    canvas.style.cursor = 'pointer'
  } else {
    hover.value = null
    canvas.style.cursor = drag.mode ? 'grabbing' : opt.panMode ? 'grab' : 'crosshair'
  }
  scheduleDraw()
}

function onPointerUp(event) {
  const canvas = canvasRef.value
  pointers.delete(event.pointerId)
  const mode = drag.mode
  drag.mode = null
  if (canvas) canvas.style.cursor = opt.panMode ? 'grab' : 'crosshair'
  if (pointers.size < 2) pinch = null
  if (!topo.value) return

  if (mode === 'box') {
    if (drag.moved) {
      commitMarquee(drag.additive)
    } else {
      const p = canvasPos(event)
      handlePick(hitTest(p.x, p.y), drag.additive)
    }
    marquee.value = null
    scheduleDraw()
  } else if (mode === 'pan' && !drag.moved) {
    const p = canvasPos(event)
    const hit = hitTest(p.x, p.y)
    if (event.button === 2) {
      openContextMenu(event, hit)
    } else {
      handlePick(hit, drag.additive)
    }
  }
}

function onPointerLeave() {
  hover.value = null
  cursorWorld.value = null
  scheduleDraw()
}

function onWheel(event) {
  event.preventDefault()
  const p = canvasPos(event)
  const factor = Math.exp(-event.deltaY * (event.deltaMode === 1 ? 0.05 : 0.0015))
  zoomBy(factor, p)
}

function onKeyDown(event) {
  const target = event.target
  if (target instanceof HTMLElement && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
  const key = event.key.toLowerCase()
  if (key === 'escape') {
    if (ctxMenu.value) {
      closeCtxMenu()
      return
    }
    if (isFullscreen.value) return // 全屏下首个 Esc 交给浏览器退出全屏
    clearSelection()
  } else if (key === 'f') {
    fitView()
  } else if (key === 'f11') {
    event.preventDefault()
    toggleFullscreen()
  } else if (key === '+' || key === '=') {
    event.preventDefault()
    zoomBy(1.25)
  } else if (key === '-' || key === '_') {
    event.preventDefault()
    zoomBy(1 / 1.25)
  } else if (key.startsWith('arrow')) {
    event.preventDefault()
    panByKey(key, event.ctrlKey || event.shiftKey ? 240 : 60)
  } else if (key === 'home') {
    event.preventDefault()
    fitView()
  } else if (key === 'l') {
    toggleLabels()
  } else if (key === 'b') {
    opt.panMode = false
  } else if (key === 'v' || key === 'h') {
    opt.panMode = true
  } else if (key === 'z') {
    zoomToSelection()
  } else if (key === '1') {
    setPickMode('node')
  } else if (key === '2') {
    setPickMode('link')
  } else if (key === '3') {
    setPickMode('both')
  } else if (key === 'e') {
    expandNeighbors()
  }
}

function setPickMode(mode) {
  if (opt.pickMode === mode) return
  opt.pickMode = mode
  hover.value = null
  scheduleDraw()
}

/* ─────────────────────────── 选择集操作 ─────────────────────────── */

function clearSelection() {
  selectedNodes.clear()
  selectedLinks.clear()
  primary.value = null
  lastBox.value = null
  scheduleDraw()
}

function selectOnlyNodes() {
  selectedLinks.clear()
  scheduleDraw()
}

/** 把已选点的邻接点一并加入选择（成片取地码时很有用） */
function expandNeighbors() {
  const t = topo.value
  if (!t) return
  if (!selectedNodes.size) {
    message.warning('请先选中至少 1 个点')
    return
  }
  const add = new Set()
  for (const id of selectedNodes) {
    const node = t.nodeById.get(id)
    if (!node) continue
    for (const nb of node.neighbors) add.add(nb.targetId)
  }
  let n = 0
  for (const id of add) {
    if (!t.nodeById.has(id) || selectedNodes.has(id)) continue
    selectedNodes.add(id)
    n += 1
  }
  message.info(`已加入 ${n} 个邻接点（现共 ${selectedNodes.size} 个点）`)
  scheduleDraw()
}

/** 标签总开关（L 键）：点 / 线标签一起开或关 */
function toggleLabels() {
  const off = opt.nodeLabel === 'none' && opt.linkLabel === 'none'
  if (off) {
    opt.nodeLabel = 'coord'
    message.info(`标签已显示：${labelModeLabel.value}`)
  } else {
    opt.nodeLabel = 'none'
    opt.linkLabel = 'none'
    message.info('标签已隐藏（L 键恢复）')
  }
  scheduleDraw()
}

/** 方向键平移视图 */
function panByKey(key, step) {
  const sx = key === 'arrowright' ? 1 : key === 'arrowleft' ? -1 : 0
  const sy = key === 'arrowup' ? 1 : key === 'arrowdown' ? -1 : 0
  if (!sx && !sy) return
  view.cx += (sx * step) / view.scale
  view.cy += (sy * step) / view.scale
  scheduleDraw()
}

const activeTab = ref('points')

function focusProps() {
  activeTab.value = 'props'
}

function codeOf(x, y) {
  return makeGroundCode(x, y, mapCode.value.trim(), { pad: padDigits.value })
}

/* ─────────────────────────── 全屏 / 侧栏 ─────────────────────────── */

async function toggleFullscreen() {
  const el = pageRef.value ?? document.documentElement
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen()
    } else if (typeof el?.requestFullscreen === 'function') {
      await el.requestFullscreen({ navigationUI: 'hide' })
    } else {
      message.warning('当前浏览器不支持网页全屏，可用 F11 系统全屏')
    }
  } catch (error) {
    message.warning(`全屏切换失败：${error?.message ?? error}`)
  }
}

function onFullscreenChange() {
  isFullscreen.value = Boolean(document.fullscreenElement)
  nextTick(() => syncSize())
}

/* ─────────────────────────── 右键菜单 / 双击 ─────────────────────────── */

function closeCtxMenu() {
  ctxMenu.value = null
}

function onGlobalPointerDown(event) {
  if (!ctxMenu.value) return
  const el = event.target
  if (el instanceof HTMLElement && el.closest('.ctx-menu')) return
  closeCtxMenu()
}

/** 右键菜单：点 / 线 / 空白 各自的常用操作 */
function openContextMenu(event, hit) {
  const p = canvasPos(event)
  const items = []
  if (hit?.type === 'node') {
    const node = hit.node
    items.push({
      key: 'props',
      label: `属性：节点 ${node.id}`,
      run: () => {
        primary.value = { type: 'node', key: node.id }
        focusProps()
      },
    })
    items.push({ key: 'code', label: '复制该点地码', run: () => copyText(codeOf(node.x, node.y), `已复制 ${codeOf(node.x, node.y)}`) })
    items.push({ key: 'locate', label: '定位并放大到该点', run: () => locateNodeRow({ id: node.id }) })
    items.push({
      key: 'neighbors',
      label: '选中该点及其邻接点',
      run: () => {
        selectedNodes.clear()
        selectedLinks.clear()
        selectedNodes.add(node.id)
        expandNeighbors()
      },
    })
  } else if (hit?.type === 'link') {
    const link = hit.link
    const mid = pointOnPolylineAt(link.path, 0.5) ?? { x: (link.ax + link.bx) / 2, y: (link.ay + link.by) / 2 }
    items.push({
      key: 'props',
      label: `属性：线段 ${link.a} → ${link.b}`,
      run: () => {
        primary.value = { type: 'link', key: link.key }
        focusProps()
      },
    })
    items.push({ key: 'code', label: '复制中点地码', run: () => copyText(codeOf(mid.x, mid.y), `已复制 ${codeOf(mid.x, mid.y)}`) })
    items.push({ key: 'locate', label: '定位并放大到该线', run: () => locateLinkRow({ key: link.key }) })
    items.push({
      key: 'speed',
      label: '排查：所有没设限速的线段',
      run: () => {
        applyPreset('noSpeed')
        activeTab.value = 'display'
      },
    })
  } else {
    items.push({ key: 'fit', label: '适应视图（F）', run: () => fitView() })
    items.push({ key: 'full', label: isFullscreen.value ? '退出网页全屏（F11）' : '网页全屏（F11）', run: () => toggleFullscreen() })
    items.push({ key: 'labels', label: '显示 / 隐藏标签（L）', run: () => toggleLabels() })
    items.push({ key: 'side', label: showSide.value ? '收起侧栏' : '展开侧栏', run: () => { showSide.value = !showSide.value } })
    items.push({ key: 'clear', label: '清空选择（Esc）', run: () => clearSelection() })
  }
  if (!items.length) return
  const width = 232
  const height = items.length * 30 + 10
  ctxMenu.value = {
    x: Math.max(4, Math.min(p.x, size.w - width - 4)),
    y: Math.max(4, Math.min(p.y, size.h - height - 4)),
    items,
  }
}

function runCtxItem(item) {
  closeCtxMenu()
  if (item?.disabled) return
  item?.run?.()
}

/** 双击：点 / 线 → 打开属性页签并放大；空白 → 以光标为中心放大 */
function onCanvasDblClick(event) {
  if (!topo.value) return
  const p = canvasPos(event)
  const hit = hitTest(p.x, p.y)
  if (hit?.type === 'node') {
    selectedNodes.add(hit.node.id)
    primary.value = { type: 'node', key: hit.node.id }
    focusProps()
    centerOn(hit.node.x, hit.node.y, Math.max(view.scale * 1.4, 30))
  } else if (hit?.type === 'link') {
    selectedLinks.add(hit.link.key)
    primary.value = { type: 'link', key: hit.link.key }
    focusProps()
    centerOn((hit.link.ax + hit.link.bx) / 2, (hit.link.ay + hit.link.by) / 2, Math.max(view.scale * 1.4, 25))
  } else {
    zoomBy(1.6, p)
  }
  scheduleDraw()
}

/** 两节点之间的无向线段 key */
function linkKeyOf(a, b) {
  return a < b ? `${a}_${b}` : `${b}_${a}`
}

/* ─────────────────────────── 列表 / 地码 ─────────────────────────── */

const selectedNodeRows = computed(() => {
  const t = topo.value
  if (!t) return []
  const mc = mapCode.value.trim()
  const pad = padDigits.value
  return [...selectedNodes]
    .map((id) => t.nodeById.get(id))
    .filter(Boolean)
    .sort((a, b) => a.id - b.id)
    .map((node, index) => ({
      idx: index + 1,
      id: node.id,
      x: node.x,
      y: node.y,
      value: node.value,
      roadProperty: node.roadProperty,
      neighborCount: node.neighbors.length,
      code: makeGroundCode(node.x, node.y, mc, { pad }),
    }))
})

const selectedLinkRows = computed(() => {
  const t = topo.value
  if (!t) return []
  return [...selectedLinks]
    .map((key) => t.linkByKey.get(key))
    .filter(Boolean)
    .sort((a, b) => a.a - b.a || a.b - b.b)
    .map((link, index) => ({
      idx: index + 1,
      key: link.key,
      a: link.a,
      b: link.b,
      distance: link.distance,
      directed: link.directed,
      curved: link.curved,
      speed: Math.max(0, ...Object.values(link.dirs).map((d) => d.speed || 0)),
    }))
})

/** 节点备注模板：支持 {id} {x} {y} {code} */
function remarkForNode(row) {
  const tpl = nodeRemarkTpl.value ?? ''
  return tpl.replace(/\{(\w+)\}/g, (raw, key) => {
    if (key === 'id') return String(row.id)
    if (key === 'x') return formatMeters(row.x)
    if (key === 'y') return formatMeters(row.y)
    if (key === 'code') return row.code
    return raw
  })
}

/** 打印用条目：已选节点 */
const codeEntries = computed(() => {
  const rows = selectedNodeRows.value.map((row) => ({
    kind: 'node',
    id: row.id,
    x: row.x,
    y: row.y,
    code: row.code,
    remark: remarkForNode(row),
  }))
  const mode = sortMode.value
  rows.sort((a, b) => {
    if (mode === 'id') return a.id - b.id
    if (mode === 'yx') return a.y - b.y || a.x - b.x
    return a.x - b.x || a.y - b.y
  })
  if (!dedupeCodes.value) return rows
  const seen = new Set()
  return rows.filter((row) => {
    if (seen.has(row.code)) return false
    seen.add(row.code)
    return true
  })
})

/** 打印地码 CSV（仅两列：打印码值,备注） */
const csvText = computed(() => buildCodesCsv(codeEntries.value))

const activeNode = computed(() => {
  if (primary.value?.type !== 'node') return null
  return topo.value?.nodeById.get(primary.value.key) ?? null
})

const activeLink = computed(() => {
  if (primary.value?.type !== 'link') return null
  return topo.value?.linkByKey.get(primary.value.key) ?? null
})

/* ─────────────────────────── 点 / 线 详细属性 ─────────────────────────── */

/** 属性面板当前对象：节点 → 线段 */
const propsTarget = computed(() => {
  if (activeNode.value) return { type: 'node', node: activeNode.value }
  if (activeLink.value) return { type: 'link', link: activeLink.value }
  return null
})

const propsTypeLabel = computed(() => {
  const t = propsTarget.value
  if (!t) return ''
  if (t.type === 'node') return `节点 ${t.node.id}`
  return `线段 ${t.link.a} → ${t.link.b}`
})

function nodePropRows(node) {
  const pad = padDigits.value
  return [
    { label: 'ID', value: String(node.id) },
    { label: '坐标（m）', value: `X ${formatMeters(node.x)} / Y ${formatMeters(node.y)}` },
    { label: '坐标（mm）', value: `X ${formatMillimeters(node.x, pad)} / Y ${formatMillimeters(node.y, pad)}` },
    { label: '地码', value: codeOf(node.x, node.y) },
    { label: '邻接线段', value: `${node.neighbors.length} 条${node.isEmpty ? '（孤立点）' : ''}` },
    { label: 'value', value: String(node.value) },
    { label: 'RoadProperty', value: `${node.roadProperty}${node.roadProperty === 1 ? '（道路属性点，画布用方块标记）' : ''}` },
    { label: 'allDir', value: String(node.allDir) },
    { label: 'EleDir / ElePre', value: `${node.eleDir === '' ? '-' : node.eleDir} / ${node.elePre}` },
    { label: 'RotRad', value: `${node.rotRad} rad（${((node.rotRad * 180) / Math.PI).toFixed(1)}°）` },
    { label: 'robottype', value: node.robotType || '-' },
    { label: 'RotarySwitch / sensorSwitch', value: `${node.rotarySwitch} / ${node.sensorswitchPoint}` },
    { label: 'PioPoint / CtuStance', value: `${node.pioPoint} / ${node.ctuStance}` },
    { label: 'TranZoneType', value: String(node.tranZoneType) },
    { label: '尺寸（m）', value: `${formatMeters(node.width)} × ${formatMeters(node.height)}` },
    { label: '原始字段', value: Object.entries(node.props ?? {}).map(([k, v]) => `${k}=${v}`).join('  ') || '-' },
  ]
}

function linkPropRows(link) {
  const t = topo.value
  const pad = padDigits.value
  const na = t?.nodeById.get(link.a)
  const nb = t?.nodeById.get(link.b)
  const mid = pointOnPolylineAt(link.path, 0.5)
  const speeds = Object.values(link.dirs).map((d) => d.speed || 0)
  return [
    { label: '线段', value: `${link.a} → ${link.b}（key ${link.key}）` },
    { label: '长度（m）', value: `${formatMeters(link.distance)}（折线 ${formatMeters(polylineLength(link.path))}）` },
    { label: '方向 / 几何', value: `${link.directed ? '双向' : '单向'} / ${link.curved ? `曲线（${link.path.length} 点）` : '直线'}` },
    { label: '有向段', value: `${Object.keys(link.dirs).length} 条（A→B ${link.dirs[link.a] ? '有' : '无'}，B→A ${link.dirs[link.b] ? '有' : '无'}）` },
    { label: '最大限速', value: speeds.length ? String(Math.max(...speeds)) : '-' },
    { label: '折线控制点', value: link.path.length > 2 ? link.path.slice(1, -1).map((p) => `(${formatMeters(p.x)}, ${formatMeters(p.y)})`).join(' ') : '-' },
    { label: '中点地码', value: mid ? codeOf(mid.x, mid.y) : '-' },
    {
      label: `端点 ${link.a}`,
      value: na ? `X ${formatMeters(na.x)} / Y ${formatMeters(na.y)} · ${codeOf(na.x, na.y)}` : '缺失',
    },
    {
      label: `端点 ${link.b}`,
      value: nb ? `X ${formatMeters(nb.x)} / Y ${formatMeters(nb.y)} · ${codeOf(nb.x, nb.y)}` : '缺失',
    },
    { label: '位数 / 地图代码', value: `${pad} 位 / ${mapCode.value.trim() || '-'}` },
  ]
}

const propsRows = computed(() => {
  const p = propsTarget.value
  if (!p) return []
  if (p.type === 'node') return nodePropRows(p.node)
  return linkPropRows(p.link)
})

/** 关联线段（节点属性页签）：邻接表，可点击跳转 */
const neighborRows = computed(() => {
  const t = topo.value
  const node = activeNode.value
  if (!t || !node) return []
  return node.neighbors
    .map((nb) => {
      const other = t.nodeById.get(nb.targetId)
      return {
        targetId: nb.targetId,
        distance: nb.distance ?? (other ? Math.hypot(other.x - node.x, other.y - node.y) : 0),
        speed: Number(nb.attrs?.Speed ?? 0),
        revert: Number(nb.attrs?.Rever ?? 0),
        robotType: nb.attrs?.robottype ?? '',
        curved: Boolean(nb.ctrlPoints?.length),
        exists: Boolean(other),
      }
    })
    .sort((a, b) => a.targetId - b.targetId)
})

const neighborColumns = [
  { title: '邻接点', key: 'targetId', width: 68 },
  { title: '长度(m)', key: 'distance', width: 86, render: (row) => formatMeters(row.distance) },
  { title: '限速', key: 'speed', width: 62, render: (row) => (row.speed ? row.speed : '-') },
  { title: 'Rever', key: 'revert', width: 62 },
  { title: '几何', key: 'curved', width: 58, render: (row) => (row.curved ? '曲线' : '直线') },
  { title: 'robottype', key: 'robotType', minWidth: 84, render: (row) => row.robotType || '-' },
]

/** 有向段明细（线段属性页签） */
const linkDirRows = computed(() => {
  const link = activeLink.value
  if (!link) return []
  return Object.entries(link.dirs).map(([srcId, d]) => ({
    key: `${link.key}_${srcId}`,
    dir: `${srcId} → ${d.targetId}`,
    speed: d.speed || 0,
    revert: d.revert,
    emptyCantRun: d.emptyCantRun,
    podDir: d.podDir,
    startDir: d.startDir || '-',
    stopDir: d.stopDir || '-',
    laserType: d.laserType,
    robotType: d.robotType || '-',
    carryType: d.carryType || '-',
    ctnrtype: d.ctnrtype || '-',
    ctrlCount: d.ctrlPoints?.length ?? 0,
  }))
})

const linkDirColumns = [
  { title: '方向', key: 'dir', width: 86 },
  { title: '限速', key: 'speed', width: 56, render: (row) => (row.speed ? row.speed : '-') },
  { title: 'Rever', key: 'revert', width: 56 },
  { title: '空车禁行', key: 'emptyCantRun', width: 76 },
  { title: 'PodDir', key: 'podDir', width: 64 },
  { title: 'StartDir', key: 'startDir', width: 76 },
  { title: 'StopDir', key: 'stopDir', width: 76 },
  { title: 'LaserType', key: 'laserType', width: 78 },
  { title: 'robottype', key: 'robotType', width: 86 },
  { title: 'carryType', key: 'carryType', width: 86 },
  { title: 'ctnrtype', key: 'ctnrtype', width: 82 },
  { title: '控制点', key: 'ctrlCount', width: 62 },
]

function gotoNeighbor(row) {
  const t = topo.value
  const node = activeNode.value
  if (!t || !node) return
  const other = t.nodeById.get(row.targetId)
  if (!other) return
  selectedNodes.add(other.id)
  selectedLinks.add(linkKeyOf(node.id, other.id))
  primary.value = { type: 'link', key: linkKeyOf(node.id, other.id) }
  centerOn((node.x + other.x) / 2, (node.y + other.y) / 2, Math.max(view.scale, 25))
}

function neighborRowProps(row) {
  return { style: 'cursor: pointer', onClick: () => gotoNeighbor(row) }
}

/** 当前对象的属性文本（复制用） */
const propsText = computed(() => {
  const p = propsTarget.value
  if (!p) return ''
  const title = p.type === 'node' ? `[节点 ${p.node.id}]` : `[线段 ${p.link.a} → ${p.link.b}]`
  return `${title}\n${propsRows.value.map((r) => `${r.label}: ${r.value}`).join('\n')}`
})

function locateProps() {
  const p = propsTarget.value
  if (!p) return
  if (p.type === 'node') locateNodeRow({ id: p.node.id })
  else locateLinkRow({ key: p.link.key })
}

/** 全屏时给页面填上画布同色背景，避免黑边/白边 */
const pageStyle = computed(() => (isFullscreen.value ? { background: palette.value.bg } : {}))

const inverseCode = ref('')
const inverseResult = computed(() => {
  if (!inverseCode.value.trim()) return null
  const parsed = parseGroundCode(inverseCode.value, mapCode.value.trim())
  if (!parsed.ok) return { ok: false }
  const t = topo.value
  let nearest = null
  if (t) {
    let best = Infinity
    for (const node of t.nodes) {
      const d = Math.hypot(node.x - parsed.x, node.y - parsed.y)
      if (d < best) {
        best = d
        nearest = { node, dist: d }
      }
    }
  }
  return { ok: true, ...parsed, nearest }
})

const nodeColumns = [
  { title: '#', key: 'idx', width: 42 },
  { title: 'ID', key: 'id', width: 62 },
  { title: 'X(m)', key: 'x', width: 86, render: (row) => formatMeters(row.x) },
  { title: 'Y(m)', key: 'y', width: 86, render: (row) => formatMeters(row.y) },
  { title: '地码', key: 'code', minWidth: 150, render: (row) => h('span', { class: 'mono' }, row.code) },
  {
    title: '属性',
    key: 'attr',
    width: 96,
    render: (row) =>
      h(NSpace, { size: 4 }, {
        default: () => [
          h(NTag, { size: 'small', bordered: false }, { default: () => `v${row.value}` }),
          row.roadProperty === 1 ? h(NTag, { size: 'small', type: 'warning', bordered: false }, { default: () => 'RP1' }) : null,
        ].filter(Boolean),
      }),
  },
]

const linkColumns = [
  { title: '#', key: 'idx', width: 42 },
  { title: '起点', key: 'a', width: 62 },
  { title: '终点', key: 'b', width: 62 },
  { title: '长度(m)', key: 'distance', width: 88, render: (row) => formatMeters(row.distance) },
  {
    title: '方向',
    key: 'directed',
    width: 78,
    render: (row) =>
      h(NTag, { size: 'small', type: row.directed ? 'success' : 'default', bordered: false }, {
        default: () => (row.directed ? '双向' : '单向'),
      }),
  },
  { title: '限速', key: 'speed', width: 62, render: (row) => (row.speed ? row.speed : '-') },
]

function locateNodeRow(row) {
  const t = topo.value
  const node = t?.nodeById.get(row.id)
  if (!node) return
  selectedNodes.clear()
  selectedLinks.clear()
  selectedNodes.add(node.id)
  primary.value = { type: 'node', key: node.id }
  centerOn(node.x, node.y, Math.max(view.scale, 25))
}

function locateLinkRow(row) {
  const t = topo.value
  const link = t?.linkByKey.get(row.key)
  if (!link) return
  selectedNodes.clear()
  selectedLinks.clear()
  selectedLinks.add(link.key)
  primary.value = { type: 'link', key: link.key }
  centerOn((link.ax + link.bx) / 2, (link.ay + link.by) / 2, Math.max(view.scale, 20))
}

function nodeRowProps(row) {
  return { style: 'cursor: pointer', onClick: () => locateNodeRow(row) }
}

function linkRowProps(row) {
  return { style: 'cursor: pointer', onClick: () => locateLinkRow(row) }
}

/* ─────────────────────────── 数据加载 ─────────────────────────── */

function applyXml(text, label) {
  const parsed = parseTopologyXml(text)
  topo.value = parsed
  fileLabel.value = label
  clearSelection()
  if (parsed.meta.qrCode) mapCode.value = parsed.meta.qrCode
  nextTick(() => {
    syncSize()
    fitView()
  })
}

async function loadServerFile(name) {
  if (!name) return
  loading.value = true
  try {
    const resp = await fetch(`/api/map_topology/raw/${encodeURIComponent(name)}`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const text = await resp.text()
    applyXml(text, name)
    currentFile.value = name
    message.success(`已加载 ${name}：${topo.value.stats.nodeCount} 点 / ${topo.value.stats.linkCount} 线`)
  } catch (error) {
    message.error(`加载 ${name} 失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

async function refreshServerFiles() {
  try {
    const resp = await fetch('/api/map_topology/list')
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json()
    serverFiles.value = data.files ?? []
    serverOk.value = true
    return serverFiles.value
  } catch {
    serverOk.value = false
    return []
  }
}

async function loadConfiguredMapCode() {
  try {
    const resp = await fetch('/api/rcms/get_config?key=rcms.map_code')
    const data = await resp.json()
    const code = data?.data?.['rcms.map_code']
    if (code && !mapCode.value) mapCode.value = String(code)
  } catch {
    /* 后端不可用时忽略 */
  }
}

function openLocalFile() {
  fileInputRef.value?.click()
}

function onLocalFileChange(event) {
  const file = event.target.files?.[0]
  if (file) readLocalFile(file)
  event.target.value = ''
}

function readLocalFile(file) {
  const reader = new FileReader()
  reader.onload = () => {
    try {
      applyXml(String(reader.result), file.name)
      currentFile.value = null
      message.success(`已解析本地文件 ${file.name}`)
    } catch (error) {
      message.error(`解析失败：${error.message}`)
    }
  }
  reader.readAsText(file, 'utf-8')
}

function onDrop(event) {
  const file = event.dataTransfer?.files?.[0]
  if (file) readLocalFile(file)
}

/* ─────────────────────────── 导出 ─────────────────────────── */

async function copyText(text, tip = '已复制到剪贴板') {
  if (!text) {
    message.warning('没有可复制的内容')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    message.success(tip)
  } catch {
    const area = document.createElement('textarea')
    area.value = text
    document.body.appendChild(area)
    area.select()
    document.execCommand('copy')
    area.remove()
    message.success(tip)
  }
}

function downloadText(filename, text, mime = 'text/plain;charset=utf-8') {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1500)
}

/** 导出打印地码 CSV（唯一导出格式：表头「打印码值,备注」），带 BOM 便于 Excel 直接打开中文 */
function exportCodesCsv() {
  if (!codeEntries.value.length) {
    message.warning('没有可导出的地码，请先框选或点选要打印的点')
    return
  }
  downloadText(`${baseName()}_codes.csv`, `\ufeff${csvText.value}`, 'text/csv;charset=utf-8')
  message.success(`已导出 ${codeEntries.value.length} 条地码（表头：打印码值,备注）`)
}

function baseName() {
  const raw = fileLabel.value || 'topology'
  return raw.replace(/\.xml$/i, '')
}

/* ─────────────────────────── 生命周期 ─────────────────────────── */

let observer = null

function syncSize() {
  const el = wrapRef.value
  const canvas = canvasRef.value
  if (!el || !canvas) return
  const rect = el.getBoundingClientRect()
  const dpr = window.devicePixelRatio || 1
  const w = Math.max(360, Math.round(rect.width))
  const h = Math.max(320, Math.round(rect.height))
  const changed = w !== size.w || h !== size.h || dpr !== size.dpr
  size.w = w
  size.h = h
  size.dpr = dpr
  canvas.width = Math.round(w * dpr)
  canvas.height = Math.round(h * dpr)
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`
  if (changed) scheduleDraw()
}

onMounted(async () => {
  syncSize()
  observer = new ResizeObserver(() => syncSize())
  if (wrapRef.value) observer.observe(wrapRef.value)
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('pointerdown', onGlobalPointerDown, true)
  document.addEventListener('fullscreenchange', onFullscreenChange)

  await loadConfiguredMapCode()
  const files = await refreshServerFiles()
  const preferred = files.find((f) => f.name === '111.xml') ?? files[0]
  if (preferred) await loadServerFile(preferred.name)
  if (!files.length) {
    message.warning('未在后端找到拓扑地图 XML，可点击「打开本地 XML」或直接拖入文件')
  }
})

onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
  observer?.disconnect()
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('pointerdown', onGlobalPointerDown, true)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
})

watch(opt, () => scheduleDraw())
watch([mapCode, padDigits], () => scheduleDraw())
</script>

<template>
  <div ref="pageRef" class="topo-page" :class="{ 'is-fullscreen': isFullscreen, 'no-side': !showSide }" :style="pageStyle">
    <NCard :bordered="false" size="small">
      <template #header>
        <div class="header-row">
          <span class="title">AGV 拓扑地图 / 地码工具</span>
          <NTag v-if="meta" size="small" :bordered="false" type="info">
            {{ meta.name || '未命名' }} · 代码 {{ meta.qrCode || '-' }} · 类型 {{ meta.mapType || '-' }}
          </NTag>
          <NTag v-if="topo" size="small" :bordered="false">
            {{ stats.nodeCount }} 点 / {{ stats.linkCount }} 线 / {{ stats.directedCount }} 有向段
          </NTag>
          <NTag v-if="topo && stats.curvedCount" size="small" :bordered="false" type="warning">
            曲线段 {{ stats.curvedCount }}
          </NTag>
          <NTag v-if="isFullscreen" size="small" :bordered="false" type="success">网页全屏</NTag>
        </div>
      </template>
      <template #header-extra>
        <NSpace>
          <NButton size="small" @click="refreshServerFiles">刷新文件</NButton>
          <NButton size="small" type="primary" :loading="loading" @click="loadServerFile(currentFile)">重新加载</NButton>
        </NSpace>
      </template>

      <NAlert v-if="!serverOk" type="warning" :bordered="false" style="margin-bottom: 10px">
        后端地图接口不可用（/api/map_topology/list）。仍可点击「打开本地 XML」或把拓扑地图 XML 拖到画布上。
      </NAlert>

      <div class="toolbar">
        <div class="tool-group">
          <span class="tool-label">地图文件</span>
          <NSelect
            v-model:value="currentFile"
            size="small"
            style="width: 240px"
            placeholder="选择服务器地图 XML"
            :options="serverFiles.map((f) => ({ label: `${f.name} (${Math.round(f.size / 1024)} KB · ${f.mtime})`, value: f.name }))"
            @update:value="loadServerFile"
          />
          <NButton size="small" @click="openLocalFile">打开本地 XML</NButton>
          <input ref="fileInputRef" type="file" accept=".xml,text/xml" style="display: none" @change="onLocalFileChange" />
        </div>

        <div class="tool-group">
          <span class="tool-label">地码</span>
          <NInput v-model:value="mapCode" size="small" style="width: 72px" placeholder="BB" />
          <span class="tool-label">位数</span>
          <NInputNumber v-model:value="padDigits" size="small" style="width: 82px" :min="1" :max="12" />
        </div>

        <div class="tool-group">
          <span class="tool-label">选择模式</span>
          <NRadioGroup v-model:value="opt.pickMode" size="small">
            <NRadioButton value="node">分点选择模式</NRadioButton>
            <NRadioButton value="link">线选择模式</NRadioButton>
            <NRadioButton value="both">点线同选</NRadioButton>
          </NRadioGroup>
        </div>

        <div class="tool-group">
          <span class="tool-label">操作</span>
          <NRadioGroup v-model:value="opt.panMode" size="small">
            <NRadioButton :value="false">框选</NRadioButton>
            <NRadioButton :value="true">平移</NRadioButton>
          </NRadioGroup>
        </div>

        <div class="tool-group">
          <span class="tool-label">视图</span>
          <NButton size="small" @click="zoomBy(1.35)">放大 ＋</NButton>
          <NButton size="small" @click="zoomBy(1 / 1.35)">缩小 －</NButton>
          <NButton size="small" @click="fitView">适应视图</NButton>
          <NButton size="small" @click="zoomToSelection">缩放到选择</NButton>
          <NButton size="small" @click="toggleLabels">
            标签{{ opt.nodeLabel === 'none' && opt.linkLabel === 'none' ? '开' : '关' }}
          </NButton>
          <NButton size="small" :type="isFullscreen ? 'warning' : 'default'" @click="toggleFullscreen">
            {{ isFullscreen ? '退出全屏' : '网页全屏' }}
          </NButton>
          <NButton size="small" @click="showSide = !showSide">{{ showSide ? '收起侧栏' : '展开侧栏' }}</NButton>
        </div>

        <div class="tool-group">
          <span class="tool-label">选择</span>
          <NButton size="small" @click="clearSelection">清空</NButton>
          <NButton size="small" :disabled="selectedLinks.size === 0" @click="selectOnlyNodes">仅保留点</NButton>
          <NButton size="small" :disabled="selectedNodes.size === 0" @click="expandNeighbors">加邻接点</NButton>
        </div>
      </div>

      <div class="body">
        <div class="canvas-area">
          <div ref="wrapRef" class="canvas-wrap" @dragover.prevent @drop.prevent="onDrop">
            <canvas
              ref="canvasRef"
              class="topo-canvas"
              :class="{ 'pan-mode': opt.panMode }"
              @pointerdown="onPointerDown"
              @pointermove="onPointerMove"
              @pointerup="onPointerUp"
              @pointercancel="onPointerUp"
              @pointerleave="onPointerLeave"
              @dblclick="onCanvasDblClick"
              @wheel="onWheel"
              @contextmenu.prevent
            />
            <div class="canvas-hud" @pointerdown.stop @dblclick.stop>
              <div class="hud-actions">
                <NButton size="tiny" @click="zoomBy(1.35)">＋</NButton>
                <NButton size="tiny" @click="zoomBy(1 / 1.35)">－</NButton>
                <NButton size="tiny" @click="fitView">适应</NButton>
                <NButton size="tiny" :type="isFullscreen ? 'warning' : 'default'" @click="toggleFullscreen">
                  {{ isFullscreen ? '退出全屏' : '全屏' }}
                </NButton>
              </div>
            </div>
            <div
              v-if="ctxMenu"
              class="ctx-menu"
              :style="{ left: `${ctxMenu.x}px`, top: `${ctxMenu.y}px` }"
              @pointerdown.stop
              @dblclick.stop
              @contextmenu.prevent
            >
              <button
                v-for="item in ctxMenu.items"
                :key="item.key"
                type="button"
                class="ctx-item"
                :class="{ disabled: item.disabled }"
                @click="runCtxItem(item)"
              >
                {{ item.label }}
              </button>
            </div>
            <NSpin v-if="loading" :show="true" class="canvas-spin" />
          </div>
          <div class="statusbar">
            <span>
              鼠标：
              <template v-if="cursorWorld">
                X = <b>{{ formatMeters(cursorWorld.x) }}</b> m，Y = <b>{{ formatMeters(cursorWorld.y) }}</b> m ·
                地码 <b class="mono">{{ makeGroundCode(cursorWorld.x, cursorWorld.y, mapCode.trim(), { pad: padDigits }) }}</b>
              </template>
              <template v-else>移入画布查看坐标</template>
            </span>
            <span>
              缩放 {{ view.scale.toFixed(2) }} px/m · 已选 点 {{ selectedNodes.size }} / 线 {{ selectedLinks.size }}
              · 模式 {{ pickModeLabel }}
              · 标签 {{ labelModeLabel }}<template v-if="!labelShown">（缩小时已隐藏，L 键切换）</template>
              <template v-if="filterActive">
                · 筛选 <b>{{ filterSummary }}</b>
              </template>
            </span>
            <span class="hint">
              左键框选（框内实时计数）· 中键/右键/Alt+左键拖动平移 · 滚轮缩放 · 右键单击打开菜单 ·
              双击点/线查看属性 · Ctrl/Shift+单击加选 ·
              1 分点 / 2 线 / 3 点线模式 · E 加邻接点 · L 标签 · F 适应 · F11 全屏 ·
              方向键平移 · ＋/－ 缩放 · Home 适应 · Esc 清空选择
            </span>
          </div>
        </div>

        <div v-if="showSide" class="side">
          <NTabs v-model:value="activeTab" type="line" size="small" animated>
            <NTabPane name="points" :tab="`已选点 ${selectedNodes.size}`">
              <NDataTable
                size="small"
                :columns="nodeColumns"
                :data="selectedNodeRows"
                :max-height="230"
                :row-props="nodeRowProps"
                :bordered="false"
                :scroll-x="520"
              />
              <NSpace align="center" size="small" style="margin-top: 8px">
                <NButton size="small" :disabled="!activeNode" @click="focusProps">查看完整属性</NButton>
                <NText depth="3" style="font-size: 12px">详细属性统一在「属性」页签显示</NText>
              </NSpace>
              <NDivider style="margin: 10px 0" />
              <div class="kv">
                <span>节点数</span><b>{{ stats.nodeCount }}</b>
                <span>线段数</span><b>{{ stats.linkCount }}</b>
                <span>有向段</span><b>{{ stats.directedCount }}</b>
                <span>孤立点</span><b>{{ stats.isolatedCount }}</b>
              </div>
            </NTabPane>

            <NTabPane name="links" :tab="`已选线 ${selectedLinks.size}`">
              <NDataTable
                size="small"
                :columns="linkColumns"
                :data="selectedLinkRows"
                :max-height="260"
                :row-props="linkRowProps"
                :bordered="false"
                :scroll-x="420"
              />
              <NSpace align="center" size="small" style="margin-top: 8px">
                <NButton size="small" :disabled="!activeLink" @click="focusProps">查看完整属性</NButton>
                <NText depth="3" style="font-size: 12px">详细属性统一在「属性」页签显示</NText>
              </NSpace>
            </NTabPane>

            <NTabPane name="props" :tab="`属性${propsTypeLabel ? ` · ${propsTypeLabel}` : ''}`">
              <NSpace vertical size="small">
                <NSpace align="center" size="small">
                  <NTag v-if="propsTarget" size="small" :bordered="false" type="info">{{ propsTypeLabel }}</NTag>
                  <NText v-else depth="3" style="font-size: 12px">点击画布上的点 / 线（或双击）查看完整属性</NText>
                  <NButton size="small" :disabled="!propsText" @click="copyText(propsText, '属性已复制')">复制属性</NButton>
                  <NButton size="small" :disabled="!propsTarget" @click="locateProps">定位</NButton>
                </NSpace>
                <template v-if="propsTarget">
                  <NDescriptions :column="1" size="small" bordered label-placement="left" :label-style="{ width: '112px' }">
                    <NDescriptionsItem v-for="row in propsRows" :key="row.label" :label="row.label">
                      <span class="mono">{{ row.value }}</span>
                    </NDescriptionsItem>
                  </NDescriptions>
                  <template v-if="activeNode">
                    <NText strong style="font-size: 12px">关联线段（点击跳转到邻接点）</NText>
                    <NDataTable
                      size="small"
                      :columns="neighborColumns"
                      :data="neighborRows"
                      :max-height="200"
                      :row-props="neighborRowProps"
                      :bordered="false"
                      :scroll-x="420"
                    />
                  </template>
                  <template v-if="activeLink">
                    <NText strong style="font-size: 12px">有向段明细</NText>
                    <NDataTable
                      size="small"
                      :columns="linkDirColumns"
                      :data="linkDirRows"
                      :max-height="220"
                      :bordered="false"
                      :scroll-x="780"
                    />
                  </template>
                </template>
                <NText depth="3" style="font-size: 12px">
                  提示：右键点/线可复制地码、切换属性标注；双击点/线自动切到本页签。
                </NText>
              </NSpace>
            </NTabPane>

            <NTabPane name="display" :tab="`显示 / 筛选${filterActive ? ` · ${filterSummary}` : ''}`">
              <NSpace vertical size="small">
                <!-- ── 显示 ── -->
                <NText strong style="font-size: 12px">显示</NText>
                <NSpace align="center" size="small">
                  <NSwitch v-model:value="opt.showNodes" size="small" /> 节点
                  <NSwitch v-model:value="opt.showLinks" size="small" /> 线段
                  <NSwitch v-model:value="opt.showArrows" size="small" /> 箭头
                  <NSwitch v-model:value="opt.markRoadProperty" size="small" /> RP=1 方块
                  <NSwitch v-model:value="opt.highlightRelated" size="small" /> 高亮关联线
                </NSpace>
                <NSpace align="center" size="small">
                  <span class="tool-label">点半径</span>
                  <NSlider v-model:value="opt.nodeRadius" :min="2" :max="10" :step="0.5" style="width: 150px" />
                  <span class="mono">{{ opt.nodeRadius }} px</span>
                </NSpace>

                <NDivider style="margin: 4px 0" />

                <!-- ── 标签（批量属性标注） ── -->
                <NText strong style="font-size: 12px">标签（点 / 线属性标注）</NText>
                <NSpace align="center" size="small">
                  <span class="tool-label">点标签</span>
                  <NSelect v-model:value="opt.nodeLabel" size="small" style="width: 158px" :options="nodeLabelOptions" />
                </NSpace>
                <NSpace align="center" size="small">
                  <span class="tool-label">线标签</span>
                  <NSelect v-model:value="opt.linkLabel" size="small" style="width: 158px" :options="linkLabelOptions" />
                  <NSwitch v-model:value="opt.onlyAbnormal" size="small" /> 只标注异常（空/0，红字）
                </NSpace>
                <NSpace align="center" size="small">
                  <NSwitch v-model:value="opt.onlySelected" size="small" /> 只标注选中项
                  <NSwitch v-model:value="opt.onlyMatched" size="small" /> 有筛选时只标注命中项
                </NSpace>
                <NSpace align="center" size="small">
                  <NSwitch v-model:value="opt.labelZoomGate" size="small" /> 缩小隐藏
                  <NSlider
                    v-model:value="opt.labelMinZoom"
                    :min="1"
                    :max="300"
                    :step="1"
                    :disabled="!opt.labelZoomGate"
                    style="width: 130px"
                  />
                  <span class="mono">≥ {{ opt.labelMinZoom }} px/m</span>
                  <NButton size="tiny" @click="opt.labelMinZoom = Math.max(1, Math.round(view.scale))">取当前</NButton>
                </NSpace>
                <NText depth="3" style="font-size: 12px">
                  当前 {{ view.scale.toFixed(2) }} px/m → 标签{{ labelShown ? '显示中' : '已隐藏' }}；重叠标签自动跳过不叠字。
                </NText>

                <NDivider style="margin: 4px 0" />

                <!-- ── 点筛选 ── -->
                <NSpace align="center" size="small">
                  <NText strong style="font-size: 12px">点筛选</NText>
                  <NSelect v-model:value="nodeFilter.key" size="small" style="width: 158px" :options="nodeFilterOptions" />
                  <NSelect v-model:value="nodeFilter.op" size="small" style="width: 66px" :options="OP_OPTIONS" />
                </NSpace>
                <NSpace align="center" size="small">
                  <NSelect
                    v-if="isEqualityOp(nodeFilter.op)"
                    v-model:value="nodeFilterValues"
                    size="small"
                    style="width: 236px"
                    multiple
                    filterable
                    tag
                    clearable
                    :max-tag-count="2"
                    :options="nodeValueStats.options"
                    placeholder="勾选图上出现过的值，或直接输入"
                  />
                  <NInput v-else v-model:value="nodeFilter.value" size="small" style="width: 120px" placeholder="数值" />
                  <NTag size="small" :bordered="false" type="success">命中 {{ filterCounts.nodes }}</NTag>
                  <NButton size="small" :disabled="!nodeMatches" @click="labelNodeFilterProp">
                    {{ opt.nodeLabel === nodeFilter.key ? '取消标注' : '标注' }}
                  </NButton>
                </NSpace>
                <NText depth="3" style="font-size: 12px">
                  图上共 {{ nodeValueStats.distinct }} 个不同值<template v-if="nodeValueStats.min !== null">
                    ，数值范围 {{ nodeValueStats.min }} ~ {{ nodeValueStats.max }}</template>
                </NText>

                <!-- ── 线筛选 ── -->
                <NSpace align="center" size="small">
                  <NText strong style="font-size: 12px">线筛选</NText>
                  <NSelect v-model:value="linkFilter.key" size="small" style="width: 158px" :options="linkFilterOptions" />
                  <NSelect v-model:value="linkFilter.op" size="small" style="width: 66px" :options="OP_OPTIONS" />
                </NSpace>
                <NSpace align="center" size="small">
                  <NSelect
                    v-if="isEqualityOp(linkFilter.op)"
                    v-model:value="linkFilterValues"
                    size="small"
                    style="width: 236px"
                    multiple
                    filterable
                    tag
                    clearable
                    :max-tag-count="2"
                    :options="linkValueStats.options"
                    placeholder="勾选图上出现过的值，或直接输入"
                  />
                  <NInput v-else v-model:value="linkFilter.value" size="small" style="width: 120px" placeholder="数值" />
                  <NTag size="small" :bordered="false" type="success">命中 {{ filterCounts.links }}</NTag>
                  <NButton size="small" :disabled="!linkMatches" @click="labelLinkFilterProp">
                    {{ opt.linkLabel === linkFilter.key ? '取消标注' : '标注' }}
                  </NButton>
                </NSpace>
                <NText depth="3" style="font-size: 12px">
                  图上共 {{ linkValueStats.distinct }} 个不同值<template v-if="linkValueStats.min !== null">
                    ，数值范围 {{ linkValueStats.min }} ~ {{ linkValueStats.max }}</template>
                </NText>

                <NSpace align="center" size="small">
                  <NButton size="small" type="primary" :disabled="!filterActive" @click="selectMatches">选中命中项</NButton>
                  <NButton size="small" :disabled="!filterActive" @click="zoomToMatches">缩放到命中</NButton>
                  <NButton size="small" :disabled="!filterActive" @click="clearFilters">清除筛选</NButton>
                </NSpace>
                <NSpace align="center" size="small">
                  <NSwitch v-model:value="opt.dimUnmatched" size="small" /> 未命中淡化
                  <NSwitch v-model:value="opt.hideUnmatched" size="small" /> 未命中隐藏（只看命中）
                </NSpace>
                <NSpace align="center" size="small">
                  <span class="tool-label">示例</span>
                  <NButton size="small" @click="applyPreset('noSpeed')">没设限速的线段</NButton>
                  <NButton size="small" @click="applyPreset('noRoad')">没配 RoadProperty 的点</NButton>
                  <NButton size="small" @click="applyPreset('noRobotType')">没配 robottype 的线段</NButton>
                  <NButton size="small" @click="applyPreset('reset')">恢复默认</NButton>
                </NSpace>
                <NText depth="3" style="font-size: 12px">
                  <b>=</b> / <b>≠</b> 支持多值（下拉里已列出图上所有出现过的值，勾选即可；也可自己输入，用逗号分隔）；
                  <b>&gt;</b> <b>&gt;=</b> <b>&lt;</b> <b>&lt;=</b> 按数值比较（只取第一个值）。命中的点 / 线在地图上绿色高亮。
                </NText>

                <NDivider style="margin: 4px 0" />

                <!-- ── 框选判定 ── -->
                <NText strong style="font-size: 12px">框选判定</NText>
                <NSpace align="center" size="small">
                  <span class="tool-label">点</span>
                  <NRadioGroup v-model:value="opt.nodeRule" size="small">
                    <NRadioButton value="inside">完全在框内</NRadioButton>
                    <NRadioButton value="touch">碰到即选</NRadioButton>
                  </NRadioGroup>
                </NSpace>
                <NSpace align="center" size="small">
                  <span class="tool-label">线</span>
                  <NRadioGroup v-model:value="opt.linkRule" size="small">
                    <NRadioButton value="both">端点在内或相交</NRadioButton>
                    <NRadioButton value="cross">与框相交</NRadioButton>
                    <NRadioButton value="endpoints">两端点在内</NRadioButton>
                  </NRadioGroup>
                </NSpace>
                <NText depth="3" style="font-size: 12px">
                  选择模式：分点 / 线 / 点线同选（快捷键 1 / 2 / 3），切换模式不会清空已选内容。
                  操作：左键框选（实时计数）· 右键单击菜单 · 双击看属性 · 方向键平移 · ＋/－ 缩放 · F 适应 · L 标签 · F11 全屏。
                </NText>
                <NText depth="3" style="font-size: 12px">
                  单位：&lt;xpos&gt;/&lt;ypos&gt;/&lt;distance&gt; 均为米（显示 3 位小数）；地码 = x 毫米 + 地图代码 + y 毫米（各
                  {{ padDigits }} 位补零），例 X 111.222 / Y 222.333 →
                  <span class="mono">{{ makeGroundCode(111.222, 222.333, mapCode.trim() || 'BB', { pad: padDigits }) }}</span>
                </NText>
              </NSpace>
            </NTabPane>
            <NTabPane name="codes" :tab="`地码 CSV ${codeEntries.length}`">
              <NSpace vertical size="small">
                <NSpace align="center" size="small">
                  <span class="tool-label">排序</span>
                  <NSelect
                    v-model:value="sortMode"
                    size="small"
                    style="width: 150px"
                    :options="[
                      { label: '按 X → Y', value: 'xy' },
                      { label: '按 Y → X', value: 'yx' },
                      { label: '按节点 ID', value: 'id' },
                    ]"
                  />
                  <NCheckbox v-model:checked="dedupeCodes" size="small">去重</NCheckbox>
                </NSpace>
                <NSpace align="center" size="small">
                  <span class="tool-label">节点备注模板</span>
                  <NInput
                    v-model:value="nodeRemarkTpl"
                    size="small"
                    style="width: 170px"
                    placeholder="如 节点{id}，留空则备注为空"
                  />
                  <NSpace align="center" size="small">
                    <NButton size="small" type="primary" @click="copyText(csvText, 'CSV 内容已复制')">复制 CSV</NButton>
                    <NButton size="small" type="success" @click="exportCodesCsv">导出 CSV</NButton>
                  </NSpace>
                </NSpace>
                <NText depth="3" style="font-size: 12px">
                  导出格式固定为 CSV，表头 <b class="mono">打印码值,备注</b>，共 2 列（已选点）；模板可用
                  <span class="mono">{id}</span> <span class="mono">{x}</span> <span class="mono">{y}</span>
                  <span class="mono">{code}</span>。
                </NText>
                <NInput :value="csvText" type="textarea" readonly :autosize="{ minRows: 8, maxRows: 16 }" placeholder="框选点位后在此预览 CSV" />
                <NDivider style="margin: 4px 0" />
                <NSpace align="center" size="small">
                  <span class="tool-label">地码反查</span>
                  <NInput v-model:value="inverseCode" size="small" style="width: 190px" placeholder="如 111222BB222333" />
                </NSpace>
                <NText v-if="inverseResult" :depth="inverseResult.ok ? 2 : 3" style="font-size: 12px">
                  <template v-if="inverseResult.ok">
                    → X {{ formatMeters(inverseResult.x) }} m，Y {{ formatMeters(inverseResult.y) }} m，代码 {{ inverseResult.mapCode || '-' }}
                    <template v-if="inverseResult.nearest">
                      ；最近节点 {{ inverseResult.nearest.node.id }}（{{ formatMeters(inverseResult.nearest.dist) }} m）
                      <NButton size="tiny" text type="primary" @click="locateNodeRow({ id: inverseResult.nearest.node.id })">定位</NButton>
                    </template>
                  </template>
                  <template v-else>格式无法识别</template>
                </NText>
              </NSpace>
            </NTabPane>

          </NTabs>
        </div>
      </div>
    </NCard>
  </div>
</template>

<style scoped>
.topo-page {
  padding: 8px 12px 24px;
}

/* 网页全屏：铺满屏幕，画布尽可能大 */
.topo-page.is-fullscreen {
  padding: 6px 10px;
  overflow: hidden;
}

.topo-page.is-fullscreen .canvas-wrap {
  height: calc(100vh - 276px);
  min-height: 320px;
}

.topo-page.is-fullscreen.no-side .canvas-wrap {
  height: calc(100vh - 176px);
}

.topo-page.is-fullscreen .side {
  flex: 0 0 430px;
  width: 430px;
  max-width: 40vw;
  max-height: calc(100vh - 190px);
  overflow: auto;
}

/* 画布内导航 HUD */
.canvas-hud {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 15;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  pointer-events: none;
}

.hud-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px;
  padding: 4px;
  border-radius: 8px;
  pointer-events: auto;
  background: rgba(127, 127, 127, 0.16);
  backdrop-filter: blur(3px);
}

/* 右键菜单 */
.ctx-menu {
  position: absolute;
  z-index: 30;
  min-width: 224px;
  padding: 4px;
  border-radius: 8px;
  background: var(--n-color, #fff);
  border: 1px solid rgba(127, 127, 127, 0.35);
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.22);
}

.ctx-item {
  display: block;
  width: 100%;
  padding: 6px 10px;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: inherit;
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
}

.ctx-item:hover {
  background: rgba(56, 189, 248, 0.16);
}

.ctx-item.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.ctx-item.disabled:hover {
  background: transparent;
}

.header-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.title {
  font-size: 16px;
  font-weight: 600;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  padding: 4px 0 10px;
}

.tool-group {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 6px;
  background: rgba(125, 125, 125, 0.08);
}

.tool-label {
  font-size: 12px;
  color: var(--n-text-color-3, #666);
  white-space: nowrap;
}

.body {
  display: flex;
  gap: 12px;
  align-items: stretch;
}

.canvas-area {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.canvas-wrap {
  position: relative;
  width: 100%;
  height: calc(100vh - 330px);
  min-height: 420px;
  border: 1px solid rgba(125, 125, 125, 0.3);
  border-radius: 8px;
  overflow: hidden;
  touch-action: none;
  user-select: none;
}

.topo-canvas {
  display: block;
  cursor: crosshair;
}

.topo-canvas.pan-mode {
  cursor: grab;
}

.canvas-spin {
  position: absolute;
  top: 12px;
  left: 12px;
}

.statusbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 6px 4px;
  font-size: 12px;
  color: var(--n-text-color-3, #666);
}

.statusbar .hint {
  opacity: 0.8;
}

.side {
  flex: 0 0 400px;
  width: 400px;
  max-width: 42vw;
  border-left: 1px solid rgba(125, 125, 125, 0.2);
  padding-left: 12px;
}

.kv {
  display: grid;
  grid-template-columns: auto 1fr auto 1fr;
  gap: 4px 10px;
  font-size: 12px;
}

.kv span {
  color: var(--n-text-color-3, #666);
}

:deep(.mono) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

@media (max-width: 1100px) {
  .body {
    flex-direction: column;
  }

  .side {
    flex: 1 1 auto;
    width: 100%;
    max-width: none;
    border-left: none;
    padding-left: 0;
  }

  .canvas-wrap {
    height: 60vh;
  }
}
</style>
