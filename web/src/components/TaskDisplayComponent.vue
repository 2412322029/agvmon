<script setup>
import { NBadge, NButton, NCard, NH3, NModal, NSpin, NTable, NTag, useDialog, useMessage } from 'naive-ui';
import { computed, ref, watch } from 'vue';
import xmlFormat from 'xml-formatter';
const dialog = useDialog()
// Safe XML formatter that handles errors gracefully
const safeXmlFormat = (xmlString) => {
    if (!xmlString) return '';
    xmlString = xmlString.replace(/&#x27;/g, "'")
        .replace(/&quot;/g, '"')
        .replace(/&gt;/g, '>')
        .replace(/&lt;/g, '<')
        .replace(/&amp;/g, '&')
    try {
        return xmlFormat(xmlString, {
            collapseContent: true,
            indentation: '    ',
            lineSeparator: '\n'
        });
    } catch (error) {
        console.warn('XML formatting error:', error.message);
        // Return the original string if formatting fails, but with safe HTML escaping
        return xmlString;
    }
};
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
    taskStatus: {
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
const expandedTasks = ref(new Set())
const subTasksData = ref({})
const subTasksLoading = ref({})
const softCancelLoading = ref(false)

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
            error.value = data.message + ":" + data?.errors?.join(',') || '查询失败';
            message.error(error.value)
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

// 切换任务展开状态
const toggleExpand = async (task) => {
    const taskId = task.tranTaskNum || task.taskId
    // 实现展开互斥功能 - 同时只能有一个子任务展开
    if (expandedTasks.value.has(taskId)) {
        expandedTasks.value.delete(taskId)
    } else {
        // 清空之前展开的所有任务，确保只有一个任务展开
        expandedTasks.value.clear()
        expandedTasks.value.add(taskId)
        await loadSubTasks(taskId)
    }
}

// 加载子任务数据
const loadSubTasks = async (taskId) => {
    subTasksLoading.value[taskId] = true

    try {
        const response = await fetch('/api/rcs_web/find_sub_tasks_detail', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                trans_task_num: taskId,
                search_year: 2020,
                show_his_data: "false"
            })
        })

        const data = await response.json()

        if (data.success) {
            subTasksData.value[taskId] = data.data || []
        } else {
            message.error(data.message + ":" + data?.errors?.join(',') || '获取子任务失败')
            subTasksData.value[taskId] = []
        }
    } catch (e) {
        console.error('获取子任务失败：', e)
        message.error('网络错误：' + e.message)
        subTasksData.value[taskId] = []
    } finally {
        subTasksLoading.value[taskId] = false
    }
}

// 检查任务是否已展开
const isExpanded = (task) => {
    const taskId = task.tranTaskNum || task.taskId
    return expandedTasks.value.has(taskId)
}

// 显示子任务详情
const showSubTaskDetail = (subTask) => {
    selectedTask.value = subTask
    showModal.value = true
}

// 获取子任务状态对应的标签类型
const getSubTaskStatusType = (status) => {
    const typeMap = {
        '1': 'info',     // 已创建
        '2': 'success',  // 正在执行
        '9': 'default',  // 已结束
        '4': 'error',    // 执行失败
        '5': 'warning'   // 已取消
    }
    return typeMap[status] || 'default'
}

// 检查任务是否可以软取消
const checkSoftCancel = async (taskId) => {
    try {
        const response = await fetch('/api/rcs_web/check_soft_cancel', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                trans_task_nums: taskId
            })
        });
        const data = await response.json();
        return data;
    } catch (e) {
        console.error('检查软取消状态失败：', e);
        message.error('网络错误：' + e.message);
        return null;
    }
};

// 检查任务是否正在滚动
const checkIsRolling = async (taskId) => {
    try {
        const response = await fetch('/api/rcs_web/check_is_rolling', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                trans_task_nums: taskId
            })
        });
        const data = await response.json();
        return data;
    } catch (e) {
        console.error('检查任务滚动状态失败：', e);
        message.error('网络错误：' + e.message);
        return null;
    }
};

