<script setup>
import {
  NAlert, NButton, NCard, NCheckbox, NDataTable, NDescriptions, NDescriptionsItem, NDivider,
  NForm, NFormItem, NInput, NInputNumber, NRadioButton, NRadioGroup, NSelect, NSpace,
  NTabPane, NTabs, NTag, NText, useMessage
} from 'naive-ui';
import { computed, h, onMounted, reactive, ref, watch } from 'vue';
import AGVProtocolParser from './AGVProtocolParser.js';

const message = useMessage();
const parser = new AGVProtocolParser();

const LIFT_COLOR = '#9254de';
const hex2 = (v) => (typeof v === 'number' ? v.toString(16).padStart(2, '0').toUpperCase() : '--');

const mainTab = ref('parse');

// 从「日志分析 → 报文行视图」跳转过来时携带的报文（sessionStorage 交接）
const LIFT_HANDOFF_KEY = 'lift-protocol:frames';
const LIFT_HANDOFF_SRC = 'lift-protocol:source';
const handoffSource = ref('');

// ══════════════════════════════════════════════════════════════════════
//  一、报文解析
// ══════════════════════════════════════════════════════════════════════
const parseInput = ref('');
const activeIdx = ref(0);

const parseResult = computed(() => (parseInput.value.trim() ? parser.parseElevatorStream(parseInput.value) : null));
const frames = computed(() => parseResult.value?.frames || []);
const activeFrame = computed(() => frames.value[activeIdx.value] || null);
watch(frames, (list) => { if (activeIdx.value >= list.length) activeIdx.value = 0; });

const frameRows = computed(() => frames.value.map((f, i) => ({
  idx: i,
  no: i + 1,
  direction: f.directionText,
  cmd: `0x${f.command.hex}`,
  name: f.command.name,
  floor: f.floorText,
  summary: f.lines.slice(1).join('  |  ') || '—',
  warnings: f.warnings.length,
  raw: f.rawData,
})));

const frameColumns = [
  { title: '#', key: 'no', width: 42 },
  { title: '方向', key: 'direction', width: 96 },
  { title: '命令字', key: 'cmd', width: 74 },
  { title: '命令名称', key: 'name', width: 165 },
  { title: '楼层', key: 'floor', width: 62 },
  { title: '摘要', key: 'summary', ellipsis: { tooltip: true } },
  {
    title: '告警', key: 'warnings', width: 56, align: 'center',
    render: (r) => (r.warnings
      ? h(NTag, { type: 'warning', size: 'tiny' }, { default: () => String(r.warnings) })
      : h('span', { style: 'color:var(--n-text-color-3)' }, '—')),
  },
];

function frameRowProps(row) {
  return {
    style: 'cursor:pointer',
    class: row.idx === activeIdx.value ? 'row-active' : '',
    onClick: () => { activeIdx.value = row.idx; },
  };
}

/** 按帧结构切分原始字节，供色块展示 */
function byteCellsOf(frame) {
  if (!frame?.bytes?.length) return [];
  const cells = [];
  const add = (label, cls, from, count) => {
    for (let i = 0; i < count; i++) {
      cells.push({
        key: `${label}-${from + i}`,
        label, cls,
        hex: hex2(frame.bytes[from + i]),
        offset: from + i,
        first: i === 0,
      });
    }
  };
  add('STX', 'seg-stx', 0, 2);
  add('BNK', 'seg-bnk', 2, 1);
  add('NOD', 'seg-nod', 3, 1);
  add('LEN', 'seg-len', 4, 1);
  add('DATA', 'seg-data', 5, frame.len);
  add('SUM', 'seg-sum', 5 + frame.len, 1);
  add('ETX', 'seg-etx', 6 + frame.len, 1);
  return cells;
}
const byteCells = computed(() => byteCellsOf(activeFrame.value));

/** 状态类应答第 5 字节的位定义（Bit7 → Bit0） */
const statusBits = computed(() => {
  const s = activeFrame.value?.status;
  if (!s || typeof s.code !== 'number') return [];
  const b = s.code;
  const bit = (n) => (b >> n) & 1;
  return [
    { bit: 7, name: '预留', value: bit(7), text: '协议预留' },
    { bit: 6, name: '预留', value: bit(6), text: '协议预留' },
    { bit: 5, name: '电梯模式', value: bit(5), text: bit(5) ? 'AGV 模式' : '人工模式(非 AGV)' },
    { bit: 4, name: '后门开门到位', value: bit(4), text: bit(4) ? '到位' : '未到位' },
    { bit: 3, name: '前门开门到位', value: bit(3), text: bit(3) ? '到位' : '未到位' },
    { bit: 2, name: '电梯状态', value: bit(2), text: bit(2) ? '异常' : '正常' },
    { bit: 1, name: '电梯下行状态', value: bit(1), text: bit(1) ? '下行' : '未下行' },
    { bit: 0, name: '电梯上行状态', value: bit(0), text: bit(0) ? '上行' : '未上行' },
  ];
});

