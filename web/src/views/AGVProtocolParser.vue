<template>
  <div class="toolbox-container">
    <n-tabs type="card" size="large" default-value="parser">
      <n-tab-pane name="parser" tab="协议解析">
        <div class="parser-container">
          <div class="input-section">
            <n-form :model="formData" label-placement="top">
              <n-form-item label="十六进制数据输入">
                <n-input v-model:value="formData.inputHex" type="textarea" :rows="6"
                  placeholder="请输入AGV协议的十六进制数据，例如：0506007200000001010100..." @input="handleInput" />
              </n-form-item>
              <n-form-item>
                <n-space>
                  <n-button type="primary" @click="parseData" :disabled="!formData.inputHex">
                    解析数据
                  </n-button>
                  <n-button @click="clearData">清空</n-button>
                  <n-button @click="useSampleData">使用示例数据</n-button>
                </n-space>
              </n-form-item>
            </n-form>
          </div>

          <div class="result-section" v-if="parseResult">
            <n-divider>解析结果</n-divider>
            <n-card size="small" title="基本信息" class="result-card">
              <n-descriptions :column="2">
                <n-descriptions-item label="协议头">
                  0x{{ parseResult.header.fixed1.toString(16) }} 0x{{ parseResult.header.fixed2.toString(16) }}
                </n-descriptions-item>
                <n-descriptions-item label="声明长度">{{ parseResult.header.declaredLength }}</n-descriptions-item>
                <n-descriptions-item label="实际长度">{{ parseResult.header.actualLength }}</n-descriptions-item>
                <n-descriptions-item label="解析状态">
                  <n-tag :type="parseResult.isValid ? 'success' : 'error'">
                    {{ parseResult.isValid ? '成功' : '失败' }}
                  </n-tag>
                </n-descriptions-item>
              </n-descriptions>
            </n-card>

            <n-card size="small" title="设备状态" class="result-card">
              <n-descriptions :column="2">
                <n-descriptions-item label="故障代码">
                  0x{{ parseResult.status.errorCode.toString(16) }}
                </n-descriptions-item>
                <n-descriptions-item label="故障状态">{{ parseResult.status?.errorText || '-' }}</n-descriptions-item>
                <n-descriptions-item label="光栅代码">
                  0x{{ parseResult.status.reserved.toString(16) }}
                </n-descriptions-item>
                <n-descriptions-item label="光栅状态">{{ parseResult.status?.reservedText || '-' }}</n-descriptions-item>
              </n-descriptions>
            </n-card>

            <n-card size="small" title="端口信息" class="result-card">
              <div style="margin-bottom: 10px;">
                数量 {{ parseResult.ports.length }}
              </div>
              <n-empty v-if="parseResult.ports.length === 0" description="没有端口数据" />
              <div v-else>
                <n-table :data="parseResult.ports" :columns="portColumns" :pagination="false" size="small" />
                <div style="margin-top: 20px; padding: 10px; border-radius: 4px;">
                  <div v-for="(port, index) in parseResult.ports" :key="index" style="margin: 5px 0;">
                    端口 {{ port.portNumber }}:
                    <span
                      :style="{ color: port.loadUnload.code === 0x01 || port.loadUnload.code === 0x02 ? 'green' : 'red' }">{{
                        port.loadUnload.text }}</span> |
                    <span :style="{ color: port.trayPresent.code === 0x01 ? 'green' : 'red' }">{{
                      port.trayPresent.text }}</span> |
                    <span :style="{ color: port.onlineStatus.code === 0x01 ? 'green' : 'red' }">{{
                      port.onlineStatus.text }}</span> |
                    <span :style="{ color: port.trayId ? 'green' : 'red' }">{{ port.trayId || '-' }}</span>
                    <div v-if="port.trayId" style="margin-left: 20px; font-size: 11px; color: #666;">
                    </div>
                  </div>
                </div>
              </div>
            </n-card>

            <n-card size="small" title="ASCII 表示" class="result-card">
              <n-code :code="hexToAscii(parseResult.rawData)" language="text" :show-line-numbers="false" />
              <n-divider>数据分解</n-divider>
              <div class="data-breakdown">
                <div><strong>协议头:</strong> {{ parseResult.rawData.substring(0, 4) }} (0x05 0x06)</div>
                <div><strong>数据长度:</strong> {{ parseResult.rawData.substring(4, 8) }} ({{
                  parseResult.header.declaredLength }} 字节)</div>
                <div><strong>设备状态:</strong> {{ parseResult.rawData.substring(8, 12) }} (故障代码: 0x{{
                  parseResult.status.errorCode.toString(16) }}, 预留: 0x{{ parseResult.status.reserved.toString(16) }})
                </div>
                <div v-for="(port, index) in parseResult.ports" :key="index">
                  <strong>端口 {{ port.portNumber }}:</strong> {{ port.rawData }} (上下料: 0x{{
                    port.loadUnload.code.toString(16) }}, 托盘: 0x{{ port.trayPresent.code.toString(16) }}, 在线: 0x{{
                    port.onlineStatus.code.toString(16) }}, 预留: 0x{{ port.reserved.toString(16) }}, Tray ID: {{
                    port.trayId || '空' }})
                </div>
              </div>
            </n-card>
          </div>

          <div v-if="parseResult && parseResult.warnings.length > 0" class="warning-section">
            <n-divider>警告信息</n-divider>
            <n-alert type="warning" title="解析警告">
              <ul>
                <li v-for="(warning, index) in parseResult.warnings" :key="index">{{ warning }}</li>
              </ul>
            </n-alert>
          </div>

          <div v-if="errorMessage" class="error-section">
            <n-divider>错误信息</n-divider>
            <n-alert type="error" title="解析错误">
              {{ errorMessage }}
            </n-alert>
          </div>
        </div>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup>
