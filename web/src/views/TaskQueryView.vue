<script setup>
import TaskDisplayComponent from '@/components/TaskDisplayComponent.vue'
import { NButton, NCard, NCollapse, NCollapseItem, NDatePicker, NForm, NFormItem, NInput, NSelect, NSpin, useMessage } from 'naive-ui'
import { onMounted, reactive, ref, watch } from 'vue'

const message = useMessage()

// 展开状态
const isFormExpanded = ref(false)
// 折叠面板展开项
const expandedNames = ref([])

// 监听展开状态变化
watch(() => isFormExpanded.value, (newVal) => {
    expandedNames.value = newVal ? ['advancedParams'] : []
})

// 查询参数
const queryParams = reactive({
    robotCode: "",
    taskTyp: "",
    taskStatus: "", // 默认为空，让用户自己选择
    carrierId: "",
    podCode: "",
    ctnrCode: "",
    tranTaskNum: "",
    wbCode: "",
    uname: "",
    dstMapCode: "",
    groupNum: "",
    liftCode: "",
    srcEqName: "",
    desEqName: "",
    sdateTo: null,
    edateTo: null,
    limit: 20,
})

// 设置默认时间范围：昨天00:00:00 到 今天23:59:59
const setDefaultDateRange = () => {
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    
    // 设置开始时间为昨天00:00:00
    const startDate = new Date(yesterday)
    startDate.setHours(0, 0, 0, 0)
    
    // 设置结束时间为今天23:59:59
    const endDate = new Date(today)
    endDate.setHours(23, 59, 59, 999)
    
    // DatePicker expects timestamp in milliseconds
    queryParams.sdateTo = startDate.getTime()
    queryParams.edateTo = endDate.getTime()
}
const formatDate = (date) => {
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    const h = String(date.getHours()).padStart(2, '0')
    const min = String(date.getMinutes()).padStart(2, '0')
    const s = String(date.getSeconds()).padStart(2, '0')
    return `${y}-${m}-${d}+${h}:${min}:${s}`
}
// 查询结果
const queryResult = ref({
    total: 0,
    code: 0,
    data: [],
    success: false,
    count: 0
})

// 加载状态
const loading = ref(false)

// 错误信息
const error = ref('')

// 查询任务数据
const queryTasks = async () => {
    loading.value = true
    error.value = ''
    
    try {
        // 格式化日期为API需要的格式
        const formattedParams = {
            ...queryParams,
            sdateTo: queryParams.sdateTo ? new Date(queryParams.sdateTo).toISOString().slice(0, 19).replace('T', ' ') : null,
            edateTo: queryParams.edateTo ? new Date(queryParams.edateTo).toISOString().slice(0, 19).replace('T', ' ') : null
        }
        
        // 调用后端API，使用POST方法和JSON body
        const response = await fetch('/api/rcs_web/find_tasks_detail', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formattedParams)
        })
        const data = await response.json()
        
        if (data.success || data.code === 0) {
              queryResult.value = data
          } else {
              error.value = data.message || '查询失败'
          }
    } catch (e) {
        error.value = '网络错误：' + e.message
        console.error('查询任务失败：', e)
    } finally {
        loading.value = false
    }
}

// 重置查询参数
const resetParams = () => {
    for (const key in queryParams) {
        if (key === 'limit') {
            queryParams[key] = 20
        } else {
            queryParams[key] = ''
        }
    }
    // 清空日期选择器
    queryParams.sdateTo = null
    queryParams.edateTo = null
}

// 组件挂载时初始化
onMounted(() => {
    // 设置默认时间范围
    setDefaultDateRange()
    // 默认查询最近的任务
    queryTasks()
})
</script>

