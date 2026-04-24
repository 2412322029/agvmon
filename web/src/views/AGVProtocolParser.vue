<template>
  <div class="toolbox-container">
    <n-tabs type="card" size="large" default-value="parser">
      <n-tab-pane name="parser" tab="协议解析">
        <div class="parser-container">
          <div class="input-section">
            <n-form :model="formData" label-placement="top">
              <n-form-item label="十六进制数据输入">
                <n-input v-model:value="formData.inputHex" type="textarea" :rows="6"
                  placeholder="请输入AGV协议的十六进制数据，例如：050600E600010001000200010001000041424344202020..."
                  @input="handleInput" />
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

            <!-- 基本信息 -->
            <n-card size="small" title="基本信息" class="result-card">
              <div class="status-overview">
                <div class="status-item">
                  <div class="status-label">解析状态</div>
                  <div class="status-value">
                    <n-tag :type="parseResult.isValid ? 'success' : 'error'" size="large">
                      {{ parseResult.isValid ? '成功' : '失败' }}
                    </n-tag>
                  </div>
                </div>
                <div class="status-item">
                  <div class="status-label">Port口数量</div>
                  <div class="status-value port-count">{{ parseResult.portCount }}</div>
                </div>
              </div>
              <n-divider style="margin: 12px 0;"></n-divider>
              <n-descriptions :column="4" bordered>
                <n-descriptions-item label="协议头">
                  <span class="hex-value">0x{{ parseResult.header.fixed1.toString(16).padStart(2, '0').toUpperCase() }}
                    0x{{ parseResult.header.fixed2.toString(16).padStart(2, '0').toUpperCase() }}</span>
                </n-descriptions-item>
                <n-descriptions-item label="声明长度">{{ parseResult.header.declaredDataLength }} 字节</n-descriptions-item>
                <n-descriptions-item label="实际长度">{{ parseResult.header.actualDataLength }} 字节</n-descriptions-item>
                <n-descriptions-item label="长度校验">
                  <n-tag :type="parseResult.header.isValid ? 'success' : 'warning'">
                    {{ parseResult.header.isValid ? '通过' : '不匹配' }}
                  </n-tag>
                </n-descriptions-item>
              </n-descriptions>
              <div v-if="parseResult.gratingStatus.upperGrating && parseResult.gratingStatus.lowerGrating">
                <div class="grating-item">
                  <div class="grating-label">上层光栅</div>
                  <div class="grating-value">
                    <n-tag :type="parseResult.gratingStatus.upperGrating.code === 0 ? 'success' : 'warning'">
                      {{ parseResult.gratingStatus.upperGrating.text }}
                    </n-tag>
                    <span class="hex-code">0x{{ parseResult.gratingStatus.upperGrating.code.toString(16).padStart(2,
                      '0').toUpperCase() }}</span>
                  </div>
                </div>
                <div class="grating-item">
                  <div class="grating-label">下层光栅</div>
                  <div class="grating-value">
                    <n-tag :type="parseResult.gratingStatus.lowerGrating.code === 0 ? 'success' : 'warning'">
                      {{ parseResult.gratingStatus.lowerGrating.text }}
                    </n-tag>
                    <span class="hex-code">0x{{ parseResult.gratingStatus.lowerGrating.code.toString(16).padStart(2,
                      '0').toUpperCase() }}</span>
                  </div>
                </div>
              </div>

            </n-card>




            <!-- Port口信息 -->
            <n-card size="small" title="Port口信息" class="result-card" v-if="parseResult.isValid">
              <div class="port-summary">
                <div class="port-count">共 {{ parseResult.ports.length }} 个Port口</div>
              </div>
              <n-empty v-if="parseResult.ports.length === 0" description="没有Port口数据" />
              <div v-else class="port-collapse">
                <div v-for="(port, index) in parseResult.ports" :key="index" :name="index">
                  <div class="port-details">
                    <h2>{{ port.portPosition }}</h2>
                    <div class="port-status-grid">
                      <div class="status-grid-item">
                        <div class="status-grid-label">就绪状态</div>
                        <div class="status-grid-value">
                          <n-tag :type="port.status.readyStatus.code === 0 ? 'warning' : 'success'">
                            {{ port.status.readyStatus.text }}
                          </n-tag>
                          <span class="hex-code">0x{{ port.status.readyStatus.code.toString(16).padStart(2,
                            '0').toUpperCase() }}</span>
                        </div>
                      </div>
                      <div class="status-grid-item">
                        <div class="status-grid-label">TrayOk状态</div>
                        <div class="status-grid-value">
                          <n-tag :type="port.status.trayOkStatus.code === 0 ? 'warning' : 'success'">
                            {{ port.status.trayOkStatus.text }}
                          </n-tag>
                          <span class="hex-code">0x{{ port.status.trayOkStatus.code.toString(16).padStart(2,
                            '0').toUpperCase() }}</span>
                        </div>
                      </div>
                      <div class="status-grid-item">
                        <div class="status-grid-label">在线状态</div>
                        <div class="status-grid-value">
                          <n-tag :type="port.status.onlineStatus.code === 0 ? 'warning' : 'success'">
                            {{ port.status.onlineStatus.text }}
                          </n-tag>
                          <span class="hex-code">0x{{ port.status.onlineStatus.code.toString(16).padStart(2,
                            '0').toUpperCase() }}</span>
                        </div>
                      </div>
                      <div class="status-grid-item">
                        <div class="status-grid-label">Tray盘状态</div>
                        <div class="status-grid-value">
                          <n-tag :type="port.status.trayPresentStatus.code === 0 ? 'warning' : 'success'">
                            {{ port.status.trayPresentStatus.text }}
                          </n-tag>
                          <span class="hex-code">0x{{ port.status.trayPresentStatus.code.toString(16).padStart(2,
                            '0').toUpperCase() }}</span>
                        </div>
                      </div>
                      <div class="status-grid-item">
                        <div class="status-grid-label">Roller状态</div>
                        <div class="status-grid-value">
                          <n-tag :type="port.status.rollerStartStatus.code === 0 ? 'warning' : 'success'">
                            {{ port.status.rollerStartStatus.text }}
                          </n-tag>
                          <span class="hex-code">0x{{ port.status.rollerStartStatus.code.toString(16).padStart(2,
                            '0').toUpperCase() }}</span>
                        </div>
                      </div>
                      <div class="status-grid-item">
                        <div class="status-grid-label">人工操作</div>
                        <div class="status-grid-value">
                          <n-tag :type="port.status.manualOperation.code === 0 ? 'warning' : 'success'">
                            {{ port.status.manualOperation.text }}
                          </n-tag>
                          <span class="hex-code">0x{{ port.status.manualOperation.code.toString(16).padStart(2,
                            '0').toUpperCase() }}</span>
                        </div>
                      </div>
                      <div class="status-grid-item">
                        <div class="status-grid-label">Tray尺寸</div>
                        <div class="status-grid-value">
                          <n-tag :type="port.status.traySize.code === 0 ? 'warning' : 'success'">
                            {{ port.status.traySize.text }}
                          </n-tag>
                          <span class="hex-code">0x{{ port.status.traySize.code.toString(16).padStart(2,
                            '0').toUpperCase() }}</span>
                        </div>
                      </div>
                      <div class="status-grid-item">
                        <div class="status-grid-label">预留</div>
                        <div class="status-grid-value">
                          <n-tag type="default">
                            {{ port.status.reserved.text }}
                          </n-tag>
                          <span class="hex-code">0x{{ port.status.reserved.code.toString(16).padStart(2,
                            '0').toUpperCase() }}</span>
                        </div>
                      </div>
                      <div class="status-grid-item">
                        <div class="status-grid-label">trayId</div>
                        <div class="status-grid-value">
                          <n-tag type="default">
                            {{ port.trayId }}
                          </n-tag>
                        </div>
                      </div>
                    </div>

                  </div>
                </div>
              </div>
            </n-card>

            <!-- 原始数据 -->
            <n-card size="small" title="原始数据" class="result-card">
              <n-descriptions :column="1" bordered>
                <n-descriptions-item label="十六进制">
                  <div v-if="parseResult.rawData" class="hex-display">
                    <div
                      v-for="(chunk, index) in splitHexData(parseResult.rawData)"
                      :key="index"
                      class="hex-chunk"
                    >
                      {{ chunk }}
                    </div>
                  </div>
                  <div v-else class="hex-display">
                    无数据
                  </div>
                </n-descriptions-item>
                <n-descriptions-item label="ASCII表示">
                  <div
                    style="font-family: monospace; font-size: 16px; word-break: break-all; padding: 8px; border-radius: 4px;">
                    {{ hexToAscii(parseResult.rawData) }}
                  </div>
                </n-descriptions-item>
              </n-descriptions>

              <n-divider>数据分解</n-divider>
              <div class="data-breakdown" v-if="parseResult.isValid">
                <div><strong>协议头:</strong> {{ parseResult.rawData.substring(0, 4) }} (0x05 0x06)</div>
                <div><strong>数据长度:</strong> {{ parseResult.rawData.substring(4, 8) }} ({{
                  parseResult.header.declaredDataLength }} 字节)</div>
                <div><strong>光栅状态:</strong> {{ parseResult.rawData.substring(8, 12) }} (下层: 0x{{
                  parseResult.gratingStatus.lowerGrating.code.toString(16).padStart(2, '0').toUpperCase() }}, 上层: 0x{{
                    parseResult.gratingStatus.upperGrating.code.toString(16).padStart(2, '0').toUpperCase() }})</div>

                <div v-for="(port, index) in parseResult.ports" :key="index" style="margin-top: 8px;">
                  <strong>{{ port.portPosition }}:</strong>
                  <div style="margin-left: 16px; font-size: 12px;">
                    <div>就绪: 0x{{ port.status.readyStatus.code.toString(16).padStart(2, '0').toUpperCase() }},
                      TrayOk: 0x{{ port.status.trayOkStatus.code.toString(16).padStart(2, '0').toUpperCase() }},
                      在线: 0x{{ port.status.onlineStatus.code.toString(16).padStart(2, '0').toUpperCase() }}</div>
                    <div>Tray盘: 0x{{ port.status.trayPresentStatus.code.toString(16).padStart(2, '0').toUpperCase() }},
                      Roller: 0x{{ port.status.rollerStartStatus.code.toString(16).padStart(2, '0').toUpperCase() }},
                      人工: 0x{{ port.status.manualOperation.code.toString(16).padStart(2, '0').toUpperCase() }}</div>
                    <div>Tray尺寸: 0x{{ port.status.traySize.code.toString(16).padStart(2, '0').toUpperCase() }},
                      Tray ID: {{ port.trayId || '空' }}</div>
                  </div>
                </div>
              </div>
            </n-card>
          </div>

          <div v-if="parseResult && parseResult.warnings && parseResult.warnings.length > 0" class="warning-section">
            <n-divider>警告信息</n-divider>
            <n-alert type="warning" title="解析警告">
              <ul>
                <li v-for="(warning, index) in parseResult.warnings" :key="index">{{ warning }}</li>
              </ul>
            </n-alert>
          </div>

          <div v-if="parseResult && parseResult.error" class="error-section">
            <n-divider>错误信息</n-divider>
            <n-alert type="error" title="解析错误">
              {{ parseResult.error }}
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
import { NAlert, NButton, NCard, NDescriptions, NDescriptionsItem, NDivider, NEmpty, NForm, NFormItem, NInput, NSpace, NTabPane, NTabs, NTag } from 'naive-ui';
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
const expandedPorts = ref([]);

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
  // 这是一个4个Port口的示例数据
  formData.inputHex = '050600E60000010001010000000154465450414D3133303032000000000000000000000000000000000000000000000000000000000000000000000000000000010001010000000154465450414D31333030330000000000000000000000000000000000000000000000000000000000000000000000000000000100010100000001434650414D3133303032000000000000000000000000000000000000000000000000000000000000000000000000000000000100010100000001434650414D313330303100000000000000000000000000000000000000000000000000000000000000000000000000000000';
  parseData();
}