const fieldColumns = [
  { title: '字段', key: 'field', width: 190 },
  { title: '原始值', key: 'value', width: 110 },
  { title: '说明', key: 'note' },
];

const statusBitColumns = [
  { title: 'Bit', key: 'bit', width: 50 },
  { title: '字段', key: 'name', width: 150 },
  {
    title: '值', key: 'value', width: 60,
    render: (r) => h(NTag, { type: r.value ? 'info' : 'default', size: 'tiny' }, { default: () => String(r.value) }),
  },
  { title: '含义', key: 'text' },
];

const SAMPLE = [
  'AB660000030100FF0003',   // 查询状态指令
  'AB6600000581000001200003', // 应答：1 楼 / AGV 模式 / 停梯
  'AB6600000581000001280003', // 应答：前门开门到位
  'AB66000004020000030003',   // 3 楼呼梯
  'AB660000038200010003',     // 呼梯应答
  'AB660000030300100003',     // 前门开门
  'AB660000030900010003',     // 进入 AGV 模式
].join('\n');

function fillParse(hex) {
  parseInput.value = hex;
  activeIdx.value = 0;
  mainTab.value = 'parse';
}
function loadSample() { parseInput.value = SAMPLE; activeIdx.value = 0; }

/** 接收「日志分析」跳转交接过来的多帧报文 */
onMounted(() => {
  let text = '';
  try {
    text = sessionStorage.getItem(LIFT_HANDOFF_KEY) || '';
    handoffSource.value = sessionStorage.getItem(LIFT_HANDOFF_SRC) || '';
    sessionStorage.removeItem(LIFT_HANDOFF_KEY);
    sessionStorage.removeItem(LIFT_HANDOFF_SRC);
  } catch (e) { /* 忽略 */ }
  if (!text.trim()) { handoffSource.value = ''; return; }
  parseInput.value = text;
  activeIdx.value = 0;
  mainTab.value = 'parse';
  const count = parser.parseElevatorStream(text).count;
  message.success(`已从日志分析载入 ${count} 帧报文${handoffSource.value ? '（' + handoffSource.value + '）' : ''}`);
});

// ══════════════════════════════════════════════════════════════════════
//  二、报文生成
// ══════════════════════════════════════════════════════════════════════
const agvCmds = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x08, 0x09];
const liftCmds = [0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x88, 0x89];

const gen = reactive({
  direction: 'agv',        // agv: AGV → 电梯；elevator: 电梯 → AGV（应答）
  command: 0x01,
  bnk: 0,
  nod: 0,
  id: 0,
  // 呼梯
  callMode: 0x00,
  floor: 1,
  // 门指令
  frontDoor: true,
  rearDoor: false,
  // 心跳
  robotStatus: 0,
  // 进料 / 出料
  flag: true,
  // 模式切换
  agvMode: 'agv',          // 'agv' 进入 AGV 模式 / 'manual' 退出为人工模式
  // 应答结果
  success: 'yes',          // 'yes' 成功 / 'no' 失败
  // 应答状态位
  statusMode: 'agv',       // Bit5：'agv' AGV 模式 / 'manual' 人工模式
  statusFrontDoorOpen: false,
  statusRearDoorOpen: false,
  statusAbnormal: false,
  statusUp: false,
  statusDown: false,
  // 校验和
  sumMode: 'off',          // off: 0x00（协议预留） / auto: 自动计算
});

const commandOptions = computed(() => (gen.direction === 'agv' ? agvCmds : liftCmds).map((c) => ({
  label: `0x${hex2(c)}  ${parser.elevatorCommands[c].name}`,
  value: c,
})));

watch(() => gen.direction, (dir) => {
  gen.command = dir === 'agv' ? 0x01 : 0x81;
});

