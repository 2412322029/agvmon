<template>
  <div class="exception-records-container">
    <n-card title="异常记录管理" :bordered="false">
      <template #header-extra>
        <div class="header-actions">
          <n-space :vertical="isMobileView" :size="isMobileView ? 8 : 12">
            <div style="display: flex;">
              <n-popover trigger="click" placement="bottom-end" :show-arrow="false">
                <template #trigger>
                  <n-button type="primary" secondary size="small">
                    导出
                  </n-button>
                </template>
                <n-card title="导出选项" size="small" style="width: 240px;">
                  <div style="margin-bottom: 12px;">
                    <n-text>文本导出选项：</n-text>
                  </div>
                  <n-form label-placement="left" :label-width="80">
                    <n-form-item label="包含时间">
                      <n-switch v-model:value="includeTimeInExport" />
                    </n-form-item>
                    <n-form-item label="包含备注">
                      <n-switch v-model:value="includeRemarksInExport" />
                    </n-form-item>
                  </n-form>
                  <n-space vertical style="width: 100%; margin-top: 12px;">
                    <n-button @click="exportToText" type="primary" block>
                      导出文本
                    </n-button>
                    <n-button @click="exportToCSV" type="info" block>
                      导出CSV（全部字段）
                    </n-button>
                  </n-space>
                </n-card>
              </n-popover>
              <n-upload :show-download-button="false" :max="1" :on-before-upload="beforeImport" accept=".csv,.txt"
                style="margin-left: 8px;">
                <n-button type="tertiary" size="small">
                  导入
                </n-button>
              </n-upload>
            </div>
            <!-- <n-button type="primary" size="small" @click="showAddModal = true">
              添加
            </n-button> -->
          </n-space>
        </div>
      </template>

      <!-- 文本导出预览模态框 -->
      <n-modal v-model:show="showPreviewModal" preset="card" style="width: 800px;" title="导出文本预览">
        <n-card title="预览内容" size="small" embedded>
          <pre
            style="white-space: pre-wrap; word-break: break-all; max-height: 400px; overflow-y: auto; margin: 0; padding: 10px; background-color: #f5f5f5; border-radius: 4px;">
      {{ previewContent }}</pre>
        </n-card>
        <template #footer>
          <n-space justify="end">
            <n-button @click="showPreviewModal = false">取消</n-button>
            <n-button @click="copyToClipboard" type="primary">复制内容</n-button>
          </n-space>
        </template>
      </n-modal>

      <!-- 查询条件 -->
      <n-form :model="searchForm" :inline="!isMobileView" :label-width="isMobileView ? 70 : 80"
        style="margin-bottom: 2px;">
        <n-form-item label="小车ID" :show-feedback="false">
          <n-input v-model:value="searchForm.agv_id" placeholder="请输入小车ID" />
        </n-form-item>
        <n-form-item label="关键词" :show-feedback="false">
          <n-input v-model:value="searchForm.keyword" placeholder="问题描述或备注" />
        </n-form-item>
        <n-form-item label="状态" :show-feedback="false">
          <n-input v-model:value="searchForm.agv_status" placeholder="小车状态" />
        </n-form-item>
        <n-form-item label="日期范围" :show-feedback="false">
          <n-date-picker v-model:value="dateRange" type="daterange" :separator="'至'" format="yyyy-MM-dd"
            value-format="yyyy-MM-dd" />
        </n-form-item>
        <n-form-item :show-label="false" :style="isMobileView ? 'margin-top: 12px;' : 'margin-left: 8px;'"
          style="flex-wrap: nowrap;">
          <n-space :horizontal="!isMobileView" :size="8" :align="isMobileView ? 'stretch' : 'flex-start'"
            style="width: 100%;">
            <n-button type="primary" @click="searchRecords" :loading="loading" :block="isMobileView">
              查询
            </n-button>
            <n-button @click="resetSearch" :block="isMobileView">
              重置
            </n-button>
          </n-space>
        </n-form-item>
      </n-form>

      <!-- 数据表格 -->
      <n-data-table :columns="columns" :data="tableData" :loading="loading" :pagination="pagination" :bordered="false"
        size="small" :pagination-props="paginationProps" :scroll-x="isMobileView ? 800 : undefined" />

      <!-- 添加/编辑异常记录模态框 -->
      <n-modal v-model:show="showAddModal" :mask-closable="false" preset="card" style="width: 600px;" title="添加异常记录">
        <n-form :model="formModel" :rules="formRules" ref="formRef">
          <n-form-item label="小车ID" path="agv_id">
            <n-input v-model:value="formModel.agv_id" placeholder="请输入小车ID" />
          </n-form-item>
          <n-form-item label="问题描述" path="problem_description">
            <n-input v-model:value="formModel.problem_description" placeholder="请输入问题描述" type="textarea"
              :autosize="{ minRows: 3, maxRows: 5 }" />
          </n-form-item>
          <n-form-item label="小车状态" path="agv_status">
            <n-input v-model:value="formModel.agv_status" placeholder="请输入小车状态" />
          </n-form-item>
          <n-form-item label="备注">
            <n-input v-model:value="formModel.remarks" placeholder="请输入备注" type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }" />
          </n-form-item>
        </n-form>
        <template #footer>
          <n-space justify="end">
            <n-button @click="showAddModal = false">取消</n-button>
            <n-button type="primary" @click="submitForm" :loading="formSubmitting">
              提交
            </n-button>
          </n-space>
        </template>
      </n-modal>
    </n-card>
  </div>
