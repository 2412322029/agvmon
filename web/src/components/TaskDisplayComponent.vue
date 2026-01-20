<script setup>
import { NBadge, NModal, NSpin, NTable, useMessage } from 'naive-ui'
import { computed, ref, watch } from 'vue'

const props = defineProps({
    tasks: {
        type: Array,
        default: () => []
    },
    robotCode: {
        type: String,
        default: ''
    },
    showQueryParams: {
        type: Boolean,
        default: true
    },
    showDetails: {
        type: Boolean,
        default: true
    },
    taskStatus:{
        type: Number,
        default: 2
    }
})

const message = useMessage()
const loading = ref(false)
const error = ref("")
const internalTasks = ref([])
const selectedTask = ref(null)
const showModal = ref(false)

// 计算最终显示的任务数据 - 优先使用外部传入的tasks，否则使用内部查询的结果
const displayTasks = computed(() => {
    if (props.tasks && Array.isArray(props.tasks) && props.tasks.length > 0) {
        return props.tasks;
    }
    if (internalTasks.value && Array.isArray(internalTasks.value)) {
        return internalTasks.value;
    }
    return [];
})

// 根据机器人代码查询任务
const queryTasksByRobotCode = async () => {
    if (!props.robotCode) {
        internalTasks.value = [];
        return;
    }

    loading.value = true;
    error.value = '';

    try {
        // 构建查询参数
        const queryParams = {
            robotCode: props.robotCode,
            taskStatus: props.taskStatus,
            limit: 20  // 限制返回数量
        };

        // 调用后端API，使用POST方法和JSON body
        const response = await fetch('/api/rcs_web/find_tasks_detail', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(queryParams)
        });
        const data = await response.json();

        if (data.success || data.code === 0) {
            internalTasks.value = data.data || [];
        } else {
            error.value = data.message || '查询失败';
            internalTasks.value = [];
        }
    } catch (e) {
        error.value = '网络错误：' + e.message;
        console.error('查询任务失败：', e);
        internalTasks.value = [];
    } finally {
        loading.value = false;
    }
};

// 当机器人代码变化时，自动查询任务
watch(() => props.robotCode, (newRobotCode) => {
    if (newRobotCode) {
        queryTasksByRobotCode();
    } else {
        internalTasks.value = [];
    }
}, { immediate: true });

// 任务状态映射
const taskStatusMap = {
    '0': '待分配',
    '1': '已分配',
    '2': '正在执行',
    '3': '执行完成',
    '4': '执行失败',
    '5': '已取消'
}

// 获取任务状态文本
const getTaskStatusText = (status) => {
    return taskStatusMap[status] || status
}

// 获取任务状态对应的标签类型
const getStatusType = (status) => {
    const typeMap = {
        '0': 'warning',  // 待分配
        '1': 'info',     // 已分配
        '2': 'success',  // 正在执行
        '3': 'default',  // 执行完成
        '4': 'error',    // 执行失败
        '5': 'default'   // 已取消
    }
    return typeMap[status] || 'default'
}

// 显示任务详情
const showTaskDetail = (task) => {
    selectedTask.value = task
    showModal.value = true
}


</script>

<template>
    <div class="task-display-container">
        <NSpin :show="loading">
            <NTable 
                v-if="displayTasks.length > 0"
                :bordered="true"
                :single-line="false"
                :striped="true"
            >
                <thead>
                    <tr>
                        <th>任务类型</th>
                        <th>robot</th>
                        <th>任务状态</th>
                    </tr>
                </thead>
                <tbody>
                    <tr 
                        v-for="task in displayTasks" 
                        :key="task.tranTaskNum || task.taskId || $index"
                    >
                        <td>{{ task.taskTyp || '-' }}</td>
                        <td>{{ task.robotCode || '-' }}</td>
                        <td>
                            <NBadge
                                :type="getStatusType(task.taskStatus?.toString())"
                                :value="task.taskStatusStr || getTaskStatusText(task.taskStatus?.toString())"
                                round
                                @click="showTaskDetail(task)"
                            />
                        </td>
                    </tr>
                </tbody>
            </NTable>
            
            <div v-else class="empty-result">
                没有找到匹配的记录
            </div>
        </NSpin>
        
        <!-- 错误信息 -->
        <div v-if="error" class="error-message">
            {{ error }}
        </div>
        
        <!-- 任务详情模态框 -->
        <NModal 
            v-model:show="showModal" 
            :mask-closable="true"
            :close-on-esc="true"
            preset="card"
            title="任务详情"
            :style="{ width: '90%', maxWidth: '800px' }"
        >
            <div v-if="selectedTask" class="task-detail-content">
                <div class="detail-grid">
                    <div class="detail-item">
                        <div class="detail-label">任务ID:</div>
                        <div class="detail-value">{{ selectedTask.tranTaskNum || selectedTask.taskId || '-' }}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">任务类型:</div>
                        <div class="detail-value">{{ selectedTask.taskTyp || '-' }}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">任务状态:</div>
                        <div class="detail-value">
                            <NBadge
                                :type="getStatusType(selectedTask.taskStatus?.toString())"
                                :value="selectedTask.taskStatusStr || getTaskStatusText(selectedTask.taskStatus?.toString())"
                                round
                            />
                        </div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">载体ID:</div>
                        <div class="detail-value">{{ selectedTask.carrierId || '-' }}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">载体位置:</div>
                        <div class="detail-value">{{ selectedTask.carrierLoc || '-' }}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">源设备名称:</div>
                        <div class="detail-value">{{ selectedTask.srcEqName || '-' }}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">目标设备名称:</div>
                        <div class="detail-value">{{ selectedTask.desEqName || '-' }}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">用户呼叫码:</div>
                        <div class="detail-value">{{ selectedTask.userCallCode || '-' }}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">用户名:</div>
                        <div class="detail-value">{{ selectedTask.uname || '-' }}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">工作站代码:</div>
                        <div class="detail-value">{{ selectedTask.wbCode || '-' }}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">容器代码:</div>
                        <div class="detail-value">{{ selectedTask.ctnrCode || '-' }}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">机器人代码:</div>
                        <div class="detail-value">{{ selectedTask.robotCode || '-' }}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">创建时间:</div>
                        <div class="detail-value">{{ selectedTask.dateCr || '-' }}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">修改时间:</div>
                        <div class="detail-value">{{ selectedTask.dateChg || '-' }}</div>
                    </div>
                </div>
            </div>
        </NModal>
    </div>
</template>

<style scoped>
.task-display-container {
    width: 100%;
    margin-bottom: 20px;
}

.result-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
    font-size: 14px;
    color: #606266;
}

.empty-result {
    text-align: center;
    padding: 50px 0;
    color: #909399;
    font-size: 14px;
}

.error-message {
    background-color: #fef0f0;
    border: 1px solid #fbc4c4;
    color: #f56c6c;
    padding: 10px 15px;
    border-radius: 4px;
    margin-bottom: 20px;
    font-size: 14px;
}

.task-details {
    padding: 15px;
    background-color: #fafafa;
    border-radius: 4px;
}

.detail-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
}

/* 在较小屏幕上进一步缩小详情网格 */
@media (max-width: 768px) {
    .detail-grid {
        grid-template-columns: 1fr;
        gap: 10px;
    }
    
    .detail-label, .detail-value {
        font-size: 12px;
    }
}

.detail-item {
    display: flex;
    flex-direction: column;
}

.detail-label {
    font-weight: 500;
    color: #606266;
    font-size: 13px;
    margin-bottom: 4px;
}

.detail-value {
    color: #303133;
    font-size: 14px;
    word-break: break-all;
}
</style>