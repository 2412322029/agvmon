/**
 * AGV 拓扑地图（MapCfg XML）解析与地码工具
 *
 * XML 结构（RCMS 导出）：
 *   <MapCfg>
 *     <MapName>L20</MapName> <MapQRCode>BB</MapQRCode> <MapType>2</MapType>
 *     <Row>999</Row> <Col>999</Col> <Width>1000</Width> <Height>1000</Height>
 *     <PointInfo>                      ← 节点（一个路径点 = 一个地码点）
 *       <id>0</id> <xpos>212.44</xpos> <ypos>406.388</ypos> ... 属性
 *       <NeighbInfo>                   ← 邻接段容器（内部可含多段，每段以 <id> 开头）
 *         <id>1</id> <distance>1.829</distance> <Speed>800</Speed> ...
 *         <CtrlPoint><Pos xpos=".." ypos=".."/>...</CtrlPoint>   ← 可选，曲线控制点
 *         <id>12</id> <distance>..</distance> ...                 ← 下一段
 *       </NeighbInfo>
 *     </PointInfo>
 *   </MapCfg>
 *
 * 坐标与地码约定：
 *   - <xpos>/<ypos> 单位为米（m）：212.44 → 212.44 m，显示时固定 3 位小数（212.440）
 *   - 邻接段 <distance> 同样为米，且等于两节点欧氏距离
 *   - 地码（地面二维码）= {x_mm}{地图代码}{y_mm}，单位 mm，各 6 位补零
 *       111222BB222333 → x = 111222 mm = 111.222 m，地图代码 BB，y = 222333 mm = 222.333 m
 */

/** 1 米 = 1000 毫米 */
export const MM_PER_M = 1000

const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" }

function decodeEntities(text) {
  if (!text || text.indexOf('&') === -1) return text
  return text.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (raw, body) => {
    if (body[0] === '#') {
      const code =
        body[1] === 'x' || body[1] === 'X'
          ? Number.parseInt(body.slice(2), 16)
          : Number.parseInt(body.slice(1), 10)
      return Number.isFinite(code) ? String.fromCodePoint(code) : raw
    }
    return ENTITIES[body] ?? raw
  })
}

function toNumber(value, fallback = 0) {
  const n = Number.parseFloat(value)
  return Number.isFinite(n) ? n : fallback
}

function parseAttrs(text) {
  const attrs = {}
  if (!text) return attrs
  const re = /([\w.:-]+)\s*=\s*"([^"]*)"|([\w.:-]+)\s*=\s*'([^']*)'/g
  let m
  while ((m = re.exec(text))) {
    attrs[m[1] || m[3]] = decodeEntities(m[2] ?? m[4] ?? '')
  }
  return attrs
}

/** 读取一段「只有标量子节点」的片段，<A>v</A> 与 <A/> 都支持 */
function readScalars(fragment) {
  const out = {}
  if (!fragment) return out
  const selfClosing = /<([A-Za-z_][\w.:-]*)\s*\/>/g
  let m
  while ((m = selfClosing.exec(fragment))) {
    if (!(m[1] in out)) out[m[1]] = ''
  }
  const paired = /<([A-Za-z_][\w.:-]*)>([^<]*)<\/\1>/g
  while ((m = paired.exec(fragment))) {
    out[m[1]] = decodeEntities(m[2].trim())
  }
  return out
}

/**
 * 米 → 整数毫米。
 * 先按 3 位小数规整再换算，保证与 formatMeters 的显示值完全一致
 * （避免 211.5255 * 1000 = 211525.50000000003 这类浮点放大误差导致「显示 211.525 但地码是 211526」）。
 */
export function toMillimeters(value) {
  const rounded = Number(toNumber(value).toFixed(3))
  return Math.round(rounded * MM_PER_M)
}