const genParams = computed(() => ({
  id: gen.id,
  floor: gen.floor,
  callMode: gen.callMode,
  frontDoor: gen.frontDoor,
  rearDoor: gen.rearDoor,
  robotStatus: gen.robotStatus,
  flag: gen.flag,
  agvMode: gen.agvMode === 'agv',
  success: gen.success === 'yes',
  mode: gen.statusMode === 'agv',
  frontDoorOpen: gen.statusFrontDoorOpen,
  rearDoorOpen: gen.statusRearDoorOpen,
  abnormal: gen.statusAbnormal,
  up: gen.statusUp,
  down: gen.statusDown,
}));

const genResult = computed(() => parser.buildElevatorFrame({
  command: gen.command,
  bnk: gen.bnk,
  nod: gen.nod,
  params: genParams.value,
  sum: gen.sumMode,
}));

const genEcho = computed(() => parser.parseElevatorStream(genResult.value.hex));
const genEchoFrame = computed(() => genEcho.value.frames?.[0] || null);
const genByteCells = computed(() => byteCellsOf(genEchoFrame.value));

function resetGen() {
  gen.bnk = 0; gen.nod = 0; gen.id = 0;
  gen.callMode = 0x00; gen.floor = 1;
  gen.frontDoor = true; gen.rearDoor = false;
  gen.robotStatus = 0; gen.flag = true; gen.agvMode = 'agv';
  gen.success = 'yes';
  gen.statusMode = 'agv'; gen.statusFrontDoorOpen = false; gen.statusRearDoorOpen = false;
  gen.statusAbnormal = false; gen.statusUp = false; gen.statusDown = false;
  gen.sumMode = 'off';
}

/** 把生成结果送到解析页签做回读校验 */
function sendToParse(hex) {
  parseInput.value = hex;
  activeIdx.value = 0;
  mainTab.value = 'parse';
  message.success('已发送到解析');
}

async function copyText(text) {
  if (!text) { message.warning('没有可复制的内容'); return; }
  try {
    await navigator.clipboard.writeText(text);
    message.success('已复制到剪贴板');
  } catch (e) {
    message.error('复制失败，请手动选择复制');
  }
}

// ══════════════════════════════════════════════════════════════════════
//  三、协议速查
// ══════════════════════════════════════════════════════════════════════
const frameFormatRows = [
  { sym: 'STX', mean: '报文头', len: '2', content: '0xAB 0x66' },
  { sym: 'BNK', mean: '组编号', len: '1', content: '1 号群为 0，2 号群为 1，依此类推（无特殊说明填 00）' },
  { sym: 'NOD', mean: '设备编号', len: '1', content: '1 号梯为 0x00，2 号梯为 0x01，依此类推' },
  { sym: 'LEN', mean: 'DATA 字节数', len: '1', content: '根据数据内容确定' },
  { sym: 'DATA', mean: '数据内容', len: '-', content: '第 1 字节为命令字，其后为各命令的参数' },
  { sym: 'SUM', mean: '校验和', len: '1', content: 'SUM = ~(BNK+NOD+LEN+DATA)+1，协议中为预留、默认不启用（填 00）' },
  { sym: 'ETX', mean: '报文尾', len: '1', content: '0x03，表示通讯数据结束' },
];
const frameFormatColumns = [
  { title: '符号', key: 'sym', width: 80 },
  { title: '含义', key: 'mean', width: 130 },
  { title: '长度(字节)', key: 'len', width: 100 },
  { title: '内容', key: 'content' },
];

const COMMAND_DESC = {
  0x01: '轮询读取电梯楼层 / 模式 / 门状态 / 上下行',
  0x02: '呼梯登记：登记楼层 + 控制模式（00 超时关门 / 01 门常开）',
  0x03: '轿厢式电梯开门指令，00 模式下需持续发送保持常开',
  0x04: '机器人状态及与电梯间心跳（无其它报文时 10s 内发送一次）',
  0x05: 'AGV 进料中（电梯液晶展示用，协议预留）',
  0x06: 'AGV 出料中（电梯液晶展示用，协议预留）',
  0x08: '关门指令：可提高关门效率，模式 01 时使用',
  0x09: '进入 / 退出 AGV 模式（Bit0：1 进入 AGV 模式）',
  0x81: '查询应答：楼层 + 状态位（模式 / 门到位 / 状态 / 上下行）',
  0x82: '呼梯应答：Bit0 1 成功 / 0 失败',
  0x83: '开门应答：楼层 + 状态位',
  0x84: '心跳应答：DATA[3] = 0xFF',
  0x85: '进料应答：Bit0 1 成功 / 0 失败',
  0x86: '出料应答：Bit0 1 成功 / 0 失败',
  0x88: '关门应答：楼层 + 状态位',
  0x89: '模式切换应答：Bit0 1 成功 / 0 失败',
};

