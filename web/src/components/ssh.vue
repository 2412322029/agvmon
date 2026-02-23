<template>
    <div class="ssh-container">
        <!-- 连接表单 -->
        <n-card v-if="showInput" title="SSH 连接" :bordered="false" size="small" segmented>
            <n-form :model="connectionForm" :rules="connectionRules" ref="formRef">
                <n-grid :cols="24" :x-gap="12" :y-gap="8">
                    <n-form-item-gi :span="24" :span-s="24" label="主机地址" path="host">
                        <n-input v-model:value="connectionForm.host" placeholder="请输入主机地址" />
                    </n-form-item-gi>
                    <n-form-item-gi :span="8" :span-s="24" label="端口" path="port">
                        <n-input-number v-model:value="connectionForm.port" :min="1" :max="65535" placeholder="22" />
                    </n-form-item-gi>
                    <n-form-item-gi :span="8" :span-s="24" label="用户名" path="username">
                        <n-input v-model:value="connectionForm.username" placeholder="请输入用户名" />
                    </n-form-item-gi>
                    <n-form-item-gi :span="8" :span-s="24" label="密码" path="password">
                        <n-input v-model:value="connectionForm.password" type="password" show-password-on="click"
                            placeholder="请输入密码" />
                    </n-form-item-gi>
                </n-grid>
                <n-space>
                    <n-button type="primary" @click="handleConnect" :disabled="connected" :loading="connecting">
                        {{ connected ? '已连接' : '连接' }}
                    </n-button>
                    <n-button @click="handleDisconnect" :disabled="!connected" :loading="disconnecting">
                        断开连接
                    </n-button>
                </n-space>
            </n-form>
        </n-card>
        <!-- 当前路径和刷新按钮 -->
        <n-card v-if="connected" :bordered="false" size="small" segmented style="margin-top: 16px;">
            <n-space vertical :wrap="true">
                <n-input-group>
                    <n-input v-model:value="pathInput" @keyup.enter="handlePathEnter" style="flex: 1;" />
                    <n-button @click="goToPath" :loading="loadingDirectory" style="min-width: 60px;">
                        确认
                    </n-button>
                </n-input-group>
                <n-button size="small" @click="refreshDirectory" :loading="loadingDirectory" block>
                    <n-icon><refresh-icon /></n-icon>
                    刷新
                </n-button>
            </n-space>
        </n-card>
        <n-spin v-if="!connected" style="margin-top: 16px; margin-left: 16px;"></n-spin>
        <!-- 文件详情 -->
        <n-modal v-model:show="showFileInfo" style="max-width: 400px; overflow: auto;" preset="card" title="文件详情" 
            :bordered="false" size="small" segmented>
            <n-descriptions label-placement="left" bordered :column="1" v-if="selectedFile">
                <n-descriptions-item label="名称">
                    <n-text>{{ selectedFile.name }}</n-text>
                </n-descriptions-item>
                <n-descriptions-item label="路径">
                    <n-text code>{{ selectedFile.path }}</n-text>
                </n-descriptions-item>
                <n-descriptions-item label="类型">
                    <n-tag :type="selectedFile.is_directory ? 'success' : selectedFile.is_link ? 'warning' : 'info'">
                        {{ selectedFile.is_directory ? '目录' : selectedFile.is_link ? '链接' : '文件' }}
                    </n-tag>
                </n-descriptions-item>
                <n-descriptions-item label="大小" v-if="!selectedFile.is_directory">
                    <n-text>{{ formatFileSize(selectedFile.size) }}</n-text>
                </n-descriptions-item>
                <n-descriptions-item label="权限">
                    <n-text code>{{ selectedFile.permissions }}</n-text>
                </n-descriptions-item>
                <n-descriptions-item label="修改时间">
                    <n-text>{{ selectedFile.month }} {{ selectedFile.day }} {{ selectedFile.time_or_year }}</n-text>
                </n-descriptions-item>
            </n-descriptions>
            <template #footer>
                <n-space justify="end">
                    <n-button @click="showFileInfo = false" size="small">
                        关闭
                    </n-button>
                    <n-button v-if="selectedFile && !selectedFile.is_directory && !selectedFile.is_link"
                        @click="handleDownload(selectedFile.path)" type="primary" size="small">
                        下载
                    </n-button>
                </n-space>
            </template>
        </n-modal>

        <!-- 文件列表 -->
        <n-card v-if="connected" :bordered="false" size="small" segmented style="margin-top: 16px;">
            <n-spin :show="loadingDirectory">
                <n-data-table :columns="columns" :data="directoryContents" :pagination="false"
                    :row-key="(row) => row.name" virtual-scroll :max-height="mobileMaxHeight" 
                    :scroll-x="isMobile ? 100 : 800" />
            </n-spin>
        </n-card>


        <!-- 下载进度弹窗 -->
        <n-modal v-model:show="showProgressModal" preset="card" title="下载进度" style="width: 600px;">
            <n-progress type="line" :percentage="downloadProgress.percentage" :status="downloadProgress.status">
                <n-text>{{ downloadProgress.filename }}</n-text>
                <n-text>{{ formatFileSize(downloadProgress.downloaded) }} / {{ formatFileSize(downloadProgress.total)
                }}</n-text>
            </n-progress>
        </n-modal>
    </div>