// 处理输入
function handleInput() {
  // 可选：实时验证或格式化输入
  // 例如，自动移除空格和非十六进制字符
  formData.inputHex = formData.inputHex.replace(/[^0-9A-Fa-f]/g, '').toUpperCase();
}

// 十六进制转ASCII
function hexToAscii(hex) {
  if (!hex) return '';
  let ascii = '';
  for (let i = 0; i < hex.length; i += 2) {
    const byte = parseInt(hex.substr(i, 2), 16);
    ascii += byte >= 32 && byte <= 126 ? String.fromCharCode(byte) : '.';
  }
  return ascii;
}

// 分割十六进制数据为可读块
function splitHexData(hex) {
  if (!hex) return [];
  const chunks = [];
  
  // 前12个字符单独显示
  if (hex.length > 12) {
    chunks.push(hex.substring(0, 12));
    // 剩余部分按116字符分割
    const chunkSize = 116;
    for (let i = 12; i < hex.length; i += chunkSize) {
      chunks.push(hex.substring(i, i + chunkSize));
    }
  } else {
    // 如果数据长度小于等于12，直接返回
    chunks.push(hex);
  }
  
  return chunks;
}



</script>

<style scoped>
.toolbox-container {
  padding: 20px;
  min-height: 100vh;
}