const commandRows = computed(() => Object.entries(parser.elevatorCommands).map(([code, v]) => ({
  code: `0x${hex2(Number(code))}`,
  name: v.name,
  dir: v.dir === 'agv' ? 'AGV → 电梯' : '电梯 → AGV',
  dataLen: `${v.dataLen}`,
  desc: COMMAND_DESC[Number(code)] || '',
})));

const commandColumns = [
  { title: '命令字', key: 'code', width: 80 },
  { title: '命令名称', key: 'name', width: 160 },
  { title: '方向', key: 'dir', width: 100 },
  { title: 'DATA 长度', key: 'dataLen', width: 90, align: 'center' },
  { title: '说明', key: 'desc' },
];

const EXAMPLES = [
  { no: 1, name: '查询状态指令', request: 'AB660000030100FF0003', response: 'AB6600000581000001200003' },
  { no: 2, name: '1 楼呼梯', request: 'AB66000004020000010003', response: 'AB660000038200010003' },
  { no: 3, name: '3 楼呼梯', request: 'AB66000004020000030003', response: 'AB660000038200010003' },
  { no: 4, name: '前门开门', request: 'AB660000030300100003', response: 'AB6600000583000001200003' },
  { no: 5, name: '前门关门', request: 'AB660000030800100003', response: 'AB6600000588000001200003' },
  { no: 6, name: '进入 AGV 模式', request: 'AB660000030900010003', response: 'AB660000038900010003' },
  { no: 7, name: '退出 AGV 模式', request: 'AB660000030900000003', response: 'AB660000038900010003' },
];
const exampleColumns = [
  { title: '#', key: 'no', width: 42 },
  { title: '指令', key: 'name', width: 130 },
  {
    title: 'AGV 发送（报文）', key: 'request',
    render: (r) => h('span', { style: 'font-family:monospace;font-size:12px' }, r.request),
  },
  {
    title: '电梯返回（示例）', key: 'response',
    render: (r) => h('span', { style: 'font-family:monospace;font-size:12px' }, r.response),
  },
  {
    title: '操作', key: 'actions', width: 150,
    render: (r) => h(NSpace, { size: 4 }, {
      default: () => [
        h(NButton, { size: 'tiny', secondary: true, onClick: () => fillParse(r.request) }, { default: () => '解析发送' }),
        h(NButton, { size: 'tiny', secondary: true, onClick: () => fillParse(r.response) }, { default: () => '解析返回' }),
      ],
    }),
  },
];

const notes = [
  'SUM 为预留字段，默认不启用（示例报文填 00）；开启时 SUM = ~(BNK+NOD+LEN+DATA)+1。',
  '只使用一侧的电梯默认使用前门；需要两侧开门时由现场人员告知前后关系。',
  '呼梯成功后电梯驶向起始楼层并开门；若已在当前楼层则直接开门；A 层开门状态下收到 B 层呼梯，电梯自主关门到 B 层再开门。',
  '启用人工/AGV 模式切换时，每条指令发出前都会先查询是否为 AGV 模式，不是则发送进入 AGV 模式指令并再次查询（防呆）。',
  '无任务交互时 WCS 主动发送进入人工模式指令退出 AGV 模式。',
  'RS485 对接时电梯需在收到指令 50ms 后再回复；422/232 无此限制。指令均为一问一答。',
];
</script>