// 检查开始传输任务
const checkStartingTransTasks = async (taskId) => {
    try {
        const response = await fetch('/api/rcs_web/check_starting_trans_tasks', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                trans_task_nums: taskId
            })
        });
        const data = await response.json();
        return data;
    } catch (e) {
        console.error('检查开始传输任务失败：', e);
        message.error('网络错误：' + e.message);
        return null;
    }
};

// 取消传输任务
const cancelTransTasks = async (taskId) => {
    try {
        const response = await fetch('/api/rcs_web/cancel_trans_tasks', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                trans_task_nums: taskId,
                cancel_type: "0",
                cancel_reason: "2"
            })
        });
        const data = await response.json();
        return data;
    } catch (e) {
        console.error('取消传输任务失败：', e);
        message.error('网络错误：' + e.message);
        return null;
    }
};

// 执行软取消操作
const performSoftCancel = async () => {
    softCancelLoading.value = true
    if (!selectedTask.value) {
        message.warning('请选择一个任务');
        softCancelLoading.value = false
        return;
    }

    const taskId = selectedTask.value.tranTaskNum || selectedTask.value.taskId;
    if (!taskId) {
        message.warning('任务ID不存在');
        softCancelLoading.value = false
        return;
    }
    try {
        // 检查任务是否正在滚动
        const checkResult = await checkIsRolling(taskId);
        dialog.info({
            title: 'checkIsRolling',
            content: JSON.stringify(checkResult),
            positiveText: '确定',
            negativeText: '取消',
            draggable: true,
            onPositiveClick: async () => {
                message.success('确定')
                // 先检查是否可以软取消
                const rollingResult = await checkSoftCancel(taskId);
                dialog.info({
                    title: 'checkSoftCancel',
                    content: JSON.stringify(rollingResult),
                    positiveText: '确定',
                    negativeText: '取消',
                    draggable: true,
                    onPositiveClick: async () => {
                        message.success('确定')
                        // 检查是否是开始传输任务
                        const startingResult = await checkStartingTransTasks(taskId);
                        dialog.info({
                            title: 'checkStartingTransTasks',
                            content: JSON.stringify(startingResult),
                            positiveText: '确定',
                            negativeText: '取消',
                            draggable: true,
                            onPositiveClick: async () => {
                                message.success('确定')
                                // 执行取消操作
                                const cancelResult = await cancelTransTasks(taskId);
                                if (cancelResult && cancelResult.success) {
                                    message.success('任务软取消成功');
                                    // 关闭模态框
                                    showModal.value = false;
                                    // 刷新任务列表
                                    if (props.robotCode) {
                                        queryTasksByRobotCode();
                                    }
                                } else {
                                    message.error(cancelResult?.message || '任务取消失败');
                                }
                            },
                            onNegativeClick: () => {
                                message.error('取消')
                            }
                        })
                    },
                    onNegativeClick: () => {
                        message.error('取消')
                    }
                })
            },
            onNegativeClick: () => {
                message.error('取消')
            }
        })
    } catch (e) {
        console.error('执行软取消操作失败：', e);
        message.error('网络错误：' + e.message);
        softCancelLoading.value = false
    } finally {
        softCancelLoading.value = false
    }


};

</script>

