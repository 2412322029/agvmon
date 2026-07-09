<template>
    <div style="margin-top: 50px; max-width: 1000px; margin: 0 auto;">
        <n-card title="系统设置" :bordered="false" embedded>
            <n-form :model="configForm" label-placement="left" label-width="200px">
                <n-form-item label="ZeroMQ 自动启停" path="zmq_auto">
                    <n-switch v-model:value="configForm.zmq_auto">
                        <template #checked>开启</template>
                        <template #unchecked>关闭</template>
                    </n-switch>
                </n-form-item>

                <n-form-item label="ZeroMQ 自动停止延迟(分)" path="zmq_auto_kill_timedelta">
                    <n-input-number v-model:value="configForm.zmq_auto_kill_timedelta" :min="0" :step="5"
                        style="width: 200px" />
                </n-form-item>
                <n-form-item label="RCMS API 地址" path="rcms.host">
                    <n-input v-model:value="configForm.rcms_host" />
                </n-form-item>

                <n-form-item label="WCS REST API" path="rcms.wcs_rest_api">
                    <n-input v-model:value="configForm.rcms_wcs_rest_api" />
                </n-form-item>

                <n-divider />
                <n-form-item label="自定义背景图片">
                    <n-space vertical>
                        <img v-if="bgPreview" :src="bgPreview" style="max-width:300px;max-height:150px;border-radius:6px;border:1px solid var(--n-border-color)" />
                        <input type="file" accept="image/*" @change="onBgFileChange" />
                        <n-button v-if="bgPreview" size="small" @click="saveBg" type="primary">应用背景</n-button>
                        <n-button v-if="hasCustomBg" size="small" @click="resetBg" secondary>恢复默认</n-button>
                    </n-space>
                </n-form-item>

            </n-form>

            <n-divider />
            <NAlert type="info" title="重启生效" style="margin: 20px 0 ;" >
            </NAlert>
            <n-space vertical>
                <n-space>
                    <n-button @click="saveAllConfig" type="primary">保存所有配置</n-button>
                    <n-button @click="reloadConfig" type="info">重新加载配置</n-button>
                </n-space>
            </n-space>
        </n-card>
    </div>

    <n-modal v-model:show="showChangesModal" preset="card" title="确认保存" style="max-width: 600px;">
        <NDescriptions label-placement="left" :column="1" size="small">
            <NDescriptionsItem v-for="change in changesData" :key="change.key" :label="change.key">
                <n-space>
                    <span style="color: #999; text-decoration: line-through;">{{ change.old }}</span>
                    <n-icon name="arrow-right" />
                    <span style="color: #18a058; font-weight: bold;">{{ change.new }}</span>
                </n-space>
            </NDescriptionsItem>
        </NDescriptions>

        <template #footer>
            <n-space justify="end">
                <n-button @click="cancelSave">取消</n-button>
                <n-button @click="confirmSave" type="primary">确认保存</n-button>
            </n-space>
        </template>
    </n-modal>
</template>

<script setup>
import {
    NAlert,
    NButton,
    NCard, NDescriptions, NDescriptionsItem, NDivider,
    NForm, NFormItem, NIcon, NInput, NInputNumber, NModal, NSpace, NSwitch, useMessage
} from 'naive-ui';
import { onMounted, reactive, ref } from 'vue';
import { applyBodyBg, resetBodyBg } from '../composables/bg';

const message = useMessage();

const configForm = reactive({
    zmq_auto: false,
    zmq_auto_kill_timedelta: 30,
    rcms_host: '',
    rcms_wcs_rest_api: ''
});

const originalConfig = ref({});
const showChangesModal = ref(false);
const changesData = ref([]);

const loadConfig = async () => {
    try {
        const keys = [
            'zmq_auto',
            'zmq_auto_kill_timedelta',
            'rcms.host',
            'rcms.wcs_rest_api'
        ];

        const response = await fetch(`/api/rcms/get_config?keys=${encodeURIComponent(keys.join(','))}`);
        const data = await response.json();

        if (data.message === 'success') {
            const configData = data.data;
            configForm.zmq_auto = configData.zmq_auto ?? false;
            configForm.zmq_auto_kill_timedelta = configData.zmq_auto_kill_timedelta ?? 30;
            configForm.rcms_host = configData['rcms.host'] ?? '';
            configForm.rcms_wcs_rest_api = configData['rcms.wcs_rest_api'] ?? '';

            originalConfig.value = {
                zmq_auto: configData.zmq_auto ?? false,
                zmq_auto_kill_timedelta: configData.zmq_auto_kill_timedelta ?? 30,
                rcms_host: configData['rcms.host'] ?? '',
                rcms_wcs_rest_api: configData['rcms.wcs_rest_api'] ?? ''
            };
        }
    } catch (error) {
        message.error('加载配置失败: ' + error.message);
    }
};