/** 米 → 毫米字符串（按位数补零，负数保留符号） */
export function formatMillimeters(value, pad = 6) {
  const mm = toMillimeters(value)
  const sign = mm < 0 ? '-' : ''
  return sign + String(Math.abs(mm)).padStart(pad, '0')
}

/** 米制坐标 → 3 位小数字符串，如 212.44 → "212.440" */
export function formatMeters(value, digits = 3) {
  return toNumber(value).toFixed(digits)
}

/**
 * 生成地码：{x_mm}{mapCode}{y_mm}
 * @param {number} x 米
 * @param {number} y 米
 * @param {string} mapCode 地图代码，如 BB
 * @param {{pad?: number, digits?: number}} [opts]
 */
export function makeGroundCode(x, y, mapCode = '', opts = {}) {
  const pad = opts.pad ?? digitsToPad(opts.digits ?? 6)
  return `${formatMillimeters(x, pad)}${mapCode}${formatMillimeters(y, pad)}`
}

function digitsToPad(digits) {
  const n = Number(digits)
  return Number.isFinite(n) && n > 0 ? Math.min(12, Math.trunc(n)) : 6
}

/**
 * 地码 → 米制坐标（可识别地图代码）
 * @returns {{ok: boolean, x?: number, y?: number, mapCode?: string, reason?: string}}
 */
export function parseGroundCode(code, mapCode = '') {
  const text = String(code ?? '').trim()
  if (!text) return { ok: false, reason: 'empty' }
  let head = ''
  let tail = ''
  let map = mapCode
  if (map && text.includes(map)) {
    const idx = text.indexOf(map)
    head = text.slice(0, idx)
    tail = text.slice(idx + map.length)
  } else {
    const m = /^(-?\d+)([A-Za-z]*)(-?\d+)$/.exec(text)
    if (!m) return { ok: false, reason: 'format' }
    head = m[1]
    map = m[2]
    tail = m[3]
  }
  if (!/^-?\d+$/.test(head) || !/^-?\d+$/.test(tail)) return { ok: false, reason: 'format' }
  return {
    ok: true,
    x: Number.parseInt(head, 10) / MM_PER_M,
    y: Number.parseInt(tail, 10) / MM_PER_M,
    mapCode: map,
  }
}

/** 读取 MapCfg 顶层标量（不解析 PointInfo） */
export function parseMapMeta(xmlText) {
  const head = String(xmlText ?? '').slice(0, 4096)
  const cfg = /<MapCfg[^>]*>([\s\S]*)/.exec(head)
  const body = cfg ? cfg[1] : head
  const scalars = readScalars(body.replace(/<PointInfo[\s\S]*/, ''))
  return {
    name: scalars.MapName ?? '',
    qrCode: scalars.MapQRCode ?? '',
    mapType: scalars.MapType ?? '',
    row: toNumber(scalars.Row, 0),
    col: toNumber(scalars.Col, 0),
    width: toNumber(scalars.Width, 0),
    height: toNumber(scalars.Height, 0),
  }
}

/** 解析单个邻接段（<id> ... </NeighbInfo> 之间的一段） */
function parseNeighborChunk(chunk) {
  const ctrlMatch = /<CtrlPoint>([\s\S]*?)<\/CtrlPoint>/.exec(chunk)
  const scalarPart = ctrlMatch ? chunk.replace(ctrlMatch[0], '') : chunk
  const scalars = readScalars(scalarPart)
  const ctrlPoints = []
  if (ctrlMatch) {
    const posRe = /<Pos\b([^<>]*?)\/?>/g
    let m
    while ((m = posRe.exec(ctrlMatch[1]))) {
      const attrs = parseAttrs(m[1])
      const px = Number.parseFloat(attrs.xpos)
      const py = Number.parseFloat(attrs.ypos)
      if (Number.isFinite(px) && Number.isFinite(py)) ctrlPoints.push({ x: px, y: py })
    }
  }
  const targetId = Number.parseInt(scalars.id ?? '', 10)
  return {
    targetId: Number.isFinite(targetId) ? targetId : null,
    distance: Number.isFinite(Number.parseFloat(scalars.distance))
      ? Number.parseFloat(scalars.distance)
      : null,
    ctrlPoints,
    attrs: scalars,
  }
}

