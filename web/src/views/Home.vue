<script setup>
import TaskDisplayComponent from '@/components/TaskDisplayComponent.vue'
import SSHComponent from '@/components/ssh.vue'
import {
  NButton, NCard, NDataTable, NDivider, NDrawer, NForm, NFormItem, NInput,
  NInputNumber,
  NModal,
  NProgress, NRadioButton, NRadioGroup,
  NScrollbar,
  NSpace, NSwitch, NTabPane, NTabs, NTag, NText, useLoadingBar, useMessage
} from 'naive-ui'
import { computed, h, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
const robotImgUrl = computed(() => location.origin + '/api/robot_img/online.png')
const robotoffImgUrl = computed(() => location.origin + '/api/robot_img/offline.png')
const robot_fullImgUrl = computed(() => location.origin + '/api/robot_img/full.png')
const clicktimes = ref(Number(localStorage.getItem('clicktimes')) || 3);
function saveClickTimes() {
  localStorage.setItem('clicktimes', clicktimes.value);
}
// 解析滚筒状态码，返回4个位置的状态数组
// 后4位从左到右：左下(1)、左上(2)、右下(3)、右上(4)
const rollerPositions = computed(() => {
  if (!selectedRobot.value) return [false, false, false, false]

  // 获取滚筒状态码，默认0
  const rollerStatus = selectedRobot.value.roller_status_code || 0

  // 取后4位数字，转换为字符串并确保4位（不足补0）
  const last4Digits = String(rollerStatus).slice(-4).padStart(4, '0')
  // 分割为数组，转换为布尔值（0为false，1为true）
  return last4Digits.split('').map(digit => digit === '1')
})
// 响应式抽屉宽度
const drawerWidth = computed(() => {
  // 根据屏幕尺寸动态调整抽屉宽度
  if (window.innerWidth <= 480) {
    return '75%' // 小屏手机使用95%宽度
  } else if (window.innerWidth <= 768) {
    return '70%' // 平板使用90%宽度
  } else {
    return '450px' // 桌面使用固定450px宽度
  }
})

// 初始化loading bar
const loadingBar = useLoadingBar()
const message = useMessage()
const isConnected = ref(false)
const ws = ref(null)
// 状态管理
const robotData = ref([])
const avgbattery = ref(0)
const loading = ref(true)
const timestamp = ref('')
const messageText = ref('正在获取机器人状态数据...')
// Tab状态
const activeTab = ref('all') // all, abnormal, removed
// tabs类型
const tabsType = ref(localStorage.getItem('tabs_type') || 'segment')
// 是否显示平均电量
const showAvgBattery = ref(localStorage.getItem('show_avg_battery') !== 'false')
const abnormal_e_offline = ref(localStorage.getItem('abnormal_e_offline') !== 'false')
const darkMode = inject('darkMode', ref(localStorage.getItem('dark_mode') === 'true'))
const selectedRobot = ref(null)
const showDetailDrawer = ref(false)
// 详情抽屉标签页状态
const detailActiveTab = ref('info')
// SSH面板状态
const showSSHPanel = ref(false)
// 设置抽屉状态
const showSettingsDrawer = ref(false)

// SSH连接配置
const sshConfig = reactive({
  username: '',  // 默认用户名
  password: ''  // 默认密码
})

// 处理标签切换
const handleTabChange = (tabName) => {
  if (tabName === 'files') {
    showSSHPanel.value = true
  } else {
    showSSHPanel.value = false
  }
}

// 监听标签变化，在抽屉打开时如果切换到files标签，也要显示SSH面板
watch(detailActiveTab, (newVal) => {
  if (newVal === 'files' && showDetailDrawer.value) {
    showSSHPanel.value = true
  } else if (newVal !== 'files') {
    showSSHPanel.value = false
  }
})

// 显示机器人详细信息
const showRobotDetail = (robot) => {
  selectedRobot.value = robot
  showDetailDrawer.value = true
  // Move focus to drawer when it opens to prevent focus retention in main content
  setTimeout(() => {
    const drawerContent = document.querySelector('.detail-drawer-content')
    if (drawerContent) {
      drawerContent.setAttribute('tabindex', '-1')
      // drawerContent.focus()
    }
  }, 100)
  sshConfig.username = "root"
  sshConfig.password = robot.version.includes('V4.') ? 'Hik@1234' : 'hiklinux'
}

// 关闭机器人详细信息
const closeDetailModal = () => {
  selectedRobot.value = null
  showDetailDrawer.value = false
  showSSHPanel.value = false  // 关闭SSH面板，这将导致断开连接
}

// 异常记录模态框相关
const showAddExceptionModal = ref(false)
const exceptionForm = ref({
  agv_id: '',
  problem_description: '',
  agv_status: '',
  remarks: ''
})
const moredetail = (agv_status, main_name, sub_name) => {
  if (agv_status.includes("机器人异常") || agv_status.includes("任务异常")) {
    return main_name || sub_name
  } else {
    return agv_status
  }
}
// 打开添加异常记录模态框
const openAddExceptionModal = () => {
  if (selectedRobot.value) {
    // 自动填充相关信息
    exceptionForm.value.agv_id = selectedRobot.value.RobotId

    // 构造问题描述：坐标(X,Y) + 状态文字
    const x = selectedRobot.value.position?.x || 0
    const y = selectedRobot.value.position?.y || 0
    const coordinates = `${x},${y}`

    exceptionForm.value.problem_description = coordinates

    // 使用状态码对应的文字作为小车状态
    // const statusCode = selectedRobot.value.status_code || 0
    const statusText = selectedRobot.value.status || '未知状态'
    exceptionForm.value.agv_status = moredetail(statusText)

    exceptionForm.value.remarks = ''
  }
  showAddExceptionModal.value = true
}

// 关闭添加异常记录模态框
const closeAddExceptionModal = () => {
  showAddExceptionModal.value = false
  // 重置表单
  exceptionForm.value = {
    agv_id: '',
    problem_description: '',
    agv_status: '',
    remarks: ''
  }
}

// 打开设置抽屉
const openSettingsDrawer = () => {
  showSettingsDrawer.value = true
}

// 关闭设置抽屉
const closeSettingsDrawer = () => {
  showSettingsDrawer.value = false
}

// 保存Tab类型设置
const saveTabsType = (value) => {
  localStorage.setItem('tabs_type', value)
}
const saveShowAvgBattery = (value) => {
  localStorage.setItem('show_avg_battery', value)
}
const saveabnormal_e_offline = (value) => {
  localStorage.setItem('abnormal_e_offline', value)
}
const savedarkMode = (value) => {
  localStorage.setItem('dark_mode', value)
}

watch(darkMode, (newVal) => {
  document.documentElement.dataset.theme = newVal ? 'dark' : 'light'
})


// 提交异常记录
const submitExceptionRecord = async () => {
  try {
    const response = await fetch('/api/rcms/add_exception_logs', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        agv_id: exceptionForm.value.agv_id,
        problem_description: exceptionForm.value.problem_description,
        agv_status: exceptionForm.value.agv_status,
        remarks: exceptionForm.value.remarks
      })
    })

    const data = await response.json()

    if (data.message === 'success') {
      message.success('异常记录添加成功')
      closeAddExceptionModal()
    } else {
      message.error(`添加失败: ${data.errors?.[0] || JSON.stringify(data.detail) || '未知错误'}`)
    }
  } catch (error) {
    message.error(`提交异常记录时发生错误: ${error.message}`)
  }
}
const timeage = (time) => {
  const now = new Date()
  const then = new Date(time)
  const diff = now - then

  // 转换为秒
  const diffSeconds = Math.floor(diff / 1000)

  // 超过10秒才显示时间
  if (diffSeconds <= 10) {
    return ''
  }

  // 定义时间单位
  if (diffSeconds < 60) {
    return `↓${diffSeconds}s`
  } else if (diffSeconds < 3600) {
    const minutes = Math.floor(diffSeconds / 60)
    return `↓${minutes}m`
  } else if (diffSeconds < 86400) {
    const hours = Math.floor(diffSeconds / 3600)
    return `↓${hours}h`
  } else {
    const days = Math.floor(diffSeconds / 86400)
    return `↓${days}d`
  }
}