const hasUnsavedChanges = () => {
    return JSON.stringify(configForm) !== JSON.stringify(originalConfig.value);
};

const validateConfig = (configData) => {
    const errors = [];

    if (!configData['rcms.host'] || !configData['rcms.host'].startsWith('http')) {
        errors.push('RCMS API 地址必须以 http 或 https 开头');
    }

    if (configData['rcms.wcs_rest_api'] && !configData['rcms.wcs_rest_api'].startsWith('http')) {
        errors.push('WCS REST API 地址必须以 http 或 https 开头');
    }

    if (configData.zmq_auto_kill_timedelta < 0) {
        errors.push('ZeroMQ 自动停止延迟不能为负数');
    }

    return errors;
};

const getChanges = () => {
    const changes = [];
    const fieldLabels = {
        zmq_auto: 'ZeroMQ 自动启停',
        zmq_auto_kill_timedelta: 'ZeroMQ 自动停止延迟(分)',
        rcms_host: 'RCMS API 地址',
        rcms_wcs_rest_api: 'WCS REST API'
    };

    for (const key in configForm) {
        if (JSON.stringify(configForm[key]) !== JSON.stringify(originalConfig.value[key])) {
            changes.push({
                key: fieldLabels[key] || key,
                old: originalConfig.value[key],
                new: configForm[key]
            });
        }
    }

    return changes;
};

const saveAllConfig = async () => {
    const configData = {
        "zmq_auto": configForm.zmq_auto,
        "zmq_auto_kill_timedelta": configForm.zmq_auto_kill_timedelta,
        "rcms.host": configForm.rcms_host,
        "rcms.wcs_rest_api": configForm.rcms_wcs_rest_api
    };

    const errors = validateConfig(configData);
    if (errors.length > 0) {
        message.error('配置验证失败:\n' + errors.join('\n'));
        return;
    }

    if (!hasUnsavedChanges()) {
        message.warning('没有修改任何配置');
        return;
    }

    const changes = getChanges();
    if (changes.length > 0) {
        changesData.value = changes;
        showChangesModal.value = true;
    } else {
        message.warning('没有修改任何配置');
    }
};

const confirmSave = async () => {
    showChangesModal.value = false;
    
    const changes = getChanges();
    if (changes.length === 0) {
        message.warning('没有修改任何配置');
        return;
    }
    
    const configData = {};
    for (const change of changes) {
        const fieldMap = {
            'ZeroMQ 自动启停': 'zmq_auto',
            'ZeroMQ 自动停止延迟(分)': 'zmq_auto_kill_timedelta',
            'RCMS API 地址': 'rcms_host',
            'WCS REST API': 'rcms_wcs_rest_api'
        };
        const key = fieldMap[change.key];
        if (key) {
            configData[key.startsWith('rcms') ? key.replace('_', '.') : key] = configForm[key];
        }
    }
    
    try {
        const response = await fetch('/api/rcms/update_config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(configData)
        });
        
        const result = await response.json();
        
        if (result.message === 'success') {
            message.success('配置已保存');
            originalConfig.value = JSON.parse(JSON.stringify(configForm));
        } else {
            message.error('保存失败: ' + (result.errors?.[0] || '未知错误'));
        }
    } catch (error) {
        message.error(`保存配置失败: ` + error.message);
    }
};

const cancelSave = () => {
    showChangesModal.value = false;
};

const reloadConfig = async () => {
    await loadConfig();
    message.success('配置已重新加载');
};

// ── 自定义背景 ─────────────────────────────────────────────────────
const bgPreview = ref('');
const bgFile = ref(null);

function onBgFileChange(e) {
  const file = e.target.files?.[0];
  if (!file) return;
  bgFile.value = file;
  const reader = new FileReader();
  reader.onload = () => { bgPreview.value = reader.result; };
  reader.readAsDataURL(file);
}

async function saveBg() {
  if (!bgFile.value) return;
  const form = new FormData();
  form.append('file', bgFile.value);
  try {
    const res = await fetch('/api/util/background', { method: 'POST', body: form });
    if (res.ok) {
      localStorage.setItem('has_custom_bg', '1');
      hasCustomBg.value = true;
      applyBodyBg();
      message.success('背景已应用');
    } else {
      message.error('上传失败');
    }
  } catch (e) {
    message.error('上传失败: ' + e.message);
  }
}

async function resetBg() {
  try {
    await fetch('/api/util/background', { method: 'DELETE' });
    localStorage.removeItem('has_custom_bg');
    hasCustomBg.value = false;
    bgPreview.value = '';
    bgFile.value = null;
    resetBodyBg();
    message.success('已恢复默认背景');
  } catch (e) {
    message.error('操作失败');
  }
}

const hasCustomBg = ref(localStorage.getItem('has_custom_bg') === '1');

onMounted(() => {
    loadConfig();
    applyBodyBg();
});
</script>