</template>

<script setup>
import { NButton, NCard, NDataTable, NText, NDatePicker, NForm, NFormItem, NInput, NModal, NPopconfirm, NPopover, NSpace, NSwitch, NUpload, useMessage } from 'naive-ui'
import { h, onMounted, ref } from 'vue'

const message = useMessage()

// 检测是否为移动设备视图
const isMobileView = ref(window.innerWidth < 768)

// 更新窗口大小检测函数
const updateIsMobileView = () => {
  isMobileView.value = window.innerWidth < 768
}

// 表格数据
const tableData = ref([])
const loading = ref(false)
const formSubmitting = ref(false)

// 模态框控制
const showAddModal = ref(false)
const showPreviewModal = ref(false)
const previewContent = ref('')

// 导出选项
const includeTimeInExport = ref(true)
const includeRemarksInExport = ref(false)

// 查询条件
const searchForm = ref({
  agv_id: '',
  keyword: '',
  agv_status: '',
  start_date: '',
  end_date: ''
})

// 日期范围
const dateRange = ref(null)

// 表单数据
const formModel = ref({
  id: null,
  agv_id: '',
  problem_description: '',
  agv_status: '',
  remarks: ''
})

// 分页配置
const pagination = ref({
  page: 1,
  pageSize: 10,
  itemCount: 0,
  showSizePicker: true,
  pageSizes: [10, 20, 50],
  onUpdatePage: (page) => {
    pagination.value.page = page
    fetchData()
  },
  onUpdatePageSize: (pageSize) => {
    pagination.value.pageSize = pageSize
    pagination.value.page = 1
    fetchData()
  }
})

// 分页属性配置（用于中文本地化）
const paginationProps = {
  showQuickJumper: !isMobileView.value,
  showSizePicker: !isMobileView.value,
  pageSizes: [10, 20, 50],
  itemCount: pagination.value.itemCount,
  onUpdatePage: (page) => {
    pagination.value.page = page
    fetchData()
  },
  onUpdatePageSize: (pageSize) => {
    pagination.value.pageSize = pageSize
    pagination.value.page = 1
    fetchData()
  },
  // 中文本地化
  prefix: (info) => `共 ${info.itemCount} 条`,
  suffix: (info) => `第 ${info.page} 页`,
  pageInfo: (info) => `每页 ${info.pageSize} 条，共 ${info.itemCount} 条，共 ${info.totalPage} 页`
}

// 表单验证规则
const formRules = {
  agv_id: {
    required: true,
    message: '请输入小车ID',
    trigger: 'blur'
  },
  problem_description: {
    required: true,
    message: '请输入问题描述',
    trigger: 'blur'
  }
}