const colored = (row) => {
  let s = "var(--n-text-color)"
  if (row.abnormal || row.status_code == 67 || (row.status && row.status.includes('异常'))) {
    s = "red"
  }
  if (row.status_text.includes('遇障') || row.status_text.includes('对接微调中')) {
    s = "#FF9900"
  }

  return s
}
const sortstate = ref(null)
watch(sortstate, (newVal) => {
  localStorage.setItem("table_sort", JSON.stringify(newVal))
}, { deep: true })
// 表格列配置
const columns = [
  {
    title: '机器人ID',
    key: 'RobotId',
    sorter: (A, B) => Number(A.RobotId) - Number(B.RobotId),
    render(row) {
      const timeInfo = timeage(row.time * 1000)
      return h('div', {
        class: 'robot-id-container',
        style: {
          color: timeInfo ? "red" : "var(--n-text-color)"
        },
      }, { default: () => timeInfo ? `${row.RobotId}\n${timeInfo}` : row.RobotId })
    }
  },
  {
    title: '状态',
    key: 'display_status',
    sorter: (A, B) => A.display_status.localeCompare(B.display_status, "zh-CN"),
    render(row) {
      return h('div', {
        class: 'status-tag-container',
      }, [
        h(NTag, {
          type: row.status_color,
          round: true,
          style: {
            cursor: 'pointer'
          },
          onClick: () => showRobotDetail(row)
        }, { default: () => row.display_status })
      ])
    }
  },
  {
    title: '设备任务',
    key: 'device_task',
    sorter: (A, B) => Number(A.status_code) - Number(B.status_code),
    render(row) {
      return h('div', {
        class: 'device-task-container',
        style: {
          color: colored(row)
        },
      }, { default: () => row.device_task || '-' })
    }
  },
  {
    title: '电量',
    key: 'battery_text',
    sorter: (A, B) => Number(A.battery) - Number(B.battery),
    render(row) {
      // 获取电池百分比数值
      const batteryValue = parseInt(row.battery_text) || 0
      const batteryPercent = Math.max(0, Math.min(100, batteryValue))
      let color = `black`
      if (batteryPercent <= 30) {
        color = "red"
      } else if (batteryPercent <= 80) {
        color = `var(--n-text-color)`
      } else {
        color = `green`
      }
      return h('div', {
        class: 'battery-container',
        style: {
          color: color
        },
      }, { default: () => row.battery_text + (row.status_code == 7 ? '⚡' : '') })
    }
  },
  {
    title: '速度',
    key: 'speed_text',
    sorter: (A, B) => Number(A.speed) - Number(B.speed),

  },
  {
    title: '报警信息',
    sorter: (A, B) => A.display_status.localeCompare(B.display_status, "zh-CN"),
    key: 'alarm_text'
  },
  // {
  //   title: '操作',
  //   key: 'actions',
  //   render(row) {
  //     return h(NButton, {
  //       size: 'small',
  //       type: 'primary',
  //       onClick: () => showRobotDetail(row)
  //     }, { default: () => '查看详情' })
  //   }
  // }
]