<template>
  <div class="lift-container">
    <div class="page-head">
      <h2 style="margin:0">电梯报文工具 <n-tag size="small" :color="{ color: 'rgba(146,84,222,0.15)', textColor: LIFT_COLOR, borderColor: LIFT_COLOR }">AB66</n-tag></h2>
      <n-text depth="3" style="font-size:12px">
        纯轿厢式电梯 · 模式切换协议 —— 解析与生成 16 进制报文（一问一答，多帧自动拆分）
      </n-text>
    </div>

    <n-tabs type="line" size="large" v-model:value="mainTab">
      <!-- ═══ 解析 ═══ -->
      <n-tab-pane name="parse" tab="报文解析">
        <n-card size="small" title="十六进制报文">
          <n-alert v-if="handoffSource" type="info" closable style="margin-bottom:8px" @close="handoffSource = ''">
            已从「日志分析 · 报文行视图」载入 {{ frames.length }} 帧报文（来源：{{ handoffSource }}），下方按帧逐条解析。
          </n-alert>
          <n-form label-placement="left" label-width="90">
            <n-form-item label="报文输入">
              <n-input v-model:value="parseInput" type="textarea" :rows="6" class="mono"
                placeholder="AB660000030100FF0003&#10;支持空格/逗号/换行分隔，可一次粘贴多帧（如请求 + 应答）" />
            </n-form-item>
            <n-form-item>
              <n-space>
                <n-button @click="loadSample">载入示例报文</n-button>
                <n-button @click="parseInput = ''" :disabled="!parseInput">清空</n-button>
                <n-button secondary @click="copyText(parseInput)" :disabled="!parseInput">复制输入</n-button>
              </n-space>
            </n-form-item>
          </n-form>

          <n-alert v-if="parseResult && !parseResult.isValid" type="error" :show-icon="true" style="margin-bottom:8px">
            {{ parseResult.error || '解析失败' }}
          </n-alert>

          <template v-if="frames.length">
            <n-space align="center" style="margin:4px 0 8px">
              <n-tag type="success" size="small">共 {{ frames.length }} 帧</n-tag>
              <n-text depth="3" style="font-size:12px">总长度 {{ parseResult.rawData.length / 2 }} 字节</n-text>
              <n-tag v-if="parseResult.errors?.length" type="warning" size="small">{{ parseResult.errors.length }} 条告警</n-tag>
            </n-space>

            <n-data-table :columns="frameColumns" :data="frameRows" :row-props="frameRowProps"
              :row-key="(r) => r.idx" size="small" :bordered="false" max-height="320" />

            <template v-if="activeFrame">
              <n-divider style="margin:12px 0 8px">第 {{ activeIdx + 1 }} 帧 —— {{ activeFrame.directionText }} · {{ activeFrame.command.name }}（0x{{ activeFrame.command.hex }}）</n-divider>

              <!-- 字节色块 -->
              <div class="byte-strip">
                <div v-for="c in byteCells" :key="c.key" class="byte-cell" :class="c.cls">
                  <span class="byte-off">{{ c.offset }}</span>
                  <span class="byte-hex">{{ c.hex }}</span>
                  <span class="byte-seg">{{ c.first ? c.label : '' }}</span>
                </div>
              </div>

              <n-space align="center" style="margin:8px 0">
                <n-tag size="small" :type="activeFrame.etxValid ? 'success' : 'error'">
                  ETX {{ activeFrame.etxValid ? '正常' : '异常' }}
                </n-tag>
                <n-tag size="small" :type="activeFrame.sumDisabled ? 'default' : 'success'">
                  SUM {{ activeFrame.sumDisabled ? '预留未启用 (00)' : activeFrame.sum === activeFrame.sumExpected ? '校验通过' : '校验不符' }}
                </n-tag>
                <n-tag size="small" type="info">{{ activeFrame.directionText }}</n-tag>
                <n-tag size="small">组编号 {{ activeFrame.bnk }}（{{ activeFrame.bnk + 1 }} 号群）· 设备编号 {{ activeFrame.nod }}（{{ activeFrame.nod + 1 }} 号梯）</n-tag>
                <n-button size="tiny" secondary @click="copyText(activeFrame.rawData)">复制本帧</n-button>
                <n-button size="tiny" secondary @click="copyText(parseInput)">复制全部</n-button>
              </n-space>

              <n-data-table :columns="fieldColumns" :data="activeFrame.fields" size="small" :bordered="false" />

              <template v-if="statusBits.length">
                <n-divider style="margin:12px 0 8px">状态字节位域（DATA[5] = 0x{{ activeFrame.status.hex }}）</n-divider>
                <n-data-table :columns="statusBitColumns" :data="statusBits" size="small" :bordered="false" />
              </template>

              <n-alert v-if="activeFrame.warnings.length" type="warning" :show-icon="true" style="margin-top:10px">
                <div v-for="w in activeFrame.warnings" :key="w">{{ w }}</div>
              </n-alert>
            </template>
          </template>

          <n-text v-else-if="parseInput.trim()" depth="3" style="font-size:12px">
            未解析到有效帧，请确认报文以 AB66 开头且为完整帧（STX + BNK + NOD + LEN + DATA + SUM + ETX）。
          </n-text>
        </n-card>
      </n-tab-pane>

      <!-- ═══ 生成 ═══ -->
      <n-tab-pane name="generate" tab="报文生成">
        <n-card size="small" title="报文参数">
          <n-form label-placement="left" label-width="130">
            <n-form-item label="通信方向">
              <n-radio-group v-model:value="gen.direction">
                <n-radio-button value="agv">AGV → 电梯（请求）</n-radio-button>
                <n-radio-button value="elevator">电梯 → AGV（应答）</n-radio-button>
              </n-radio-group>
            </n-form-item>

            <n-form-item label="命令字">
              <n-select v-model:value="gen.command" :options="commandOptions" style="width:320px" />
            </n-form-item>

            <n-form-item label="群组 / 设备">
              <n-space align="center">
                <n-text depth="3" style="font-size:12px">BNK</n-text>
                <n-input-number v-model:value="gen.bnk" :min="0" :max="255" style="width:110px" />
                <n-text depth="3" style="font-size:12px">{{ gen.bnk + 1 }} 号群</n-text>
                <n-text depth="3" style="font-size:12px;margin-left:8px">NOD</n-text>
                <n-input-number v-model:value="gen.nod" :min="0" :max="255" style="width:110px" />
                <n-text depth="3" style="font-size:12px">{{ gen.nod + 1 }} 号梯</n-text>
              </n-space>
            </n-form-item>

            <n-form-item label="ID 号">
              <n-space align="center">
                <n-input-number v-model:value="gen.id" :min="0" :max="255" style="width:110px" />
                <n-text depth="3" style="font-size:12px">默认 0x00</n-text>
              </n-space>
            </n-form-item>

            <!-- 0x02 呼梯 -->
            <template v-if="gen.command === 0x02">
              <n-form-item label="控制模式">
                <n-radio-group v-model:value="gen.callMode">
                  <n-radio-button :value="0x00">00 到达后，超时自动关门</n-radio-button>
                  <n-radio-button :value="0x01">01 到达后，门保持常开</n-radio-button>
                </n-radio-group>
              </n-form-item>
              <n-form-item label="登记楼层">
                <n-space align="center">
                  <n-input-number v-model:value="gen.floor" :min="1" :max="127" style="width:110px" />
                  <n-text depth="3" style="font-size:12px">1 ~ 127，楼层从 1 起（低 7 位）</n-text>
                </n-space>
              </n-form-item>
              <n-form-item label="使用后门">
                <n-checkbox v-model:checked="gen.rearDoor">Bit7 = 1（不勾选为前门）</n-checkbox>
              </n-form-item>
            </template>

            <!-- 0x03 / 0x08 开 / 关门 -->
            <template v-if="gen.command === 0x03 || gen.command === 0x08">
              <n-form-item label="门动作">
                <n-space align="center">
                  <n-checkbox v-model:checked="gen.frontDoor">前门（Bit4）</n-checkbox>
                  <n-checkbox v-model:checked="gen.rearDoor">后门（Bit5）</n-checkbox>
                </n-space>
              </n-form-item>
            </template>

            <!-- 0x04 心跳 -->
            <template v-if="gen.command === 0x04">
              <n-form-item label="机器人状态">
                <n-space align="center">
                  <n-input-number v-model:value="gen.robotStatus" :min="0" :max="15" style="width:110px" />
                  <n-text depth="3" style="font-size:12px">Bit3~0：0 正常 / 非 0 异常</n-text>
                </n-space>
              </n-form-item>
            </template>

            <!-- 0x05 / 0x06 进料 / 出料 -->
            <template v-if="gen.command === 0x05 || gen.command === 0x06">
              <n-form-item label="标志位">
                <n-checkbox v-model:checked="gen.flag">
                  {{ gen.command === 0x05 ? '进料中 = 1' : '出料中 = 1' }}（Bit0）
                </n-checkbox>
              </n-form-item>
            </template>

            <!-- 0x09 模式切换 -->
            <template v-if="gen.command === 0x09">
              <n-form-item label="目标模式">
                <n-radio-group v-model:value="gen.agvMode">
                  <n-radio-button value="agv">1 进入 AGV 模式</n-radio-button>
                  <n-radio-button value="manual">0 退出（人工模式）</n-radio-button>
                </n-radio-group>
              </n-form-item>
            </template>

            <!-- 0x81 / 0x83 / 0x88 状态类应答 -->
            <template v-if="[0x81, 0x83, 0x88].includes(gen.command)">
              <n-form-item label="所在楼层">
                <n-space align="center">
                  <n-input-number v-model:value="gen.floor" :min="1" :max="127" style="width:110px" />
                  <n-text depth="3" style="font-size:12px">DATA[4] Bit6~0，楼层从 1 起</n-text>
                </n-space>
              </n-form-item>
              <n-form-item label="电梯模式">
                <n-radio-group v-model:value="gen.statusMode">
                  <n-radio-button value="agv">1 AGV 模式</n-radio-button>
                  <n-radio-button value="manual">0 人工模式</n-radio-button>
                </n-radio-group>
              </n-form-item>
              <n-form-item label="开门到位">
                <n-space align="center">
                  <n-checkbox v-model:checked="gen.statusFrontDoorOpen">前门开门到位（Bit3）</n-checkbox>
                  <n-checkbox v-model:checked="gen.statusRearDoorOpen">后门开门到位（Bit4）</n-checkbox>
                </n-space>
              </n-form-item>
              <n-form-item label="电梯状态">
                <n-checkbox v-model:checked="gen.statusAbnormal">异常（Bit2：不勾选为正常）</n-checkbox>
              </n-form-item>
              <n-form-item label="上 / 下行">
                <n-space align="center">
                  <n-checkbox v-model:checked="gen.statusUp">上行（Bit0）</n-checkbox>
                  <n-checkbox v-model:checked="gen.statusDown">下行（Bit1）</n-checkbox>
                  <n-text depth="3" style="font-size:12px">两者都为 0 即停梯</n-text>
                </n-space>
              </n-form-item>
            </template>

            <!-- 应答结果 -->
            <template v-if="[0x82, 0x85, 0x86, 0x89].includes(gen.command)">
              <n-form-item label="执行结果">
                <n-radio-group v-model:value="gen.success">
                  <n-radio-button value="yes">1 成功</n-radio-button>
                  <n-radio-button value="no">0 失败</n-radio-button>
                </n-radio-group>
              </n-form-item>
              <n-form-item v-if="gen.command === 0x82" label="批注提示">
                <n-text depth="3" style="font-size:12px">文档批注中 DATA[3] 同时表示呼梯模式：00 超时关门 / 01 门常开</n-text>
              </n-form-item>
            </template>

            <n-form-item label="校验和 SUM">
              <n-space align="center">
                <n-radio-group v-model:value="gen.sumMode">
                  <n-radio-button value="off">0x00（协议预留）</n-radio-button>
                  <n-radio-button value="auto">自动计算</n-radio-button>
                </n-radio-group>
                <n-text depth="3" style="font-size:12px">
                  SUM = ~(BNK+NOD+LEN+DATA)+1 = 0x{{ hex2(genResult.sumExpected) }}
                </n-text>
              </n-space>
            </n-form-item>

            <n-form-item>
              <n-space>
                <n-button @click="resetGen">重置参数</n-button>
                <n-button secondary @click="sendToParse(genResult.hex)">发送到解析</n-button>
              </n-space>
            </n-form-item>
          </n-form>
        </n-card>

        <n-card size="small" title="生成结果" style="margin-top:10px">
          <n-alert v-if="genResult.warnings.length" type="warning" :show-icon="true" style="margin-bottom:8px">
            <div v-for="w in genResult.warnings" :key="w">{{ w }}</div>
          </n-alert>

          <div class="hex-out">
            <span class="hex-out-text">{{ genResult.hex }}</span>
            <n-button size="tiny" type="primary" secondary @click="copyText(genResult.hex)">复制</n-button>
          </div>

          <n-descriptions :column="4" bordered size="small" style="margin-top:10px">
            <n-descriptions-item label="命令字">
              0x{{ hex2(gen.command) }} {{ parser.elevatorCommands[gen.command].name }}
            </n-descriptions-item>
            <n-descriptions-item label="DATA 长度">{{ genResult.dataBytes.length }} 字节</n-descriptions-item>
            <n-descriptions-item label="DATA">{{ genResult.dataBytes.map((b) => hex2(b)).join(' ') }}</n-descriptions-item>
            <n-descriptions-item label="SUM">
              {{ hex2(genResult.sum) }}{{ genResult.sum === 0 ? '（预留）' : genResult.sum === genResult.sumExpected ? '（正确）' : '' }}
            </n-descriptions-item>
          </n-descriptions>

          <div v-if="genByteCells.length" class="byte-strip" style="margin-top:10px">
            <div v-for="c in genByteCells" :key="'g' + c.key" class="byte-cell" :class="c.cls">
              <span class="byte-off">{{ c.offset }}</span>
              <span class="byte-hex">{{ c.hex }}</span>
              <span class="byte-seg">{{ c.first ? c.label : '' }}</span>
            </div>
          </div>

          <n-divider style="margin:12px 0 8px">回读校验（用解析器反解生成结果）</n-divider>
          <div v-if="genEchoFrame">
            <n-space align="center" style="margin-bottom:6px">
              <n-tag size="small" :color="{ color: 'rgba(146,84,222,0.15)', textColor: LIFT_COLOR, borderColor: LIFT_COLOR }">
                {{ genEchoFrame.directionText }}
              </n-tag>
              <n-tag size="small">{{ genEchoFrame.command.name }}（0x{{ genEchoFrame.command.hex }}）</n-tag>
              <n-tag v-if="genEchoFrame.floor !== undefined" size="small">{{ genEchoFrame.floorText }}</n-tag>
              <n-tag size="small" :type="genEchoFrame.sumDisabled ? 'default' : 'success'">
                SUM {{ genEchoFrame.sumDisabled ? '预留未启用' : genEchoFrame.sum === genEchoFrame.sumExpected ? '校验通过' : '校验不符' }}
              </n-tag>
            </n-space>
            <n-data-table :columns="fieldColumns" :data="genEchoFrame.fields" size="small" :bordered="false" />
            <n-alert v-if="genEchoFrame.warnings.length" type="warning" :show-icon="true" style="margin-top:8px">
              <div v-for="w in genEchoFrame.warnings" :key="w">{{ w }}</div>
            </n-alert>
          </div>
        </n-card>
      </n-tab-pane>

      <!-- ═══ 速查 ═══ -->
      <n-tab-pane name="ref" tab="协议速查">
        <n-card size="small" title="报文格式">
          <n-data-table :columns="frameFormatColumns" :data="frameFormatRows" size="small" :bordered="false" />
        </n-card>

        <n-card size="small" title="命令字一览" style="margin-top:10px">
          <n-data-table :columns="commandColumns" :data="commandRows" size="small" :bordered="false" />
        </n-card>

        <n-card size="small" title="指令示例（点击可直接解析）" style="margin-top:10px">
          <n-data-table :columns="exampleColumns" :data="EXAMPLES" size="small" :bordered="false"
            :row-key="(r) => r.no" />
        </n-card>

        <n-card size="small" title="备注" style="margin-top:10px">
          <ul class="note-list">
            <li v-for="(n, i) in notes" :key="i"><n-text depth="2" style="font-size:13px">{{ n }}</n-text></li>
          </ul>
        </n-card>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<style scoped>