// 表格列配置
const columns = [
  {
    title: 'ID',
    key: 'id',
    width: isMobileView.value ? 60 : 80,
    align: 'center'
  },
  {
    title: '小车ID',
    key: 'agv_id',
    width: isMobileView.value ? 100 : 120
  },
  {
    title: '问题描述',
    key: 'problem_description',
    minWidth: isMobileView.value ? 150 : 200
  },
  {
    title: '小车状态',
    key: 'agv_status',
    width: isMobileView.value ? 120 : 150
  },
  {
    title: '备注',
    key: 'remarks',
    minWidth: isMobileView.value ? 120 : 150
  },
  {
    title: '创建时间',
    key: 'create_time',
    width: isMobileView.value ? 140 : 180,
    render(row) {
      // 确保时间正确显示，如果数据中没有时间则显示"-"
      const time = row.create_time || row.create_datetime || row.timestamp || '-';
      if (time === '-') {
        return h('span', { style: { color: '#999' } }, '-')
      }
      // 尝试将时间戳转换为可读格式
      let formattedTime = time;
      if (typeof time === 'number') {
        // 如果是时间戳，转换为日期
        formattedTime = new Date(time * 1000).toLocaleString('zh-CN');
      } else if (typeof time === 'string' && /^\d+$/.test(time)) {
        // 如果是字符串格式的时间戳，也转换
        formattedTime = new Date(parseInt(time) * 1000).toLocaleString('zh-CN');
      } else if (typeof time === 'string' && !isNaN(Date.parse(time))) {
        // 如果是日期字符串，转换为本地格式
        formattedTime = new Date(time).toLocaleString('zh-CN');
      }
      return h('span', formattedTime);
    }
  },
  {
    title: '操作',
    key: 'actions',
    width: isMobileView.value ? 140 : 200,
    render(row) {
      return h('div', { class: 'action-buttons' }, [
        h(NButton, {
          size: isMobileView.value ? 'tiny' : 'small',
          type: 'primary',
          style: 'margin-right: 4px;',
          onClick: () => editRecord(row)
        }, { default: () => '编辑' }),
        h(NPopconfirm, {
          onPositiveClick: () => deleteRecord(row.id)
        }, {
          trigger: () => h(NButton, {
            size: isMobileView.value ? 'tiny' : 'small',
            type: 'error'
          }, { default: () => '删除' }),
          default: () => '确定要删除这条记录吗？'
        })
      ])
    }
  }
]

// 获取数据
const fetchData = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams({
      agv_id: searchForm.value.agv_id,
      keyword: searchForm.value.keyword,
      agv_status: searchForm.value.agv_status,
      start_date: searchForm.value.start_date,
      end_date: searchForm.value.end_date,
      page: pagination.value.page,
      page_size: pagination.value.pageSize
    })

    const response = await fetch(`/api/rcms/exception_logs?${params.toString()}`)
    const result = await response.json()

    if (result.message === 'success') {
      tableData.value = result.data.data
      pagination.value.itemCount = result.data.total_count
    } else {
      message.error(result.errors?.[0] || '获取数据失败')
    }
  } catch (error) {
    message.error(`获取数据失败: ${error.message}`)
  } finally {
    loading.value = false
  }
}

// 查询记录
const searchRecords = () => {
  // 更新日期范围
  if (dateRange.value && dateRange.value.length === 2) {
    searchForm.value.start_date = dateRange.value[0]
    searchForm.value.end_date = dateRange.value[1]
  } else {
    searchForm.value.start_date = ''
    searchForm.value.end_date = ''
  }

  pagination.value.page = 1
  fetchData()
}

// 重置查询条件
const resetSearch = () => {
  searchForm.value = {
    agv_id: '',
    keyword: '',
    agv_status: '',
    start_date: '',
    end_date: ''
  }
  dateRange.value = null
  pagination.value.page = 1
  fetchData()
}

// 编辑记录
const editRecord = (record) => {
  formModel.value = { ...record }
  showAddModal.value = true
}

// 删除记录
const deleteRecord = async (id) => {
  try {
    const response = await fetch(`/api/rcms/exception_logs/${id}`, {
      method: 'DELETE'
    })
    const result = await response.json()

    if (result.message === 'success') {
      message.success('删除成功')
      fetchData()
    } else {
      message.error(result.errors?.[0] || '删除失败')
    }
  } catch (error) {
    message.error(`删除失败: ${error.message}`)
  }
}