/**
 * 解析拓扑地图 XML
 * @param {string} xmlText XML 原文
 * @returns {{
 *   meta: object,
 *   nodes: Array<object>,
 *   links: Array<object>,
 *   nodeById: Map<number, object>,
 *   bounds: {minX:number,maxX:number,minY:number,maxY:number},
 *   stats: {nodeCount:number, linkCount:number, directedCount:number, curvedCount:number, dangling:number}
 * }}
 */
export function parseTopologyXml(xmlText) {
  if (typeof xmlText !== 'string' || !xmlText.trim()) {
    throw new Error('地图 XML 内容为空')
  }
  const meta = parseMapMeta(xmlText)
  const nodes = []
  const nodeById = new Map()
  const pointRe = /<PointInfo(\s[^<>]*)?>([\s\S]*?)<\/PointInfo>/g

  let m
  while ((m = pointRe.exec(xmlText))) {
    const attrs = parseAttrs(m[1] || '')
    const body = m[2] || ''
    const neighIdx = body.search(/<NeighbInfo[\s/>]/)
    const head = neighIdx >= 0 ? body.slice(0, neighIdx) : body
    const neighBody = neighIdx >= 0 ? body.slice(neighIdx) : ''
    const fields = readScalars(head)

    const id = Number.parseInt(attrs.id ?? fields.id ?? '', 10)
    if (!Number.isFinite(id)) continue
    const x = Number.parseFloat(attrs.xpos ?? fields.xpos ?? '')
    const y = Number.parseFloat(attrs.ypos ?? fields.ypos ?? '')
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue

    const neighbors = []
    const neighMatch = /<NeighbInfo(?:\s[^<>]*)?>([\s\S]*?)<\/NeighbInfo>/.exec(neighBody)
    if (neighMatch) {
      for (const chunk of neighMatch[1].split(/(?=<id>)/)) {
        if (!/<id>/.test(chunk)) continue
        const nb = parseNeighborChunk(chunk)
        if (nb.targetId !== null) neighbors.push(nb)
      }
    }

    const node = {
      id,
      x,
      y,
      width: toNumber(fields.width, 0),
      height: toNumber(fields.height, 0),
      value: toNumber(fields.value, 0),
      roadProperty: toNumber(fields.RoadProperty, 0),
      allDir: toNumber(fields.allDir, 0),
      eleDir: fields.EleDir ?? '',
      elePre: toNumber(fields.ElePre, 0),
      rotRad: toNumber(fields.RotRad, 0),
      robotType: fields.robottype ?? '',
      rotarySwitch: toNumber(fields.RotarySwitch, 0),
      sensorswitchPoint: toNumber(fields.sensorswitchPoint, 0),
      pioPoint: toNumber(fields.PioPoint, -1),
      ctuStance: toNumber(fields.CtuStance, 0),
      tranZoneType: toNumber(fields.TranZoneType, 0),
      isEmpty: false,
      neighbors,
      linkKeys: [],
      props: fields,
    }

    nodes.push(node)
    nodeById.set(id, node)
  }

  if (!nodes.length) throw new Error('未解析到任何 <PointInfo> 节点，请确认是拓扑地图 XML')

  // 组装无向线段（同一对节点的双向邻接合并为一条线）
  const links = []
  const linkByKey = new Map()
  let directedCount = 0
  let dangling = 0

  const straightPath = (a, b) => [
    { x: a.x, y: a.y },
    { x: b.x, y: b.y },
  ]

  for (const node of nodes) {
    for (const nb of node.neighbors) {
      directedCount += 1
      const other = nodeById.get(nb.targetId)
      if (!other) {
        dangling += 1
        continue
      }
      const a = node.id < other.id ? node : other
      const b = node.id < other.id ? other : node
      const key = `${a.id}_${b.id}`
      let link = linkByKey.get(key)
      if (!link) {
        link = {
          key,
          id: links.length,
          a: a.id,
          b: b.id,
          ax: a.x,
          ay: a.y,
          bx: b.x,
          by: b.y,
          distance: nb.distance ?? Math.hypot(b.x - a.x, b.y - a.y),
          dirs: {},
          polylines: [],
          curved: false,
        }
        linkByKey.set(key, link)
        links.push(link)
      }
      link.dirs[node.id] = {
        targetId: nb.targetId,
        distance: nb.distance,
        speed: toNumber(nb.attrs.Speed, 0),
        revert: toNumber(nb.attrs.Rever, 0),
        emptyCantRun: toNumber(nb.attrs.EmptyCantRun, 0),
        podDir: toNumber(nb.attrs.PodDir, -1),
        startDir: nb.attrs.StartDir ?? '',
        stopDir: nb.attrs.StopDir ?? '',
        laserType: toNumber(nb.attrs.LaserType, 0),
        robotType: nb.attrs.robottype ?? '',
        carryType: nb.attrs.carryType ?? '',
        ctnrtype: nb.attrs.ctnrtype ?? '',
        ctrlPoints: nb.ctrlPoints,
        props: nb.attrs,
      }
      if (!link.distance && nb.distance) link.distance = nb.distance

      // 有向段的多段线（本节点 → 目标节点）
      const poly = nb.ctrlPoints?.length
        ? [{ x: node.x, y: node.y }, ...nb.ctrlPoints, { x: other.x, y: other.y }]
        : straightPath(node, other)
      const signature = JSON.stringify(poly)
      if (!link.polylines.some((p) => p.signature === signature)) {
        link.polylines.push({ signature, points: poly, from: node.id, to: other.id, curved: poly.length > 2 })
      }
      if (poly.length > 2) link.curved = true
    }
  }

  // 至少要有一条显示用折线（直线兜底）
  for (const link of links) {
    if (!link.polylines.length) {
      link.polylines.push({
        signature: 'straight',
        points: straightPath({ x: link.ax, y: link.ay }, { x: link.bx, y: link.by }),
        from: link.a,
        to: link.b,
        curved: false,
      })
    }
    link.polylines.sort((p1, p2) => Number(p2.curved) - Number(p1.curved))
    link.path = link.polylines[0].points
    link.directed = Boolean(link.dirs[link.a]) && Boolean(link.dirs[link.b])
  }

  for (const node of nodes) {
    node.isEmpty = node.neighbors.length === 0
  }

  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const n of nodes) {
    if (n.x < minX) minX = n.x
    if (n.x > maxX) maxX = n.x
    if (n.y < minY) minY = n.y
    if (n.y > maxY) maxY = n.y
  }

  return {
    meta,
    nodes,
    links,
    nodeById,
    linkByKey,
    bounds: { minX, maxX, minY, maxY },
    stats: {
      nodeCount: nodes.length,
      linkCount: links.length,
      directedCount,
      curvedCount: links.filter((l) => l.curved).length,
      dangling,
      isolatedCount: nodes.filter((n) => n.isEmpty).length,
    },
  }
}