// 连接WebSocket
const connectWebSocket = () => {
  loading.value = true
  messageText.value = '正在连接服务器...'

  try {
    // 创建WebSocket连接（使用相对路径）
    const wsUrl = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsPath = `${wsUrl}//${window.location.host}/ws/robot-status`
    console.log('正在连接WebSocket:', wsPath)
    ws.value = new WebSocket(wsPath)

    // 连接打开
    ws.value.onopen = () => {
      console.log('WebSocket连接已打开')
      isConnected.value = true
      loading.value = false
      messageText.value = 'WebSocket连接已打开'
      console.log('连接状态:', isConnected.value)
    }

    // 接收消息
    ws.value.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type == 'heartbeat') {
          return
        }
        // 转换数据格式，添加友好的文本显示
        timestamp.value = data.timestamp || ''
        const formattedData = Object.values(data.data || {}).map(item => {
          // 确定显示状态和颜色，基于showrobot.py的逻辑
          let displayStatus = '正常'
          let statusColor = 'success'

          // 异常状态判断
          if (item.abnormal || [67, 61].includes(Number(item.status_code)) || (item.status && item.status.includes('异常'))) {
            displayStatus = '异常'
            statusColor = 'error'
          }
          // 暂停状态判断
          else if (item.stop) {
            displayStatus = '暂停'
            statusColor = 'warning'
          }
          // 排除状态判断
          else if (item.remove) {
            displayStatus = '排除'
            statusColor = 'info'
          }

          // 获取设备任务信息
          const device_task = item.status ? `${item.status}(${item.status_code || ''})` : '未知'

          return {
            ...item,
            // 转换状态为文本
            status_text: item.status || '未知',
            // 设备任务文本显示
            device_task: device_task,
            // 转换电量为百分比文本
            battery_text: (item.battery || 0) + '%',
            alarm_text: item.alarm ? `${item.alarm.main_name || ''};${item.alarm.sub_name || ''}` : '无',
            // 显示状态信息
            display_status: displayStatus,
            status_color: statusColor,
            // 转换速度为文本
            speed_text: item.speed ? `${item.speed}` : '0'
          }
        })
        robotData.value = formattedData
        avgbattery.value = Math.round(robotData.value.reduce((sum, b) => sum + Number(b.battery), 10) / robotData.value.length)
        // 如果当前有选中的机器人，更新选中的机器人数据
        if (selectedRobot.value) {
          const updatedRobot = formattedData.find(robot => robot.RobotId === selectedRobot.value.RobotId)
          if (updatedRobot) {
            selectedRobot.value = updatedRobot
          }
        }
      } catch (error) {
        console.error('解析WebSocket消息错误:', error)
      }
    }

    // 连接关闭
    ws.value.onclose = () => {
      console.log('WebSocket连接已关闭')
      isConnected.value = false
      loading.value = false
      messageText.value = 'WebSocket连接已关闭'
      loadingBar.error()

      // 尝试重新连接
      // setTimeout(connectWebSocket, 3000)
    }

    // 连接错误
    ws.value.onerror = (error) => {
      console.error('WebSocket连接错误:', error)
      isConnected.value = false
      loading.value = false
      messageText.value = 'WebSocket连接错误'
      loadingBar.error()
    }

  } catch (error) {
    console.error('创建WebSocket连接失败:', error)
    isConnected.value = false
    loading.value = false
    messageText.value = '创建WebSocket连接失败'
    loadingBar.error()

    // 尝试重新连接
  }
}