import { NAlert, NButton, NCard, NCode, NDescriptions, NDescriptionsItem, NDivider, NEmpty, NForm, NFormItem, NInput, NSpace, NTable, NTabPane, NTabs, NTag } from 'naive-ui';
import { reactive, ref } from 'vue';
import AGVProtocolParser from './AGVProtocolParser';

// 创建解析器实例
const parser = new AGVProtocolParser();

// 响应式数据
const formData = reactive({
  inputHex: ''
});

const parseResult = ref(null);
const errorMessage = ref('');
const readCommand = ref('');

// 表格列配置
const portColumns = [
  {
    title: '端口号',
    key: 'portNumber',
    width: 80
  },
  {
    title: '上下料状态',
    key: 'loadUnload',
    width: 120,
    render: (row) => {
      return {
        type: 'span',
        style: { color: row.loadUnload.code === 0x01 || row.loadUnload.code === 0x02 ? 'green' : 'red' },
        children: row.loadUnload.text
      };
    }
  },
  {
    title: '托盘状态',
    key: 'trayPresent',
    width: 140,
    render: (row) => {
      return {
        type: 'span',
        style: { color: row.trayPresent.code === 0x01 ? 'green' : 'red' },
        children: row.trayPresent.text
      };
    }
  },
  {
    title: '在线状态',
    key: 'onlineStatus',
    width: 120,
    render: (row) => {
      return {
        type: 'span',
        style: { color: row.onlineStatus.code === 0x01 ? 'green' : 'red' },
        children: row.onlineStatus.text
      };
    }
  },
  {
    title: 'Tray ID',
    key: 'trayId',
    ellipsis: true,
    render: (row) => {
      return {
        type: 'span',
        style: { color: row.trayId ? 'green' : 'red' },
        children: row.trayId || '-'
      };
    }
  },
  {
    title: '原始数据',
    key: 'rawData',
    ellipsis: true,
    render: (row) => {
      return {
        type: 'span',
        style: 'font-family: monospace;',
        children: row.rawData
      };
    }
  }
];

// 处理数据输入
function handleInput() {
  // 可根据需要添加输入处理逻辑
}

// 解析数据
function parseData() {
  try {
    parseResult.value = parser.parseEQStatus(formData.inputHex);
    errorMessage.value = '';
    console.log('解析结果:', parseResult.value);
  } catch (error) {
    parseResult.value = null;
    errorMessage.value = error.message;
    console.error('解析错误:', error);
  }
}

// 清空数据
function clearData() {
  formData.inputHex = '';
  parseResult.value = null;
  errorMessage.value = '';
}

// 使用示例数据
function useSampleData() {
  formData.inputHex = '0506007200000102010100004238303041324D483037313730313432340D0A0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000';
  parseData();
}

// 十六进制转ASCII
function hexToAscii(hex) {
  let ascii = '';
  for (let i = 0; i < hex.length; i += 2) {
    const byte = parseInt(hex.substr(i, 2), 16);
    ascii += byte >= 32 && byte <= 126 ? String.fromCharCode(byte) : '.';
  }
  return ascii;
}
</script>

<style scoped>
.toolbox-container {
  padding: 10px;
}

.main-card {
  max-width: 1200px;
  margin: 0 auto;
}

.parser-container {
  padding: 10px 0;
}

.input-section {
  margin-bottom: 15px;
}

.result-section {
  margin-top: 15px;
}

.result-card {
  margin-bottom: 12px;
}

.warning-section,
.error-section {
  margin-top: 15px;
}

.generator-container {
  padding: 10px 0;
}

.data-breakdown {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.4;
}

.data-breakdown div {
  margin-bottom: 4px;
}
</style>