/** 点是否在矩形内 */
export function pointInRect(x, y, rect) {
  return x >= rect.minX && x <= rect.maxX && y >= rect.minY && y <= rect.maxY
}

/** 线段是否与轴对齐矩形相交 */
export function segmentIntersectsRect(x1, y1, x2, y2, rect) {
  if (pointInRect(x1, y1, rect) || pointInRect(x2, y2, rect)) return true
  const { minX, maxX, minY, maxY } = rect
  // 快速排除
  if (Math.max(x1, x2) < minX || Math.min(x1, x2) > maxX) return false
  if (Math.max(y1, y2) < minY || Math.min(y1, y2) > maxY) return false
  const edges = [
    [minX, minY, maxX, minY],
    [maxX, minY, maxX, maxY],
    [maxX, maxY, minX, maxY],
    [minX, maxY, minX, minY],
  ]
  return edges.some(([ex1, ey1, ex2, ey2]) => segmentsIntersect(x1, y1, x2, y2, ex1, ey1, ex2, ey2))
}

function segmentsIntersect(ax, ay, bx, by, cx, cy, dx, dy) {
  const d1 = cross(cx, cy, dx, dy, ax, ay)
  const d2 = cross(cx, cy, dx, dy, bx, by)
  const d3 = cross(ax, ay, bx, by, cx, cy)
  const d4 = cross(ax, ay, bx, by, dx, dy)
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))
}