<template>
    <div class="task-query-container">
        <h3 class="task-query-title">任务查询</h3>

        <!-- 查询表单 -->
        <NCard class="task-query-form">
            <NForm>
                <!-- 固定显示的机器人代码查询项 -->
                <div class="form-row">
                    <NFormItem label="机器人代码" path="robotCode" style="flex: 1; margin-right: 15px;">
                        <NInput v-model:value="queryParams.robotCode" placeholder="请输入机器人代码" />
                    </NFormItem>
                </div>

                <!-- 可展开的查询参数 -->
                <NCollapse v-model:expanded-names="expandedNames" :default-expanded-names="[]">
                    <NCollapseItem name="advancedParams" title="高级查询">
                        <div class="form-row">
                            <NFormItem label="任务状态" path="taskStatus" style="flex: 1; margin-right: 15px;">
                                <NSelect v-model:value="queryParams.taskStatus" placeholder="全部">
                                    <option value="">全部</option>
                                    <option value="0">待分配</option>
                                    <option value="1">已分配</option>
                                    <option value="2">正在执行</option>
                                    <option value="3">执行完成</option>
                                    <option value="4">执行失败</option>
                                    <option value="5">已取消</option>
                                </NSelect>
                            </NFormItem>
                            <NFormItem label="任务类型" path="taskTyp" style="flex: 1;">
                                <NInput v-model:value="queryParams.taskTyp" placeholder="请输入任务类型" />
                            </NFormItem>
                        </div>

                        <div class="form-row">
                            <NFormItem label="载体ID" path="carrierId" style="flex: 1; margin-right: 15px;">
                                <NInput v-model:value="queryParams.carrierId" placeholder="请输入载体ID" />
                            </NFormItem>
                            <NFormItem label="工作站代码" path="wbCode" style="flex: 1;">
                                <NInput v-model:value="queryParams.wbCode" placeholder="请输入工作站代码" />
                            </NFormItem>
                        </div>

                        <div class="form-row">
                            <NFormItem label="用户名" path="uname" style="flex: 1; margin-right: 15px;">
                                <NInput v-model:value="queryParams.uname" placeholder="请输入用户名" />
                            </NFormItem>
                            <NFormItem label="任务号" path="tranTaskNum" style="flex: 1;">
                                <NInput v-model:value="queryParams.tranTaskNum" placeholder="请输入任务号" />
                            </NFormItem>
                        </div>

                        <div class="form-row">
                    <NFormItem label="开始时间" path="sdateTo" style="flex: 1; margin-right: 15px;">
                        <NDatePicker 
                            :value="queryParams.sdateTo"
                            @update:value="(value) => queryParams.sdateTo = value"
                            type="datetime"
                            placeholder="选择开始时间"
                        />
                    </NFormItem>
                    <NFormItem label="结束时间" path="edateTo" style="flex: 1;">
                        <NDatePicker 
                            :value="queryParams.edateTo"
                            @update:value="(value) => queryParams.edateTo = value"
                            type="datetime"
                            placeholder="选择结束时间"
                        />
                    </NFormItem>
                </div>

                        <div class="form-row">
                            <NFormItem label="每页数量" path="limit" style="flex: 1;">
                                <NSelect v-model:value="queryParams.limit" placeholder="20">
                                    <option value="20">20</option>
                                    <option value="50">50</option>
                                    <option value="100">100</option>
                                </NSelect>
                            </NFormItem>
                        </div>
                    </NCollapseItem>
                </NCollapse>

                <div class="form-actions">
                    <NButton type="primary" @click="queryTasks" :loading="loading" style="margin-right: 10px;">
                        查询
                    </NButton>
                    <NButton type="default" @click="resetParams" style="margin-right: 10px;">
                        重置
                    </NButton>
                    <NButton type="default" @click="isFormExpanded = !isFormExpanded">
                        {{ isFormExpanded ? '收起' : '展开' }}高级查询
                    </NButton>
                </div>
            </NForm>
        </NCard>

        <!-- 错误信息 -->
        <div v-if="error" class="error-message">
            {{ error }}
        </div>

        <!-- 查询结果 -->
        <NCard class="task-result-card">
            <div class="result-header">
                <span>共找到 {{ queryResult.total || queryResult.count || 0 }} 条记录</span>
            </div>
            <NSpin :show="loading">
                <TaskDisplayComponent :tasks="queryResult.data"/>
            </NSpin>
        </NCard>
    </div>
</template>

<style scoped>
.task-query-container {
    max-width: 100%;
    margin: 0;
    padding: 10px;
}

.task-query-title {
    font-size: 20px;
    font-weight: 600;
    margin-bottom: 20px;
    color: #333;
}

.task-query-form {
    margin-bottom: 20px;
}

.form-row {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 10px;
}

/* 在较小屏幕上进一步缩小间距 */
@media (max-width: 768px) {
    .form-row {
        gap: 8px;
        margin-bottom: 8px;
    }

    .form-actions {
        flex-direction: column;
        gap: 8px;
    }

    .form-actions .n-button {
        width: 100%;
    }
}

.form-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 15px;
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

/* 结果卡片样式 */
.task-result-card {
    margin-top: 20px;
}

.result-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
    font-size: 14px;
    color: #606266;
}

/* 响应式设计 */
@media (max-width: 768px) {
    .form-row {
        flex-direction: column;
    }

    .task-query-container {
        padding: 5px;
    }
}
</style>