.lift-container {
  padding: 8px 12px 24px;
  max-width: 1200px;
  margin: 0 auto;
}
.page-head {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 4px;
}
.mono :deep(textarea) {
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  letter-spacing: 0.5px;
}

/* 字节色块 */
.byte-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 10px;
  background: var(--n-color-embedded);
  border-radius: 6px;
}
.byte-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 42px;
  padding: 4px 6px;
  border-radius: 4px;
  border: 1px solid transparent;
}
.byte-off {
  font-size: 10px;
  color: var(--n-text-color-3);
  line-height: 1.1;
}
.byte-hex {
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
}
.byte-seg {
  font-size: 10px;
  line-height: 1.2;
  min-height: 12px;
  color: var(--n-text-color-2);
}
.seg-stx { background: rgba(120, 120, 120, 0.12); border-color: rgba(120, 120, 120, 0.4); }
.seg-bnk { background: rgba(32, 128, 240, 0.12); border-color: rgba(32, 128, 240, 0.4); }
.seg-nod { background: rgba(32, 160, 240, 0.14); border-color: rgba(32, 160, 240, 0.45); }
.seg-len { background: rgba(240, 160, 32, 0.14); border-color: rgba(240, 160, 32, 0.45); }
.seg-data { background: rgba(24, 160, 88, 0.12); border-color: rgba(24, 160, 88, 0.4); }
.seg-sum { background: rgba(146, 84, 222, 0.12); border-color: rgba(146, 84, 222, 0.45); }
.seg-etx { background: rgba(208, 48, 80, 0.12); border-color: rgba(208, 48, 80, 0.4); }

/* 生成结果 */
.hex-out {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--n-color-embedded);
  border-radius: 6px;
}
.hex-out-text {
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
  color: #9254de;
  word-break: break-all;
  flex: 1;
}
.note-list {
  margin: 0;
  padding-left: 18px;
}
.note-list li {
  margin-bottom: 6px;
  line-height: 1.6;
}
:deep(.row-active td) {
  background: rgba(146, 84, 222, 0.12) !important;
}
</style>