</template>

<script setup>
import { FolderOutline, Refresh as RefreshIcon } from '@vicons/ionicons5'
import axios from 'axios'
import {
    NButton,
    NCard,
    NDataTable,
    NDescriptions,
    NDescriptionsItem,
    NForm,
    NFormItemGi,
    NGrid,
    NIcon,
    NInput,
    NInputGroup,
    NInputNumber,
    NModal,
    NProgress,
    NSpace,
    NSpin,
    NTag,
    NText,
    useMessage
} from 'naive-ui'
import { computed, h, onMounted, onUnmounted, reactive, ref } from 'vue'

// 定义 props
const props = defineProps({
    defaultHost: {
        type: String,
        default: '172.26.126.120'
    },
    defaultPort: {
        type: Number,
        default: 22
    },
    defaultUsername: {
        type: String,
        default: ''
    },
    defaultPassword: {
        type: String,
        default: ''
    },
    showInput: {
        type: Boolean,
        default: false
    },
    autoConnect: {
        type: Boolean,
        default: false
    }
})

// 消息提示
const message = useMessage()

// 连接表单数据
const connectionForm = reactive({
    host: props.defaultHost,
    port: props.defaultPort,
    username: props.defaultUsername,
    password: props.defaultPassword
})

// 验证规则
const connectionRules = {
    host: { required: true, message: '请输入主机地址', trigger: 'blur' },
    port: {
        validator: (rule, value) => {
            if (value === undefined || value === null || value === '') {
                return new Error('请输入端口号')
            }
            if (typeof value !== 'number') {
                return new Error('端口号必须是数字')
            }
            if (value < 1 || value > 65535) {
                return new Error('端口号应在1-65535之间')
            }
            return true
        },
        trigger: ['input', 'blur']
    },
    username: { required: true, message: '请输入用户名', trigger: 'blur' },
    password: { required: true, message: '请输入密码', trigger: 'blur' }
}

// 状态变量
const connected = ref(false)
const connecting = ref(false)
const disconnecting = ref(false)
const loadingDirectory = ref(false)
const sshId = ref('')
const currentPath = ref('.')
const pathInput = ref('.')
const directoryContents = ref([])
const showProgressModal = ref(false)
const downloadProgress = reactive({
    percentage: 0,
    downloaded: 0,
    total: 0,
    filename: '',
    status: 'info'
})

// 移动端适配
const isMobile = ref(window.innerWidth <= 768)
const mobileMaxHeight = computed(() => {
    return isMobile.value ? 400 : 450
})

// 文件详情
const selectedFile = ref(null)
const showFileInfo = ref(false)


// 表单引用
const formRef = ref(null)

// 处理连接
const handleConnect = async () => {
    if (props.showInput && !formRef.value.validate()) {
        message.error('请填写完整的连接信息')
        return
    }


    connecting.value = true
    try {
        const response = await axios.post('/agv/connect', {
            host: connectionForm.host,
            port: connectionForm.port,
            username: connectionForm.username,
            password: connectionForm.password
        })

        if (response.data.message === '连接成功') {
            sshId.value = response.data.id
            connected.value = true
            message.success('SSH连接成功')

            // 加载根目录
            await loadDirectory('/mnt')
        } else {
            message.error(response.data.message + ":" + response.data.error || '连接失败')
        }
    } catch (error) {
        message.error(error.response?.data?.message || error.message || '连接失败')
    } finally {
        connecting.value = false
    }

}

// 处理断开连接
const handleDisconnect = async () => {
    disconnecting.value = true
    try {
        const response = await axios.get(`/agv/disconnect?id=${sshId.value}`)
        if (response.data.message === '断开成功') {
            connected.value = false
            sshId.value = ''
            directoryContents.value = []
            currentPath.value = '.'
            message.success('SSH连接已断开')
        } else {
            message.error(response.data.error || '断开连接失败')
        }
        pathInput.value = '.';  // 重置路径输入框
    } catch (error) {
        message.error(error.response?.data?.error || error.message || '断开连接失败')
    } finally {
        disconnecting.value = false
    }
}