<template>
    <div class="task-display-container">
        <NSpin :show="loading">
            <NTable v-if="displayTasks.length > 0" :bordered="true" :single-line="false" :striped="true">
                <thead>
                    <tr>
                        <!-- <th width="50"></th> -->
                        <th>任务类型</th>
                        <th>机器人</th>
                        <th>任务状态</th>
                    </tr>
                </thead>
                <tbody>
                    <template v-for="task in displayTasks" :key="task.tranTaskNum || task.taskId || $index">
                        <tr>
                            <td>
                                <span @click="toggleExpand(task)"
                                    :class="['expand-toggle', isExpanded(task) ? 'expanded' : 'collapsed']"
                                    style="cursor: pointer; display: inline-block; padding: 4px 8px;">
                                    {{ isExpanded(task) ? '▼' : '▶' }}
                                </span>
                                {{ task.taskTyp || '-' }}
                            </td>
                            <td>{{ task.robotCode || '-' }}</td>
                            <td>
                                <NBadge :type="getStatusType(task.taskStatus?.toString())"
                                    :value="task.taskStatusStr || getTaskStatusText(task.taskStatus?.toString())" round
                                    @click="showTaskDetail(task)" style="cursor: pointer;" />
                            </td>
                        </tr>

                        <!-- 子任务行 (嵌套在主任务行内) -->
                        <tr v-show="isExpanded(task)">
                            <td colspan="4" class="sub-task-cell">
                                <div class="sub-task-expanded">
                                    <NCard size="small" :bordered="false" class="sub-task-card">
                                        <template #header>
                                            <NH3 prefix="bar" style="margin: 0;">子任务流程</NH3>
                                        </template>

                                        <NSpin :show="subTasksLoading[task.tranTaskNum || task.taskId || '']">
                                            <div v-if="subTasksData[task.tranTaskNum || task.taskId || '']?.length"
                                                class="vertical-timeline">
                                                <div v-for="(subTask, index) in subTasksData[task.tranTaskNum || task.taskId || '']"
                                                    :key="index" class="timeline-item-vertical"
                                                    @click="showSubTaskDetail(subTask)">
                                                    <div class="timeline-content-vertical">
                                                        <div class="task-seq"></div>
                                                        <div class="task-type">#{{ subTask.subTaskSeq || index + 1 }} {{
                                                            subTask.subTaskTyp || '未知任务' }} <NTag
                                                                :type="getSubTaskStatusType(subTask.taskStatus)"
                                                                size="small">
                                                                {{ subTask.taskStatusStr ||
                                                                    getTaskStatusText(subTask.taskStatus) }}
                                                            </NTag>
                                                        </div>

                                                        <div class="task-num">{{ subTask.subTaskNum || '' }}</div>
                                                    </div>
                                                </div>
                                            </div>

                                            <div v-else class="no-sub-tasks">
                                                暂无子任务数据
                                            </div>
                                        </NSpin>
                                    </NCard>
                                </div>
                            </td>
                        </tr>
                    </template>
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
        <NModal v-model:show="showModal" :mask-closable="true" :close-on-esc="true" preset="card"
            :title="selectedTask?.subTaskNum ? '子任务详情' : '任务详情'"
            :style="{ width: '90%', maxWidth: '840px', maxHeight: '80vh' }">
            <div v-if="selectedTask" class="task-detail-content">
                <div class="detail-grid">
                    <!-- 主任务特有字段 -->
                    <div v-if="!selectedTask.subTaskNum" class="detail-item">
                        <div class="detail-label">任务ID:</div>
                        <div class="detail-value">{{ selectedTask.tranTaskNum || selectedTask.taskId || '-' }}</div>
                    </div>
                    <div v-if="!selectedTask.subTaskNum" class="detail-item">
                        <div class="detail-label">任务类型:</div>
                        <div class="detail-value">{{ selectedTask.taskTyp || '-' }}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">任务状态:</div>
                        <div class="detail-value">
                            <NBadge :type="getStatusType(selectedTask.taskStatus?.toString())"
                                :value="selectedTask.taskStatusStr || getTaskStatusText(selectedTask.taskStatus?.toString())"
                                round />
                        </div>
                    </div>

                    <!-- 主任务特有字段 -->
                    <div v-if="!selectedTask.subTaskNum" class="detail-item">
                        <div class="detail-label">载体ID:</div>
                        <div class="detail-value">{{ selectedTask.carrierId || '-' }}</div>
                    </div>

                    <div v-if="!selectedTask.subTaskNum" class="detail-item">
                        <div class="detail-label">源设备名称:</div>
                        <div class="detail-value">{{ selectedTask.srcEqName || '-' }}</div>
                    </div>
                    <div v-if="!selectedTask.subTaskNum" class="detail-item">
                        <div class="detail-label">目标设备名称:</div>
                        <div class="detail-value">{{ selectedTask.desEqName || '-' }}</div>
                    </div>
                    <div v-if="!selectedTask.subTaskNum" class="detail-item">
                        <div class="detail-label">用户呼叫码:</div>
                        <div class="detail-value">{{ selectedTask.userCallCode || '-' }}</div>
                    </div>
                    <div v-if="!selectedTask.subTaskNum" class="detail-item">
                        <div class="detail-label">用户名:</div>
                        <div class="detail-value">{{ selectedTask.uname || '-' }}</div>
                    </div>
                    <div v-if="!selectedTask.subTaskNum" class="detail-item">
                        <div class="detail-label">upDown:</div>
                        <div class="detail-value">{{ selectedTask.upDown || '-' }}</div>
                    </div>
                    <div v-if="!selectedTask.subTaskNum" class="detail-item">
                        <div class="detail-label">工作站代码:</div>
                        <div class="detail-value">{{ selectedTask.wbCode || '-' }}</div>
                    </div>
                    <div v-if="!selectedTask.subTaskNum" class="detail-item">
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

                    <!-- 子任务特有字段 -->
                    <div v-if="selectedTask.subTaskNum" class="detail-item">
                        <div class="detail-label">子任务编号:</div>
                        <div class="detail-value">{{ selectedTask.subTaskNum || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.subTaskNum" class="detail-item">
                        <div class="detail-label">子任务序号:</div>
                        <div class="detail-value">{{ selectedTask.subTaskSeq || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.mainTaskNum" class="detail-item">
                        <div class="detail-label">主任务编号:</div>
                        <div class="detail-value">{{ selectedTask.mainTaskNum || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.mapCode" class="detail-item">
                        <div class="detail-label">chgRobDate:</div>
                        <div class="detail-value">{{ selectedTask.chgRobDate || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.startX !== undefined" class="detail-item">
                        <div class="detail-label">起点X坐标:</div>
                        <div class="detail-value">{{ selectedTask.startX || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.startY !== undefined" class="detail-item">
                        <div class="detail-label">起点Y坐标:</div>
                        <div class="detail-value">{{ selectedTask.startY || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.endX !== undefined" class="detail-item">
                        <div class="detail-label">终点X坐标:</div>
                        <div class="detail-value">{{ selectedTask.endX || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.endY !== undefined" class="detail-item">
                        <div class="detail-label">终点Y坐标:</div>
                        <div class="detail-value">{{ selectedTask.endY || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.podTyp" class="detail-item">
                        <div class="detail-label">Pod类型:</div>
                        <div class="detail-value">{{ selectedTask.podTyp || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.priority" class="detail-item">
                        <div class="detail-label">优先级:</div>
                        <div class="detail-value">{{ selectedTask.priority || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.groupFlag !== undefined" class="detail-item">
                        <div class="detail-label">组标志:</div>
                        <div class="detail-value">{{ selectedTask.groupFlag || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.needConfirm" class="detail-item">
                        <div class="detail-label">需要确认:</div>
                        <div class="detail-value">{{ selectedTask.needConfirm || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.needTrigger" class="detail-item">
                        <div class="detail-label">需要触发:</div>
                        <div class="detail-value">{{ selectedTask.needTrigger || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.loopExec" class="detail-item">
                        <div class="detail-label">循环执行:</div>
                        <div class="detail-value">{{ selectedTask.loopExec || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.thirdTyp" class="detail-item">
                        <div class="detail-label">第三方类型:</div>
                        <div class="detail-value">{{ selectedTask.thirdTyp || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.thirdMethod" class="detail-item">
                        <div class="detail-label">第三方方法:</div>
                        <div class="detail-value">{{ selectedTask.thirdMethod || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.thirdUrl" class="detail-item">
                        <div class="detail-label">第三方URL:</div>
                        <div class="detail-value">{{ selectedTask.thirdUrl || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.wbCodeName" class="detail-item">
                        <div class="detail-label">工作台名称:</div>
                        <div class="detail-value">{{ selectedTask.wbCodeName || '-' }}</div>
                    </div>

                    <div v-if="selectedTask.dstMapCode" class="detail-item">
                        <div class="detail-label">via:</div>
                        <div class="detail-value">{{ selectedTask.via || '-' }}</div>
                    </div>
                    <div v-if="selectedTask.taskTypCode" class="detail-item">
                        <div class="detail-label">任务类型代码:</div>
                        <div class="detail-value">{{ selectedTask.taskTypCode || '-' }}</div>
                    </div>
                    <!-- 任务消息字段 -->
                    <div v-if="selectedTask.taskMsg" class="detail-item full-width">
                        <div class="detail-label">任务消息:</div>
                        <div class="detail-value xml-content">
                            <pre class="xml-pre"><code>{{ safeXmlFormat(selectedTask.taskMsg || '') }}</code></pre>
                        </div>
                    </div>
                    <!-- 添加软取消按钮 -->
                    <div v-if="!selectedTask?.subTaskNum && selectedTask" class="soft-cancel-button detail-item">
                        <n-button type="warning" @click="performSoftCancel"
                            :disabled="selectedTask?.taskStatus === '3' || selectedTask?.taskStatus === '5' || softCancelLoading"
                            :loading="softCancelLoading" style="margin: 2px;">
                            {{ softCancelLoading ? '取消中...' : '软取消任务' }}
                        </n-button>
                    </div>
                </div>

            </div>
        </NModal>
    </div>
</template>

<style scoped>
.expand-toggle.expanded {
    color: #f56c6c;
    /* 蓝色表示已展开 */
    transform: rotate(0deg);
    /* 确保箭头向下 */
}

.expand-toggle.collapsed {
    color: #999;
    /* 灰色表示未展开 */
    transform: rotate(0deg);
    /* 确保箭头向右 */
}



.task-display-container {
    width: 100%;
    margin-bottom: 20px;
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

.detail-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 15px;
}

/* 在较小屏幕上进一步缩小详情网格 */
@media (max-width: 768px) {
    .detail-grid {
        grid-template-columns: 1fr;
        gap: 10px;
    }

    .detail-label,
    .detail-value {
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

.sub-task-cell {
    padding: 0 !important;
    background-color: #f9f9f9;
}

.sub-task-expanded {
    margin-top: -1px;
    /* Reduce space between main task and subtasks */
}

.sub-task-card {
    margin: 0;
    border-radius: 0;
    border-left: none;
    border-right: none;
    border-bottom: none;
}

.no-sub-tasks {
    text-align: center;
    color: #909399;
    padding: 20px 0;
    font-style: italic;
}

/* 垂直时间线样式 */
.vertical-timeline {
    display: flex;
    flex-direction: column;
    padding: 10px 0;
    gap: 10px;
}

.timeline-item-vertical {
    display: flex;
    flex-direction: column;
    background: #fff;
    border: 1px solid #e4e7ed;
    border-radius: 4px;
    padding: 10px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    cursor: pointer;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    position: relative;
}

.timeline-item-vertical:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}

.timeline-content-vertical {
    text-align: left;
    width: 100%;
}

.task-seq {
    font-weight: bold;
    color: #409eff;
    margin-bottom: 3px;
    font-size: 14px;
}

.task-type {
    font-weight: 550;
    margin-bottom: 5px;
    color: #303133;
}

.task-num {
    font-size: 12px;
    color: #909399;
    margin-top: 3px;
}

.timeline-connector-vertical {
    position: relative;
    height: 20px;
}

.timeline-connector-vertical::before {
    content: '';
    position: absolute;
    top: -10px;
    left: 50%;
    transform: translateX(-50%);
    width: 2px;
    height: 20px;
    background-color: #dcdfe6;
}

.task-detail-content {
    overflow-y: auto;
    max-height: 70vh;
}

/* 任务消息XML显示样式 */
.full-width {
    grid-column: 1 / -1;
    /* 占据整行 */
}

.xml-content {
    background-color: #f8f8f8;
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 10px;
    /* max-height: 300px; */
    overflow: auto;
    width: 90%;
}

.xml-pre {
    white-space: pre-wrap;
    word-wrap: break-word;
    margin: 0;
    /* min-width: 410px; */
    font-family: 'Monaco', 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    line-height: 1.4;
    color: #333;
    tab-size: 4;
    /* 确保tab缩进正确显示 */
}

.xml-pre code {
    font-family: 'Monaco', 'Consolas', 'Courier New', monospace;
    line-height: 1.4;
}

.soft-cancel-button {
    display: flex;
    flex-direction: row;
    align-items: center;
}
</style>