function cross(ax, ay, bx, by, px, py) {
  return (bx - ax) * (py - ay) - (by - ay) * (px - ax)
}

/** 点到线段的距离 */
export function distanceToSegment(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1
  const dy = y2 - y1
  const lenSq = dx * dx + dy * dy
  if (lenSq === 0) return Math.hypot(px - x1, py - y1)
  let t = ((px - x1) * dx + (py - y1) * dy) / lenSq
  t = Math.max(0, Math.min(1, t))
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
}

/** 折线是否与矩形相交 */
export function polylineIntersectsRect(points, rect) {
  for (const p of points) {
    if (pointInRect(p.x, p.y, rect)) return true
  }
  for (let i = 1; i < points.length; i += 1) {
    if (segmentIntersectsRect(points[i - 1].x, points[i - 1].y, points[i].x, points[i].y, rect)) {
      return true
    }
  }
  return false
}

/** 点到折线的最近距离 */
export function distanceToPolyline(px, py, points) {
  let best = Infinity
  for (let i = 1; i < points.length; i += 1) {
    const d = distanceToSegment(px, py, points[i - 1].x, points[i - 1].y, points[i].x, points[i].y)
    if (d < best) best = d
  }
  return best
}

/* ─────────────────── 折线弧长参数化（临时点沿线调整用） ─────────────────── */

/** 折线总长度（米） */
export function polylineLength(points) {
  if (!points || points.length < 2) return 0
  let total = 0
  for (let i = 1; i < points.length; i += 1) {
    total += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y)
  }
  return total
}

/**
 * 按弧长比例取折线上的点（t=0 → 起点，t=1 → 终点，t=0.5 → 弧长中点）
 * @param {Array<{x:number,y:number}>} points
 * @param {number} t 0~1
 * @returns {{x:number,y:number,t:number}}
 */
export function pointOnPolylineAt(points, t) {
  if (!points || points.length === 0) return null
  if (points.length === 1) return { x: points[0].x, y: points[0].y, t: 0 }
  const total = polylineLength(points)
  if (total <= 0) return { x: points[0].x, y: points[0].y, t: 0 }
  const target = Math.min(1, Math.max(0, t)) * total
  let acc = 0
  for (let i = 1; i < points.length; i += 1) {
    const p0 = points[i - 1]
    const p1 = points[i]
    const seg = Math.hypot(p1.x - p0.x, p1.y - p0.y)
    if (acc + seg >= target || i === points.length - 1) {
      const local = seg > 0 ? (target - acc) / seg : 0
      const k = Math.min(1, Math.max(0, local))
      return { x: p0.x + (p1.x - p0.x) * k, y: p0.y + (p1.y - p0.y) * k, t: target / total }
    }
    acc += seg
  }
  const last = points[points.length - 1]
  return { x: last.x, y: last.y, t: 1 }
}

/**
 * 把任意点投影到折线上（找最近点），返回弧长比例与投影点
 * @returns {{t:number, x:number, y:number, dist:number}|null}
 */