.parser-container {
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.input-section {
  margin-bottom: 20px;
}

.result-section {
  margin-top: 20px;
}

.result-card {
  margin-bottom: 16px;
  border-radius: 6px;
}

.warning-section,
.error-section {
  margin-top: 20px;
}

.data-breakdown {
  margin-top: 12px;
  padding: 12px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 16px;
  line-height: 1.6;
}

.data-breakdown div {
  margin-bottom: 4px;
  padding: 2px 0;
}

.data-breakdown strong {
  color: #1890ff;
}

/* 状态概览样式 */
.status-overview {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px;
  border-radius: 6px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-label {
  font-size: 12px;
  min-width: 80px;
}

.status-value {
  font-size: 16px;
  font-weight: bold;
}

.port-count {
  font-size: 24px;
  color: #1890ff;
}

.hex-value {
  font-family: monospace;
  font-size: 14px;
  color: #1890ff;
}

/* 光栅状态样式 */
.grating-status-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.grating-item {
  padding: 12px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 20px;
}

.grating-label {
  font-size: 12px;
  min-width: 80px;
}

.grating-value {
  display: flex;
  align-items: center;
  gap: 12px;
}

.hex-code {
  font-size: 12px;
  font-family: monospace;
}

/* Port口信息样式 */
.port-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.port-count {
  font-weight: bold;
  font-size: 14px;
}

.port-collapse {
  margin-top: 12px;
}

.port-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.port-header-tags {
  display: flex;
  align-items: center;
}

.port-details {
  padding: 12px 0;
}

.port-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.status-grid-item {
  padding: 10px;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
}

.status-grid-label {
  font-size: 12px;
  margin-bottom: 6px;
}

.status-grid-value {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tray-id-section {
  margin-top: 16px;
  padding: 12px;
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.tray-id-label {
  font-weight: bold;
  font-size: 14px;
}

.tray-id-value {
  font-size: 16px;
}

.hex-display {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hex-chunk {
  font-family: monospace;
  font-size: 16px;
  word-break: break-all;
  padding: 8px;
  border-radius: 4px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .status-overview {
    flex-direction: column;
    gap: 12px;
    align-items: flex-start;
  }

  .grating-status-container {
    flex-direction: column;
  }

  .port-status-grid {
    grid-template-columns: 1fr;
  }

  .tray-id-section {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}
</style>