// 断开WebSocket连接
const disconnectWebSocket = () => {
  if (ws.value) {
    ws.value.close()
    ws.value = null
  }
}

// 刷新数据
const refreshData = () => {
  if (isConnected.value) {
    loadingBar.start()
    // WebSocket会自动更新数据
    setTimeout(() => {
      loadingBar.finish()
    }, 1000)
  } else {
    connectWebSocket()
  }
}

const tableRef = ref(null)
// 生命周期钩子
onMounted(() => {
  connectWebSocket()
  getmaplist()
})

onBeforeUnmount(() => {
  disconnectWebSocket()
})
const robotcount = reactive({
  all: 0,
  abnormal: 0,
  removed: 0,
  offline: 0
})

const tabsConfig = computed(() => [
  { name: 'all', label: `全部(${robotcount.all})`, count: robotcount.all },
  { name: 'abnormal', label: `异常(${robotcount.abnormal})`, count: robotcount.abnormal },
  { name: 'removed', label: `排除(${robotcount.removed})`, count: robotcount.removed },
  { name: 'offline', label: `离线(${robotcount.offline})`, count: robotcount.offline }
])

const getFilteredData = () => {
  let data = robotData.value || []
  let abnormalrbt, removedrbt = []
  if (abnormal_e_offline.value) {
    abnormalrbt = data.filter(item => (item.abnormal === true || item.status_code == 67 || item.display_status == "异常") && timeage(item.time * 1000) == "")
    removedrbt = data.filter(item => (item.remove === true) && timeage(item.time * 1000) == "")
  } else {
    abnormalrbt = data.filter(item => item.abnormal === true || item.status_code == 67 || item.display_status == "异常")
    removedrbt = data.filter(item => item.remove === true)
  }

  let offlinerbt = data.filter(item => timeage(item.time * 1000) !== "")

  robotcount.abnormal = abnormalrbt.length
  robotcount.removed = removedrbt.length
  robotcount.offline = offlinerbt.length
  robotcount.all = data.length
  switch (activeTab.value) {
    case 'abnormal':
      return abnormalrbt
    case 'removed':
      return removedrbt
    case 'offline':
      return offlinerbt
    default:
      return data
  }
}
const stopagv = async (agvcode = "", stop = false) => {
  // 调用后端API，使用POST方法和JSON body
  const response = await fetch('/api/rcs_web/stopagv', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      "agvcode": agvcode,
      "stop": stop
    })
  })
  const data = await response.json()

  if (data.code == 0) {
    message.info(data.message)
  } else {
    message.error(data.message)
  }
}
const removeagv = async (agvcode = "") => {
  const response = await fetch('/api/rcms/remove_agv_status?robot_id=' + agvcode, {
    method: 'GET',
  })
  const data = await response.json()
  message.error(data.message || JSON.stringify(data))
}
const mapinfo = ref([])
const getmaplist = async () => {
  const response = await fetch('/api/rcms/maplist', {
    method: 'GET',
  })
  const data = await response.json()
  mapinfo.value = data
  if (mapinfo.value?.length == 0) {
    message.error("获取地图列表失败")
  }
}
const freeagv = async (agvcode = "", stop = false) => {
  // 调用后端API，使用POST方法和JSON body
  const response = await fetch('/api/rcs_web/freeagv', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      "agvcode": agvcode,
    })
  })
  const data = await response.json()

  if (data.code == 0) {
    message.info(data.message)
  } else {
    message.error(data.message)
  }
}
</script>