export function nearestPointOnPolyline(px, py, points) {
  if (!points || points.length === 0) return null
  if (points.length === 1) {
    const p = points[0]
    return { t: 0, x: p.x, y: p.y, dist: Math.hypot(px - p.x, py - p.y) }
  }
  const total = polylineLength(points)
  let acc = 0
  let best = null
  for (let i = 1; i < points.length; i += 1) {
    const p0 = points[i - 1]
    const p1 = points[i]
    const dx = p1.x - p0.x
    const dy = p1.y - p0.y
    const lenSq = dx * dx + dy * dy
    const seg = Math.sqrt(lenSq)
    let k = lenSq > 0 ? ((px - p0.x) * dx + (py - p0.y) * dy) / lenSq : 0
    k = Math.min(1, Math.max(0, k))
    const x = p0.x + dx * k
    const y = p0.y + dy * k
    const dist = Math.hypot(px - x, py - y)
    if (!best || dist < best.dist) {
      best = { t: total > 0 ? (acc + seg * k) / total : 0, x, y, dist }
    }
    acc += seg
  }
  return best
}

/* ─────────────────────────── 属性筛选 ─────────────────────────── */

/**
 * 拆分多值：逗号（中英文）、分号、竖线、空白都算分隔符
 * @param {string} text
 * @returns {string[]}
 */
export function splitFilterValues(text) {
  return String(text ?? '')
    .split(/[,，;；|\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

/** 空值判定：null/undefined、空字符串、数字 0 都算「空」 */
export function isEmptyFieldValue(raw) {
  if (raw === null || raw === undefined) return true
  if (typeof raw === 'string') return raw.trim() === '' || raw.trim() === '-'
  const n = Number(raw)
  return Number.isFinite(n) ? n === 0 : false
}

/**
 * 单条筛选规则匹配
 *   - '=' / '!=' 支持多值（任一命中即可），值写「空 / empty / null」表示属性为空或为 0
 *   - '>' '>=' '<' '<=' 按数值比较（只取第一个值）
 * @param {string|number} raw 属性原始值
 * @param {string} op 运算符
 * @param {string} expected 输入值（可多值）
 * @returns {boolean} 规则未填值时应由调用方跳过（本函数返回 false）
 */
export function matchFieldRule(raw, op, expected) {
  const tokens = splitFilterValues(expected)
  if (!tokens.length) return false
  if (op === '=' || op === '!=') {
    const hit = tokens.some((token) => {
      const lower = token.toLowerCase()
      if (token === '空' || lower === 'empty' || lower === 'null') return isEmptyFieldValue(raw)
      if (String(raw) === token) return true
      const a = Number(raw)
      const b = Number(token)
      return Number.isFinite(a) && Number.isFinite(b) && a === b
    })
    return op === '=' ? hit : !hit
  }
  const a = Number(raw)
  const b = Number(tokens[0])
  if (!Number.isFinite(a) || !Number.isFinite(b)) return false
  if (op === '>') return a > b
  if (op === '>=') return a >= b
  if (op === '<') return a < b
  if (op === '<=') return a <= b
  return false
}

/* ─────────────────────────── 地码 CSV ─────────────────────────── */

/** CSV 单元格转义（含逗号 / 引号 / 换行时加引号） */
export function csvEscape(value) {
  const text = value === null || value === undefined ? '' : String(value)
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/**
 * 生成打印用地码 CSV：表头固定为「打印码值,备注」，仅两列
 * @param {Array<{code: string, remark?: string}>} rows
 * @returns {string}
 */
export function buildCodesCsv(rows) {
  const lines = ['打印码值,备注']
  for (const row of rows || []) {
    if (!row) continue
    const code = row.code ?? row.codeValue ?? ''
    if (!code) continue
    lines.push(`${csvEscape(code)},${csvEscape(row.remark ?? '')}`)
  }
  return lines.join('\r\n')
}