// 添加记录
const addRecord = async () => {
  formSubmitting.value = true
  try {
    const response = await fetch('/api/rcms/add_exception_logs', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        agv_id: formModel.value.agv_id,
        problem_description: formModel.value.problem_description,
        agv_status: formModel.value.agv_status,
        remarks: formModel.value.remarks
      })
    })

    const result = await response.json()

    if (result.message === 'success') {
      message.success('添加成功')
      return true
    } else {
      message.error(result.errors?.[0] || '添加失败')
      return false
    }
  } catch (error) {
    message.error(`添加失败: ${error.message}`)
    return false
  } finally {
    formSubmitting.value = false
  }
}

// 更新记录
const updateRecord = async () => {
  formSubmitting.value = true
  try {
    const response = await fetch(`/api/rcms/exception_logs/${formModel.value.id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        agv_id: formModel.value.agv_id,
        problem_description: formModel.value.problem_description,
        agv_status: formModel.value.agv_status,
        remarks: formModel.value.remarks
      })
    })

    const result = await response.json()

    if (result.message === 'success') {
      message.success('更新成功')
      return true
    } else {
      message.error(result.errors?.[0] || '更新失败')
      return false
    }
  } catch (error) {
    message.error(`更新失败: ${error.message}`)
    return false
  } finally {
    formSubmitting.value = false
  }
}

// 提交表单
const submitForm = async () => {
  let success = false

  if (formModel.value.id) {
    // 更新记录
    success = await updateRecord()
  } else {
    // 添加记录
    success = await addRecord()
  }

  if (success) {
    showAddModal.value = false
    resetForm()
    fetchData()
  }
}

// 重置表单
const resetForm = () => {
  formModel.value = {
    id: null,
    agv_id: '',
    problem_description: '',
    agv_status: '',
    remarks: ''
  }
}

// 导出为文本格式
const exportToText = () => {
  if (tableData.value.length === 0) {
    message.warning('当前没有数据可以导出');
    return;
  }

  // 生成文本格式：AGV ID + 时间（根据选项）+ 状态 + 备注（根据选项）
  const textLines = tableData.value.map(record => {
    // 构建输出行
    let lineParts = [];

    // 添加时间（如果选项开启）
    if (includeTimeInExport.value) {
      let timePart = '';
      const time = record.create_time || record.create_datetime || record.timestamp || '';

      if (time) {
        let dateObj;
        if (typeof time === 'number') {
          // 时间戳
          dateObj = new Date(time * 1000);
        } else if (typeof time === 'string' && /^\d+$/.test(time)) {
          // 字符串时间戳
          dateObj = new Date(parseInt(time) * 1000);
        } else if (typeof time === 'string' && !isNaN(Date.parse(time))) {
          // 日期字符串
          dateObj = new Date(time);
        } else {
          // 如果无法解析，尝试直接解析字符串
          dateObj = new Date(time);
        }

        if (dateObj && !isNaN(dateObj.getTime())) {
          // 格式化为 HH:mm:ss
          timePart = dateObj.toLocaleTimeString('zh-CN', { hour12: false });
        } else {
          timePart = '';
        }
      } else {
        timePart = '';
      }
      lineParts.push(record.agv_id || '');
      lineParts.push(timePart);
    }

    // 添加状态
    lineParts.push(record.agv_status || '');

    // 添加备注（如果选项开启）
    if (includeRemarksInExport.value) {
      lineParts.push(record.remarks || '');
    }

    return lineParts.join(' ');
  });

  previewContent.value = textLines.join('\n');
  showPreviewModal.value = true;
}

// 复制到剪贴板
const copyToClipboard = () => {
  const textContent = previewContent.value;

  navigator.clipboard.writeText(textContent)
    .then(() => {
      message.success('文本已复制到剪贴板');
      showPreviewModal.value = false;
    })
    .catch(err => {
      message.error('复制失败，请手动复制');
      console.error('Failed to copy text: ', err);

      // 如果复制失败，提供一个临时的 textarea 供用户手动复制
      const textArea = document.createElement('textarea');
      textArea.value = textContent;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      showPreviewModal.value = false;
    });
}

// 导出为CSV格式
const exportToCSV = () => {
  if (tableData.value.length === 0) {
    message.warning('当前没有数据可以导出');
    return;
  }

  // 创建CSV头部
  const headers = ['ID', '小车ID', '问题描述', '小车状态', '备注', '创建时间'];
  const csvContent = [
    headers.join(','),
    ...tableData.value.map(record => [
      record.id || '',
      `"${record.agv_id || ''}"`,
      `"${(record.problem_description || '').replace(/"/g, '""')}"`,
      `"${(record.agv_status || '').replace(/"/g, '""')}"`,
      `"${(record.remarks || '').replace(/"/g, '""')}"`,
      `"${formatDateForCSV(record.timestamp || '')}"`
    ].join(','))
  ].join('\n');

  // 创建下载链接
  const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.setAttribute('href', url);
  link.setAttribute('download', `exception_records_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// 格式化日期用于CSV
const formatDateForCSV = (dateValue) => {
  if (!dateValue) return '';

  let dateObj;
  if (typeof dateValue === 'number') {
    // 时间戳
    dateObj = new Date(dateValue * 1000);
  } else if (typeof dateValue === 'string' && /^\d+$/.test(dateValue)) {
    // 字符串时间戳
    dateObj = new Date(parseInt(dateValue) * 1000);
  } else if (typeof dateValue === 'string' && !isNaN(Date.parse(dateValue))) {
    // 日期字符串
    dateObj = new Date(dateValue);
  } else {
    // 如果无法解析，尝试直接解析字符串
    dateObj = new Date(dateValue);
  }

  if (dateObj && !isNaN(dateObj.getTime())) {
    return dateObj.toLocaleString('zh-CN');
  }
  return dateValue;
}

// 处理文件导入前的操作
const beforeImport = async (data) => {
  // Naive UI Upload组件提供的文件对象结构不同
  const file = data.file.file;
  const fileName = data.file.name.toLowerCase();

  try {
    if (fileName.endsWith('.csv')) {
      await importCSV(file);
    } else if (fileName.endsWith('.txt')) {
      await importTXT(file);
    } else {
      message.error('不支持的文件格式，请上传CSV或TXT文件');
      return false;
    }
    return false; // 阻止默认上传行为
  } catch (error) {
    message.error(`导入失败: ${error.message}`);
    return false;
  }
}

// 导入CSV文件
const importCSV = (file) => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = async (e) => {
      try {
        const content = e.target.result;
        const lines = content.split(/\r?\n/).filter(line => line.trim() !== '');

        if (lines.length < 2) {
          throw new Error('CSV文件内容为空或格式不正确');
        }

        let importedCount = 0;
        for (let i = 1; i < lines.length; i++) {
          const line = lines[i].trim();
          if (!line) continue;

          // 简单的CSV解析（考虑引号包围的字段）
          const fields = parseCSVLine(line);

          if (fields.length >= 3) { // 至少需要小车ID和问题描述
            const agvId = fields[1]?.trim() || '';
            const problemDescription = fields[2]?.trim() || '';

            // 验证必要字段
            if (!agvId || !problemDescription) {
              console.warn(`第${i + 1}行缺少必要字段，跳过导入: AGV ID='${agvId}', 问题描述='${problemDescription}'`);
              continue; // 跳过这一行
            }

            const record = {
              agv_id: agvId,
              problem_description: problemDescription,
              agv_status: fields[3]?.trim() || '',
              remarks: fields[4]?.trim() || ''
            };

            // 添加记录到数据库
            try {
              const response = await fetch('/api/rcms/add_exception_logs', {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json'
                },
                body: JSON.stringify(record)
              });

              const result = await response.json();
              if (result.message !== 'success') {
                throw new Error(`添加记录失败: ${result.errors?.[0] || '未知错误'}`);
              }
              importedCount++;
            } catch (error) {
              throw new Error(`导入第${i + 1}行时出错: ${error.message}`);
            }
          }
        }

        message.success(`成功导入 ${importedCount} 条记录`);
        fetchData(); // 刷新数据
        resolve();
      } catch (error) {
        reject(error);
      }
    };

    reader.onerror = () => {
      reject(new Error('读取文件失败'));
    };

    reader.readAsText(file, 'UTF-8');
  });
};

// 解析CSV行（简单实现，处理带引号的字段）
const parseCSVLine = (line) => {
  const fields = [];
  let currentField = '';
  let inQuotes = false;
  let i = 0;

  while (i < line.length) {
    const char = line[i];

    if (char === '"') {
      if (inQuotes && i + 1 < line.length && line[i + 1] === '"') {
        // 转义的双引号
        currentField += '"';
        i += 2;
        continue;
      }
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      fields.push(currentField.trim());
      currentField = '';
    } else {
      currentField += char;
    }
    i++;
  }

  fields.push(currentField.trim());
  return fields;
};

// 导入TXT文件（按行解析，每行格式：AGV_ID TIME STATUS REMARKS）
const importTXT = (file) => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = async (e) => {
      try {
        const content = e.target.result;
        const lines = content.split(/\r?\n/).filter(line => line.trim() !== '');

        if (lines.length === 0) {
          throw new Error('TXT文件内容为空');
        }

        let importedCount = 0;
        for (let i = 0; i < lines.length; i++) {
          const line = lines[i].trim();
          if (!line) continue;

          // 解析文本行：AGV ID [TIME] STATUS [REMARKS]
          const parts = line.split(/\s+/).filter(part => part !== '');

          if (parts.length >= 2) { // 至少需要AGV ID和 something else
            const agvId = parts[0]?.trim() || '';
            let problemDescription = parts.length > 2 ? parts.slice(1, -1).join(' ') : '从文本导入';
            let agvStatus = parts.length > 2 ? parts[parts.length - 1] : parts[1];

            // 如果有更多部分，最后一个是状态，倒数第二部分可能是时间
            if (parts.length >= 3) {
              // 尝试识别时间格式 (HH:MM:SS)
              const lastPart = parts[parts.length - 1];
              const secondLastPart = parts[parts.length - 2];

              // 如果最后部分看起来像时间，则倒数第二部分是状态，剩余的是问题描述
              if (/^\d{1,2}:\d{2}:\d{2}$/.test(lastPart)) {
                agvStatus = secondLastPart;
                problemDescription = parts.slice(1, parts.length - 2).join(' ');
              } else {
                // 否则最后一个部分是状态
                agvStatus = lastPart;
                problemDescription = parts.slice(1, parts.length - 1).join(' ');
              }
            }

            // 验证必要字段
            if (!agvId || !problemDescription) {
              console.warn(`第${i + 1}行缺少必要字段，跳过导入: AGV ID='${agvId}', 问题描述='${problemDescription}'`);
              continue; // 跳过这一行
            }

            const record = {
              agv_id: agvId,
              problem_description: problemDescription,
              agv_status: agvStatus,
              remarks: ''
            };

            // 添加记录到数据库
            try {
              const response = await fetch('/api/rcms/add_exception_logs', {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json'
                },
                body: JSON.stringify(record)
              });

              const result = await response.json();
              if (result.message !== 'success') {
                throw new Error(`添加记录失败: ${result.errors?.[0] || '未知错误'}`);
              }
              importedCount++;
            } catch (error) {
              throw new Error(`导入第${i + 1}行时出错: ${error.message}`);
            }
          }
        }

        message.success(`成功导入 ${importedCount} 条记录`);
        fetchData(); // 刷新数据
        resolve();
      } catch (error) {
        reject(error);
      }
    };

    reader.onerror = () => {
      reject(new Error('读取文件失败'));
    };

    reader.readAsText(file, 'UTF-8');
  });
};

// 初始化数据
onMounted(() => {
  fetchData()
  window.addEventListener('resize', updateIsMobileView)
})
</script>

<style scoped>
.exception-records-container {
  padding: 20px;
  background-color: #f5f5f5;
  min-height: 100vh;
}

.action-buttons {
  display: flex;
  gap: 8px;
}

.header-actions {
  display: flex;
  justify-content: flex-end;
  min-width: 200px;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .exception-records-container {
    padding: 10px 5px;
  }

  .header-actions {
    width: 100%;
    min-width: auto;
    justify-content: flex-end;
  }

  .mobile-search-controls {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .mobile-search-controls .n-button {
    margin-left: 0 !important;
    margin-top: 8px;
  }

  .desktop-search-controls {
    display: flex;
    gap: 8px;
  }
}

/* 针对更小屏幕的优化 */
@media (max-width: 480px) {
  .exception-records-container {
    padding: 5px;
  }

  :deep(.n-card__content) {
    padding: 12px 10px !important;
  }
}
</style>