// 加载目录内容
const loadDirectory = async (path = '/mnt') => {
    loadingDirectory.value = true
    try {
        const response = await axios.post('/agv/list_dir', {
            id: sshId.value,
            path: path
        })

        if (response.data.success) {
            directoryContents.value = response.data.data.map(item => ({
                ...item,
                path: path === '.' ? item.name : `${path}/${item.name}`
            }))
            currentPath.value = path
            pathInput.value = path  // 同步到路径输入框
        } else {
            message.error(response.data.error || '加载目录失败')
        }
    } catch (error) {
        message.error(error.response?.data?.error || error.message || '加载目录失败')
    } finally {
        loadingDirectory.value = false
    }
}

// 刷新当前目录
const refreshDirectory = async () => {
    await loadDirectory(currentPath.value)
}

// 切换到上级目录
const goToParentDirectory = async () => {
    const pathParts = currentPath.value.split('/')
    if (pathParts.length <= 1) {
        await loadDirectory('.')
    } else {
        pathParts.pop()
        const newPath = pathParts.join('/') || '.'
        await loadDirectory(newPath)
    }
    pathInput.value = currentPath.value;  // 同步到路径输入框
}

// 处理路径输入回车事件
const handlePathEnter = async () => {
    await goToPath();
}

// 跳转到指定路径
const goToPath = async () => {
    await loadDirectory(pathInput.value);
}