<template>
  <div class="main-container">
    <!-- 主内容区域 -->
    <div class="main-content" :inert="showDetailDrawer">
      <NCard :title="mapinfo?.[0]?.name || 'AGV监控'" :bordered="false" style="max-width: 1200px; margin: 0 auto;">
        <template #header-extra>
          <NSpace>
            <NButton @click="openSettingsDrawer" :bordered="false">

              <template #icon>
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="3"></circle>
                  <path
                    d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z">
                  </path>
                </svg>
              </template>
            </NButton>
            <NTag :type="isConnected ? 'success' : 'error'" round style="margin-top: 4px;">
              {{ isConnected ? '已连接' : '未连接' }}
            </NTag>
            <NButton type="primary" @click="refreshData" :loading="loading">
              重新连接
            </NButton>
          </NSpace>
        </template>
        <!-- 标签页过滤器 -->
        <NTabs v-model:value="activeTab" :type="tabsType" style="margin-bottom: 0px;">
          <NTabPane v-for="tab in tabsConfig" :key="tab.name" :name="tab.name" :tab="tab.label"
            :tab-props="{ style: { color: (tab.name === 'abnormal' && tab.count > 0) ? 'red' : '' } }" />
        </NTabs>

        <n-progress v-if="showAvgBattery" type="line" :percentage="avgbattery" :color="{ stops: ['orange', 'green'] }"
          :height="6"> {{
            avgbattery }}%
          <span style="font-size: 14px; color: #36ad6a; margin-left: 14px"> {{ timestamp ? new Date(Number(timestamp) *
            1000).toLocaleTimeString('zh-CN') : '' }} </span>
        </n-progress>
        <NText v-if="loading" type="secondary" style="text-align: center; display: block; margin: 40px 0;">
          {{ messageText }}
        </NText>

        <NDataTable v-else ref="tableRef" :columns="columns" :data="getFilteredData()" :pagination="false" bordered
          stripe size="medium" empty-text="暂无机器人数据" v-model:sorter="sortstate" />
        <NDivider />

        <NText type="secondary" style="font-size: 12px;">
          实时数据更新频率：1次/秒
        </NText>
      </NCard>
    </div>

    <!-- 设置抽屉 -->
    <NDrawer v-model:show="showSettingsDrawer" placement="bottom" :width="drawerWidth" @close="closeSettingsDrawer"
      resizable default-height="50%">
      <n-scrollbar>
        <div class="settings-drawer-content">
          <NTabs type="bar" style="margin-bottom: 20px;">
            <NTabPane name="basic" tab="页面设置">
              <NForm>
                <NFormItem label="Tab类型" style="display: flex; align-items: center; margin: 10px;">
                  <template #label>
                    <span style="margin-right: 10px;">Tab类型 </span>
                  </template>
                  <NRadioGroup v-model:value="tabsType" @update:value="saveTabsType">
                    <NRadioButton value="bar" type="primary">柱状</NRadioButton>
                    <NRadioButton value="line">线条</NRadioButton>
                    <NRadioButton value="card">卡片</NRadioButton>
                    <NRadioButton value="segment">分段</NRadioButton>
                  </NRadioGroup>
                </NFormItem>
                <!-- 显示平均电量 -->
                <div style="display: flex; align-items: center; margin: 10px;">
                  <span style="margin-right: 10px;">平均电量</span>
                  <NSwitch v-model:value="showAvgBattery" @update:value="saveShowAvgBattery" />
                  <span style="font-size: 12px; color: #999; margin-left: 8px;">显示所有机器人平均电量进度条</span>
                </div>
                <!-- 离线机器人不显示在异常和排除里面 -->
                <div style="display: flex; align-items: center; margin: 10px;">
                  <span style="margin-right: 10px;">排除离线</span>
                  <NSwitch v-model:value="abnormal_e_offline" @update:value="saveabnormal_e_offline" />
                  <span style="font-size: 12px; color: #999; margin-left: 8px;">离线机器人不显示在异常和排除标签页</span>
                </div>
                <div style="display: flex; align-items: center; margin: 10px;">
                  <span style="margin-right: 10px;">暗色模式</span>
                  <NSwitch v-model:value="darkMode" @update:value="savedarkMode" />
                  <span style="font-size: 12px; color: #999; margin-left: 8px;">切换深色/浅色主题</span>
                </div>
                <!-- 点击多少次切换背景（<0表示关闭背景） -->
                <div style="display: flex; align-items: center; margin: 10px;">
                  <span style="margin-right: 10px;">点击次数</span>
                  <NInputNumber v-model:value="clicktimes" style="width: 120px;" @update:value="saveClickTimes"
                    button-placement="both" />
                  <span style="font-size: 12px; color: #999; margin-left: 8px;">点击切换背景次数< 1关闭</span>
                </div>
              </NForm>
            </NTabPane>
            <NTabPane name="map" tab="地图信息">
              <div v-for="map in mapinfo" :key="map.name">
                <NFormItem :label="map.name">
                  <view-json>{{ JSON.stringify(map) }}</view-json>
                </NFormItem>
              </div>
            </NTabPane>
          </NTabs>
        </div>

      </n-scrollbar>
    </NDrawer>

    <!-- 机器人详情抽屉 -->
    <NDrawer v-model:show="showDetailDrawer" placement="right" :width="drawerWidth" @close="closeDetailModal">
      <div v-if="selectedRobot" class="detail-drawer-content">
        <h1 style="font-size: 24px; font-weight: bold; display: flex;align-items: center">{{ selectedRobot.RobotId }}
          <span style="margin-left: 10px; position: relative; width: 40px; height: 40px; display: inline-block;">
            <img :src="timeage(selectedRobot.time * 1000) == '' ? robotImgUrl : robotoffImgUrl" style="width: 40px; height: 40px; transform: rotate(180deg);" alt="">
            <!-- 左下 (第1位) -->
            <img v-if="rollerPositions[0]" :src="robot_fullImgUrl"
              style="position: absolute; bottom: 8px; left:11px; width: 8px; height: 8px;" alt="">
            <!-- 左上 (第2位) -->
            <img v-if="rollerPositions[1]" :src="robot_fullImgUrl"
              style="position: absolute; top: 11px; left: 11px; width: 8px; height: 8px;" alt="">
            <!-- 右下 (第3位) -->
            <img v-if="rollerPositions[2]" :src="robot_fullImgUrl"
              style="position: absolute; bottom: 8px; right: 8px; width: 8px; height: 8px;" alt="">
            <!-- 右上 (第4位) -->
            <img v-if="rollerPositions[3]" :src="robot_fullImgUrl"
              style="position: absolute; top: 11px; right: 8px; width: 8px; height: 8px;" alt="">
          </span>
          <span style="font-size: 14px; margin: 8px"> {{ timeage(selectedRobot.time * 1000) }} </span>
          <NButton v-if="timeage(selectedRobot.time * 1000) !== ''" @click="removeagv(selectedRobot.RobotId)"
            type="error" dashed size="medium">移除
          </NButton>
        </h1>

        <!-- 标签页 -->
        <NTabs v-model:value="detailActiveTab" type="card" style="margin: 20px 0;" @update:value="handleTabChange">

          <NTabPane name="info" tab="基本信息">
            <NScrollbar style="max-height: 78vh" trigger="none">
              <div class="detail-section">
                <h4>基本信息</h4>
                <div class="detail-item">
                  <span class="label">IP地址:</span>
                  <span class="value">{{ selectedRobot.ip || '未知' }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">状态:</span>
                  <span class="value">{{ selectedRobot.status || '未知' }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">状态码:</span>
                  <span class="value">{{ selectedRobot.status_code || 0 }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">电量:</span>
                  <span class="value">{{ selectedRobot.battery || 0 }}%</span>
                </div>
                <div class="detail-item">
                  <span class="label">速度:</span>
                  <span class="value">{{ selectedRobot.speed || 0 }}mm/s</span>
                </div>
                <div class="detail-item">
                  <span class="label">地图代码:</span>
                  <span class="value">{{ selectedRobot.map_code || '未知' }}</span>
                </div>
              </div>
              <div class="detail-section">
                <h4>异常与报警</h4>
                <div class="detail-item">
                  <span class="label">状态信息:</span>
                  <div class="value">
                    <NSpace>
                      <NTag :type="selectedRobot.abnormal ? 'error' : 'success'" size="small">
                        异常: {{ selectedRobot.abnormal ? '是' : '否' }}
                      </NTag>
                      <NTag :type="selectedRobot.stop ? 'warning' : 'success'" size="small">
                        停止: {{ selectedRobot.stop ? '是' : '否' }}
                      </NTag>
                      <NTag :type="selectedRobot.stay ? 'info' : 'success'" size="small">
                        停留: {{ selectedRobot.stay ? '是' : '否' }}
                      </NTag>
                      <NTag :type="selectedRobot.remove ? 'info' : 'success'" size="small">
                        排除: {{ selectedRobot.remove ? '是' : '否' }}
                      </NTag>
                    </NSpace>
                  </div>
                </div>
                <div class="detail-item">
                  <span class="label">主报警名称:</span>
                  <span class="value">{{ selectedRobot.alarm?.main_name || '无' }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">子报警名称:</span>
                  <span class="value">{{ selectedRobot.alarm?.sub_name || '无' }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">解决方案:</span>
                  <span class="value">{{ selectedRobot.alarm?.solution || '无' }}</span>
                </div>
                <NSpace>
                  <NButton @click="stopagv(selectedRobot.RobotId, stop = true)" type="error">停止</NButton>
                  <NButton @click="stopagv(selectedRobot.RobotId, stop = false)" type="primary">恢复</NButton>
                  <NButton @click="openAddExceptionModal" type="warning">添加异常记录</NButton>
                </NSpace>
              </div>
              <div class="detail-section">
                <h4>位置与方向</h4>
                <div class="detail-item">
                  <span class="label">位置:</span>
                  <span class="value">{{ selectedRobot.position?.x || 0 }}，{{ selectedRobot.position?.y || 0 }}，{{
                    selectedRobot.position?.h || 0 }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">方向:</span>
                  <span class="value">{{ selectedRobot.direction || 0 }}°</span>
                </div>
                <div class="detail-item">
                  <span class="label">目标距离:</span>
                  <span class="value">{{ selectedRobot.tgt_distance || 0 }}mm</span>
                </div>
              </div>

              <div class="detail-section">
                <h4>系统信息</h4>
                <div class="detail-item">
                  <span class="label">版本:</span>
                  <span class="value">{{ selectedRobot.version || '未知' }} - {{ sshConfig.password }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">滚筒状态码:</span>
                  <span class="value">{{ selectedRobot.roller_status_code || 0 }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">POD ID:</span>
                  <span class="value">{{ selectedRobot.pod?.id || '无' }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">POD绑定:</span>
                  <span class="value">{{ selectedRobot.pod?.bind || 0 }}</span>
                </div>
                <div class="detail-item">
                  <span class="label">时间:</span>
                  <span class="value">{{ new Date(selectedRobot.time * 1000).toLocaleString() }}</span>
                </div>
              </div>

              <div class="detail-section">
                <h4>其他状态</h4>
                <div class="detail-item">
                  <span class="label">是否变化:</span>
                  <span class="value">{{ selectedRobot.change ? '是' : '否' }}</span>
                </div>
                <NSpace>
                  <NButton @click="freeagv(selectedRobot.RobotId)" type="error">释放</NButton>
                </NSpace>
              </div>

              <div class="detail-section">
                <h4>完整数据</h4>
                <!-- <pre class="pre" style="max-height: 200px; overflow-y: auto;"> -->
                <view-json>{{ JSON.stringify(selectedRobot, null, 2) }}</view-json>
                <!-- </pre> -->
              </div>
            </NScrollbar>
          </NTabPane>
          <NTabPane name="tasks" tab="任务查询">
            <NScrollbar style="max-height: 78vh" trigger="none">
              <TaskDisplayComponent :robot-code="selectedRobot.RobotId" :taskStatus="2" :show-query-params="false"
                :show-details="false" />
            </NScrollbar>
          </NTabPane>
          <NTabPane name="files" tab="文件列表">
            <div class="ssh-panel">
              <SSHComponent v-if="showSSHPanel" :defaultHost="selectedRobot.ip" :defaultUsername="sshConfig.username"
                :defaultPassword="sshConfig.password" :showInput="false" :autoConnect="true" />
            </div>
          </NTabPane>

        </NTabs>
      </div>
    </NDrawer>

    <!-- 添加异常记录模态框 -->
    <n-modal v-model:show="showAddExceptionModal" preset="dialog" title="添加异常记录" :show-icon="false" :closable="true"
      :mask-closable="true" style="width: 500px; max-width: 90vw;">
      <n-form :model="exceptionForm" label-placement="left" label-width="auto">
        <n-form-item label="小车ID">
          <n-input v-model:value="exceptionForm.agv_id" readonly />
        </n-form-item>
        <n-form-item label="问题描述">
          <n-input v-model:value="exceptionForm.problem_description" placeholder="请输入问题描述" />
        </n-form-item>
        <n-form-item label="小车状态">
          <n-input v-model:value="exceptionForm.agv_status" placeholder="请输入小车状态" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="exceptionForm.remarks" type="textarea" placeholder="请输入备注信息" />
        </n-form-item>
      </n-form>
      <template #action>
        <n-space>
          <n-button @click="closeAddExceptionModal">取消</n-button>
          <n-button type="primary" @click="submitExceptionRecord">提交</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>

</template>

<style scoped>
/* 详情区块 */
.detail-section {
  margin-bottom: 24px;
  padding-bottom: 20px;
  border-bottom: 1px solid #e5e5e5;
}

.detail-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.detail-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

/* 详情项 */
.detail-item {
  display: flex;
  flex-wrap: wrap;
  margin-bottom: 8px;
  font-size: 13px;
}

.detail-item .label {
  width: 80px;
  font-weight: 500;
  color: #666;
  margin-right: 12px;
  flex-shrink: 0;
}

.detail-item .value {
  flex: 1;
  min-width: 0;
  color: #333;
  word-break: break-word;
}

/* ackground-color: #f5f5f7;
  padding: 10px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 12px;
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
}

@media (max-width: 768px) {
  /* 移动端详情页样式优化 */
.detail-item {
  font-size: 12px;
  margin-bottom: 6px;
}

.detail-item .label {
  width: 70px;
  margin-right: 8px;
}

.detail-section h4 {
  font-size: 13px;
  margin-bottom: 10px;
}

.pre {
  font-size: 11px;
  padding: 8px;
  max-height: 150px;
}

/* 调整详情抽屉内边距 */
.detail-drawer-content {
  padding: 12px;
}

/* 调整机器人ID标题大小 */
.detail-drawer-content h1 {
  font-size: 20px;
  margin-bottom: 16px;
}


/* 卡片样式 */
:deep(.n-card) {
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* 表格样式 */
:deep(.n-table-tr) {
  transition: background-color 0.2s;
}

:deep(.n-table-tr:hover) {
  background-color: rgba(0, 0, 0, 0.02);
}

/* 表格容器，确保移动端可以水平滚动 */
:deep(.n-data-table) {
  overflow-x: auto;
  width: 100%;
  white-space: nowrap;
}

/* 机器人ID容器样式 */
.robot-id-container {
  white-space: pre-line;
  line-height: 1.4;
  font-size: 12px;
}

/* 防止表格文字竖排显示 */
:deep(.n-table-th__content) {
  white-space: nowrap;
  transform: none !important;
  writing-mode: initial !important;
  text-orientation: initial !important;
}

/* 设置表格列最小宽度，防止过度压缩 */
:deep(.n-table-th),
:deep(.n-table-td) {
  min-width: 80px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 主内容区域 */
.main-container {
  min-height: 100vh;
  padding: 3px;
  background-color: transparent !important;
}

@media (max-width: 768px) {
  .main-container {
    padding: 5px;
  }

  /* 移动端表格样式优化 */
  :deep(.n-table) {
    font-size: 12px;
  }

  /* 表格单元格内边距调整 */
  :deep(.n-table-th),
  :deep(.n-table-td) {
    padding: 8px 4px;
  }

  /* 调整操作按钮大小 */
  :deep(.n-button) {
    font-size: 12px;
    padding: 4px 8px;
  }

  /* 标签页样式优化 */
  :deep(.n-tabs) {
    font-size: 12px;
  }

  /* 标题样式优化 */
  :deep(.n-card__header) {
    font-size: 14px;
  }
}

/* 针对小屏手机的额外优化 */
@media (max-width: 480px) {

  /* 进一步减小表格字体大小 */
  :deep(.n-table) {
    font-size: 11px;
  }

  /* 进一步调整表格单元格内边距 */
  :deep(.n-table-th),
  :deep(.n-table-td) {
    padding: 6px 3px;
  }

  /* 调整卡片标题大小 */
  :deep(.n-card__header) {
    font-size: 13px;
  }

  /* 调整标签页大小 */
  :deep(.n-tabs) {
    font-size: 11px;
  }

  /* 调整标签大小 */
  :deep(.n-tag) {
    font-size: 11px;
    padding: 2px 6px;
  }

  /* 调整按钮大小 */
  :deep(.n-button) {
    font-size: 11px;
    padding: 3px 6px;
  }

  /* 调整详情页样式 */
  .detail-item {
    font-size: 11px;
  }

  .detail-item .label {
    width: 65px;
  }

  /* 调整加载状态和提示文本大小 */
  :deep(.n-text) {
    font-size: 12px;
  }

  /* 调整卡片边距 */
  :deep(.n-card) {
    margin: 0;
  }

  /* 调整标签页头部边距 */
  :deep(.n-tabs__header) {
    margin-bottom: 10px;
  }

  /* 调整卡片内容区域边距 */
  :deep(.n-card__content) {
    padding: 12px;
  }

  /* 调整抽屉头部样式 */
  :deep(.n-drawer__header) {
    padding: 12px 16px;
  }

  /* 调整抽屉标题大小 */
  :deep(.n-drawer__title) {
    font-size: 14px;
  }

  /* SSH面板样式 */
  .ssh-panel {
    height: calc(100vh - 150px);
    /* 调整高度以适应抽屉 */
    overflow-y: auto;
  }
}

/* 针对超大屏幕的优化 */
@media (min-width: 1200px) {

  /* 限制卡片最大宽度，确保在大屏幕上有良好的阅读体验 */
  :deep(.n-card) {
    max-width: 1400px;
    margin: 0 auto;
  }
}

input[aria-hidden="true"] {
  display: none !important;
}

.settings-drawer-content {
  padding: 12px;
}

/* 暗色模式样式 */
[data-theme='dark'] .main-container {
  background-color: #1f1f1f;
}

[data-theme='dark'] :deep(.n-card) {
  background-color: #1f1f1f;
  border: 1px solid #333;
}

[data-theme='dark'] :deep(.n-tabs__header) {
  border-color: #333;
}

[data-theme='dark'] :deep(.n-tabs__tab) {
  color: rgba(255, 255, 255, 0.8);
}

[data-theme='dark'] :deep(.n-tabs__tab--active) {
  color: #1890ff;
  background-color: rgba(0, 0, 0, 0.2);
}

[data-theme='dark'] :deep(.n-data-table) {
  background-color: #1f1f1f;
}

[data-theme='dark'] :deep(.n-table-th) {
  background-color: #2a2a2a;
  color: rgba(255, 255, 255, 0.8);
  border-bottom: 1px solid #333;
}

[data-theme='dark'] :deep(.n-table-td) {
  border-bottom: 1px solid #333;
}

[data-theme='dark'] :deep(.n-table-tr:hover) {
  background-color: rgba(255, 255, 255, 0.05);
}

[data-theme='dark'] .detail-section {
  border-bottom: 1px solid #333;
}

[data-theme='dark'] .detail-section h4 {
  color: rgba(255, 255, 255, 0.8);
}

[data-theme='dark'] .detail-item .label {
  color: rgba(255, 255, 255, 0.6);
}

[data-theme='dark'] .detail-item .value {
  color: rgba(255, 255, 255, 0.8);
}

[data-theme='dark'] :deep(.n-drawer) {
  background-color: #1f1f1f;
}

[data-theme='dark'] :deep(.n-drawer__header) {
  border-bottom: 1px solid #333;
}

[data-theme='dark'] :deep(.n-drawer__title) {
  color: rgba(255, 255, 255, 0.8);
}

[data-theme='dark'] :deep(.n-form-item-label) {
  color: rgba(255, 255, 255, 0.8);
}

[data-theme='dark'] :deep(.n-drawer-content) {
  color: rgba(255, 255, 255, 0.8);
}
</style>