// 列表列配置
const columns = computed(() => {
    const baseColumns = [
        {
            title: '名称',
            key: 'name',
            render(row) {
                if (row.is_directory) {
                    return h('span', {
                        style: { 
                            cursor: 'pointer', 
                            color: '#18a058', 
                            overflow: 'hidden', 
                            textOverflow: 'ellipsis', 
                            whiteSpace: 'nowrap'
                        },
                        onClick: () => {
                            loadDirectory(row.path);
                            pathInput.value = row.path;  // 更新路径输入框
                        }
                    }, [
                        h(NIcon, { component: FolderOutline }),
                        ' ',
                        row.name
                    ])
                } else if (row.is_link) {
                    return h('span', { 
                        style: { 
                            cursor: 'pointer', 
                            color: '#666',
                            overflow: 'hidden', 
                            textOverflow: 'ellipsis', 
                            whiteSpace: 'nowrap' 
                        } 
                    }, [
                        h('span', { style: { color: '#666' } }, '🔗 '),
                        row.name
                    ])
                } else {
                    return h('span', {
                        style: { 
                            cursor: 'pointer', 
                            color: '#2080f0',
                            overflow: 'hidden', 
                            textOverflow: 'ellipsis', 
                            whiteSpace: 'nowrap' 
                        },
                        onClick: () => showFileDetails(row)
                    }, [
                        h('span', { style: { color: '#2080f0' } }, '📄 '),
                        row.name
                    ])
                }
            }
        }
    ];

    // 在桌面端显示更多列
    if (!isMobile.value) {
        baseColumns.push(
            {
                title: '类型',
                key: 'type',
                width: 80,
                render(row) {
                    if (row.is_directory) return '目录'
                    if (row.is_link) return '链接'
                    return '文件'
                }
            },
            {
                title: '大小',
                key: 'size',
                width: 100,
                render(row) {
                    if (row.is_directory) return '-'
                    // 格式化文件大小
                    const size = row.size
                    if (size < 1024) return `${size} B`
                    if (size < 1024 * 1024) return `${(size / 1024).toFixed(2)} KB`
                    if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(2)} MB`
                    return `${(size / (1024 * 1024 * 1024)).toFixed(2)} GB`
                }
            },
            {
                title: '权限',
                key: 'permissions',
                width: 120
            },
            {
                title: '修改时间',
                key: 'time_or_year',
                width: 120,
                render(row) {
                    return `${row.month} ${row.day} ${row.time_or_year}`
                }
            }
        );
        
        // 桌面端的操作列
        baseColumns.push({
            title: '操作',
            key: 'actions',
            width: 100,
            render(row) {
                return h(NSpace, null, {
                    default: () => [
                        h(NButton, {
                            size: 'small',
                            type: 'primary',
                            secondary: true,
                            onClick: () => showFileDetails(row)
                        }, {
                            default: () => '详情'
                        })
                    ]
                })
            }
        });
    } else {
        // 移动端只显示操作列，减少列数以适应屏幕
        baseColumns.push({
            title: '操作',
            key: 'actions',
            width: 60,
            render(row) {
                return h(NSpace, null, {
                    default: () => [
                        h(NButton, {
                            size: 'tiny',
                            type: 'primary',
                            secondary: true,
                            onClick: () => showFileDetails(row)
                        }, {
                            default: () => '...'
                        })
                    ]
                })
            }
        });
    }


    return baseColumns;
});

// 显示文件详情
const showFileDetails = (file) => {
    selectedFile.value = file;
    showFileInfo.value = true;
}

// Format file size to human readable format
const formatFileSize = (bytes) => {
    if (typeof bytes !== 'number' || isNaN(bytes)) return '-';
    if (bytes === 0) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
};

// 处理文件下载
const handleDownload = async (filePath) => {
    try {
        // 初始化进度信息
        downloadProgress.filename = filePath.split('/').pop();
        downloadProgress.downloaded = 0;
        downloadProgress.total = 0;
        downloadProgress.percentage = 0;
        downloadProgress.status = 'info';
        showProgressModal.value = true;

        // 使用 XHR 进行下载，这样可以更好地处理错误和进度
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/agv/stream_download', true);
        xhr.setRequestHeader('Content-Type', 'application/json');

        // 设置响应类型为 blob
        xhr.responseType = 'blob';

        // 监听下载进度
        xhr.onprogress = function (event) {
            if (event.lengthComputable) {
                downloadProgress.total = event.total;
                downloadProgress.downloaded = event.loaded;
                downloadProgress.percentage = Math.round((event.loaded / event.total) * 100);
            } else {
                // 如果无法计算进度，显示已下载的字节数
                downloadProgress.downloaded = event.loaded;
            }
        };

        // 处理下载完成
        xhr.onload = function () {
            if (xhr.status === 200) {
                // 创建下载链接
                const blob = xhr.response;
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.setAttribute('download', filePath.split('/').pop());
                document.body.appendChild(link);
                link.click();
                link.remove();
                window.URL.revokeObjectURL(url);

                // 下载完成，更新进度条状态
                downloadProgress.percentage = 100;
                downloadProgress.status = 'success';
                message.success(`文件下载完成: ${filePath.split('/').pop()}`);

                // 关闭进度弹窗
                setTimeout(() => {
                    showProgressModal.value = false;
                }, 1000);
            } else {
                // 尝试读取错误响应
                const reader = new FileReader();
                reader.onload = function () {
                    try {
                        const errorObj = JSON.parse(reader.result);
                        message.error(errorObj.error || `下载失败: HTTP ${xhr.status}`);
                    } catch (e) {
                        message.error(`下载失败: HTTP ${xhr.status}`);
                    }
                };
                reader.readAsText(xhr.response);

                downloadProgress.status = 'error';
                setTimeout(() => {
                    showProgressModal.value = false;
                }, 1000);
            }
        };

        // 处理网络错误
        xhr.onerror = function () {
            message.error('网络错误，下载失败');
            downloadProgress.status = 'error';
            setTimeout(() => {
                showProgressModal.value = false;
            }, 1000);
        };

        // 发送请求数据
        xhr.send(JSON.stringify({
            id: sshId.value,
            filepath: filePath
        }));

    } catch (error) {
        showProgressModal.value = false;
        message.error(error.response?.data?.error || error.message || '下载失败');
        console.error('下载失败:', error);
    }
}

// 初始化时尝试连接
onMounted(() => {
    // 如果提供了默认连接信息，可以自动连接
    if (props.autoConnect) {
        handleConnect()
    }
    
    // 监听窗口大小变化
    window.addEventListener('resize', handleWindowResize);
})

// 监听窗口大小变化
const handleWindowResize = () => {
    isMobile.value = window.innerWidth <= 768
}

// 组件卸载时断开连接
onUnmounted(async () => {
    if (connected.value && sshId.value) {
        try {
            const response = await axios.get(`/agv/disconnect?id=${sshId.value}`)
            if (response.data.message === '断开成功') {
                console.log('SSH连接已自动断开')
                            message.info('SSH连接已自动断开')

            }
        } catch (error) {
            console.error('自动断开SSH连接时出错:', error)
                            message.error('自动断开SSH连接时出错')
        }
    }
    // 移除窗口大小变化监听器
    window.removeEventListener('resize', handleWindowResize);
})
</script>

<style scoped>
.ssh-container {
    padding: 0px;
}

.n-card {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* 移动端适配 */
@media (max-width: 768px) {
    .ssh-container {
        padding: 2px;
    }

    /* 优化表格在移动端的显示 */
    :deep(.n-data-table-td) {
        padding: 8px 4px !important;
    }

    :deep(.n-data-table-th) {
        padding: 8px 4px !important;
    }
}

/* 优化输入框在移动端的显示 */
@media (max-width: 480px) {
    :deep(.n-form-item-label) {
        white-space: nowrap;
        flex: none;
    }

    :deep(.n-input) {
        min-width: auto;
    }
}
</style>
