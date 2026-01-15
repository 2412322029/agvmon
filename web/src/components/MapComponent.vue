<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

// 地图数据
const props = defineProps({
    mapData: {
        type: Object,
        default: () => ({ map_ret_list: [], ret_name_list: [] })
    },
    robots: {
        type: Array,
        default: () => []
    },
    width: {
        type: [Number, String],
        default: 800
    },
    height: {
        type: [Number, String],
        default: 600
    },
    // 搜索参数，用于定位特定机器人
    searchRobotId: {
        type: String,
        default: ''
    }
})

// Canvas引用
const mapCanvasRef = ref(null)
const robotCanvasRef = ref(null)

// 地图状态
const scale = ref(1)
const offsetX = ref(0)
const offsetY = ref(0)
const isDragging = ref(false)
const lastMousePos = ref({ x: 0, y: 0 })

// 触摸事件状态
const isTouching = ref(false)
const lastTouchPos = ref({ x: 0, y: 0 })
const lastTouchDistance = ref(0)

// 搜索相关状态
const searchInput = ref('')

// 图片缓存
const imageCache = {
    robotImg: null,
    robotFullImg: null
}

// 计算实际画布尺寸
const canvasSize = computed(() => {
    let actualWidth = props.width
    let actualHeight = props.height
    
    // 处理百分比宽度
    if (typeof actualWidth === 'string' && actualWidth.includes('%')) {
        // 获取父容器的实际宽度
        if (mapCanvasRef.value) {
            const parentElement = mapCanvasRef.value.parentElement
            if (parentElement) {
                const parentWidth = parentElement.clientWidth
                const widthPercent = parseFloat(actualWidth)
                actualWidth = (parentWidth * widthPercent) / 100
            }
        }
    }
    
    // 处理百分比高度
    if (typeof actualHeight === 'string' && actualHeight.includes('%')) {
        // 获取父容器的实际高度
        if (mapCanvasRef.value) {
            const parentElement = mapCanvasRef.value.parentElement
            if (parentElement) {
                const parentHeight = parentElement.clientHeight
                const heightPercent = parseFloat(actualHeight)
                actualHeight = (parentHeight * heightPercent) / 100
            }
        }
    }
    
    // 确保是数字类型
    actualWidth = Number(actualWidth) || 800
    actualHeight = Number(actualHeight) || 600
    
    return { width: actualWidth, height: actualHeight }
})

// 预加载图片
const preloadImages = async () => {
    const origin = window.location.origin
    const robotImgUrl = `${origin}/api/robot_img/online.png`
    const robotFullImgUrl = `${origin}/api/robot_img/full.png`

    // 预加载机器人图片
    imageCache.robotImg = await loadImage(robotImgUrl)
    imageCache.robotFullImg = await loadImage(robotFullImgUrl)
}

// 图片加载函数
const loadImage = (url) => {
    return new Promise((resolve) => {
        const img = new Image()
        img.src = url
        img.onload = () => resolve(img)
        img.onerror = () => resolve(null)
    })
}

// 计算地图的边界
const mapBounds = computed(() => {
    // 获取地图区域数据，支持多种数据格式
    const mapRetList = props.mapData?.map_ret_list ||
        props.mapData?.MapRetCfg?.MapRet ||
        []

    // 获取文本标签数据，支持多种数据格式
    const retNameList = props.mapData?.ret_name_list ||
        props.mapData?.MapRetCfg?.RetName ||
        []

    if (mapRetList.length === 0) {
        return { minX: 0, maxX: 1000, minY: 0, maxY: 1000 }
    }

    let minX = Infinity
    let maxX = -Infinity
    let minY = Infinity
    let maxY = -Infinity

    // 处理地图区域数据
    mapRetList.forEach(mapRet => {
        const points = mapRet.Point || mapRet.points || []
        points.forEach(point => {
            const x = point.xpos || point['@xpos']
            const y = point.ypos || point['@ypos']
            minX = Math.min(minX, Number(x))
            maxX = Math.max(maxX, Number(x))
            minY = Math.min(minY, Number(y))
            maxY = Math.max(maxY, Number(y))
        })
    })

    // 处理文本标签数据
    retNameList.forEach(retName => {
        const startX = retName.start_x || retName['@start_x']
        const endX = retName.end_x || retName['@end_x']
        const startY = retName.start_y || retName['@start_y']
        const endY = retName.end_y || retName['@end_y']

        minX = Math.min(minX, Number(startX), Number(endX))
        maxX = Math.max(maxX, Number(startX), Number(endX))
        minY = Math.min(minY, Number(startY), Number(endY))
        maxY = Math.max(maxY, Number(startY), Number(endY))
    })

    // 添加一些边距
    const padding = (maxX - minX) * 0.1
    minX -= padding
    maxX += padding
    minY -= padding
    maxY += padding

    return { minX, maxX, minY, maxY }
})

// 将地图坐标转换为Canvas坐标
const coordToPixel = (x, y) => {
    const { minX, maxX, minY, maxY } = mapBounds.value
    const { width: canvasWidth, height: canvasHeight } = canvasSize.value

    // 计算比例
    const xScale = canvasWidth / (maxX - minX)
    const yScale = canvasHeight / (maxY - minY)
    const usedScale = Math.min(xScale, yScale) * scale.value

    // 计算中心点偏移
    const centerX = (maxX + minX) / 2
    const centerY = (maxY + minY) / 2
    const canvasCenterX = canvasWidth / 2 + offsetX.value
    const canvasCenterY = canvasHeight / 2 + offsetY.value

    // 转换坐标
    const pixelX = canvasCenterX + (x - centerX) * usedScale
    const pixelY = canvasCenterY - (y - centerY) * usedScale // Y轴翻转

    return { x: pixelX, y: pixelY }
}

// 绘制地图层（只绘制地图和文本标签，不绘制机器人）
const drawMapLayer = () => {
    if (!mapCanvasRef.value) return

    const canvas = mapCanvasRef.value
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // 清空画布
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // 获取地图区域数据，支持多种数据格式
    const mapRetList = props.mapData?.map_ret_list ||
        props.mapData?.MapRetCfg?.MapRet ||
        []

    // 获取文本标签数据，支持多种数据格式
    const retNameList = props.mapData?.ret_name_list ||
        props.mapData?.MapRetCfg?.RetName ||
        []

    // 绘制地图区域
    mapRetList.forEach(mapRet => {
        // 处理不同格式的点数据
        const points = mapRet.Point || mapRet.points || []
        if (points.length < 3) return

        // 转换点坐标，支持两种格式：{xpos, ypos} 和 {@xpos, @ypos}
        const pixelPoints = points.map(point => {
            const x = point.xpos || point['@xpos']
            const y = point.ypos || point['@ypos']
            return coordToPixel(Number(x), Number(y))
        })

        // 绘制多边形
        ctx.beginPath()
        ctx.moveTo(pixelPoints[0].x, pixelPoints[0].y)
        for (let i = 1; i < pixelPoints.length; i++) {
            ctx.lineTo(pixelPoints[i].x, pixelPoints[i].y)
        }
        ctx.closePath()

        // 设置填充颜色，支持两种格式：{color_r, color_g, color_b, color_a} 和 {@color_r, @color_g, @color_b, @color_a}
        const area = mapRet.Area || mapRet.area
        const r = area.color_r || area['@color_r']
        const g = area.color_g || area['@color_g']
        const b = area.color_b || area['@color_b']
        const a = area.color_a || area['@color_a']
        ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${a / 255})`
        ctx.fill()

        // 设置边框颜色
        ctx.strokeStyle = '#000000'
        ctx.lineWidth = 1
        ctx.stroke()
    })

    // 绘制文本标签
    retNameList.forEach(retName => {
        // 计算文本位置（中心），支持两种格式：{start_x, end_x} 和 {@start_x, @end_x}
        const startX = retName.start_x || retName['@start_x']
        const endX = retName.end_x || retName['@end_x']
        const startY = retName.start_y || retName['@start_y']
        const endY = retName.end_y || retName['@end_y']
        const centerX = (Number(startX) + Number(endX)) / 2
        const centerY = (Number(startY) + Number(endY)) / 2
        const { x, y } = coordToPixel(centerX, centerY)

        // 设置文本样式，支持两种格式：{font_color_r, font_color_g, font_color_b, font_color_a} 和 {@font_color_r, @font_color_g, @font_color_b, @font_color_a}
        const r = retName.font_color_r || retName['@font_color_r']
        const g = retName.font_color_g || retName['@font_color_g']
        const b = retName.font_color_b || retName['@font_color_b']
        const a = retName.font_color_a || retName['@font_color_a']
        const size = (retName.size || retName['@size'])/2
        const font = retName.font || retName['@font']

        // 调整字体大小，使其更加合适（原大小的0.2倍）
        const fontSize = Math.max(4, Math.min(20, (size || 16) * scale.value * 0.2))

        ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${a / 255})`
        ctx.font = `${fontSize}px ${font}`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'

        // 绘制文本，支持两种格式：{text} 和 {#text}
        const text = retName.text || retName['#text']
        ctx.fillText(text, x, y)
    })
}

// 绘制机器人层（只绘制机器人，不绘制地图）
const drawRobotLayer = () => {
    if (!robotCanvasRef.value) return

    const canvas = robotCanvasRef.value
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // 清空画布
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // 绘制机器人
    props.robots.forEach(robot => {
        if (!robot.position) return

        const { x, y } = coordToPixel(robot.position.x, robot.position.y)
        const direction = robot.direction || 0
        // 缩小小车基础大小并添加基于缩放的动态调整
        const baseRobotSize = 20 // 从40缩小到20
        // 基于缩放比例动态调整，但设置最大最小限制
        const scaledRobotSize = Math.max(10, Math.min(20, baseRobotSize * scale.value))
        const robotSize = scaledRobotSize

        // 绘制机器人图片
        ctx.save()
        ctx.translate(x, y)
        ctx.rotate((direction * Math.PI) / 180)

        // 使用预加载的图片（不应用额外缩放，因为坐标转换已经包含了缩放）
        if (imageCache.robotImg) {
            ctx.drawImage(imageCache.robotImg, -robotSize / 2, -robotSize / 2, robotSize, robotSize)
        }

        ctx.restore()

        // 绘制负载指示器（如果有负载）
        if (robot.roller_status_code && imageCache.robotFullImg) {
            // 解析滚筒状态码，获取负载信息
            const rollerStatus = String(robot.roller_status_code).slice(-4).padStart(4, '0')
            const hasLoads = rollerStatus.split('').map(digit => digit === '1')

            // 绘制四个负载指示器
            const indicatorSize = 6
            const offsets = [
                { x: -10, y: 10 },  // 左下
                { x: -10, y: -10 }, // 左上
                { x: 10, y: 10 },   // 右下
                { x: 10, y: -10 }   // 右上
            ]

            hasLoads.forEach((hasLoad, index) => {
                if (hasLoad) {
                    const offset = offsets[index]
                    const indicatorX = x + offset.x
                    const indicatorY = y + offset.y
                    ctx.drawImage(imageCache.robotFullImg, indicatorX - indicatorSize / 2, indicatorY - indicatorSize / 2, indicatorSize, indicatorSize)
                }
            })
        }

        // 绘制机器人ID
        ctx.fillStyle = '#000000'
        ctx.font = `${8}px Arial`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.fillText(robot.RobotId, x, y + 18)
    })
}

// 统一绘制函数
const drawMap = () => {
    drawMapLayer()
    drawRobotLayer()
}

// 鼠标事件处理
const handleMouseDown = (e) => {
    isDragging.value = true
    lastMousePos.value = { x: e.clientX, y: e.clientY }
}

const handleMouseMove = (e) => {
    if (!isDragging.value) return

    const dx = e.clientX - lastMousePos.value.x
    const dy = e.clientY - lastMousePos.value.y
    offsetX.value += dx
    offsetY.value += dy
    lastMousePos.value = { x: e.clientX, y: e.clientY }

    // 分别绘制两个图层以提高性能
    drawMapLayer()
    drawRobotLayer()
}

const handleMouseUp = () => {
    isDragging.value = false
}

const handleWheel = (e) => {
    e.preventDefault()
    const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1
    // 调整最小缩放比例为0.5，避免地图过小
    scale.value = Math.max(1, Math.min(5, scale.value * zoomFactor))

    // 分别绘制两个图层以提高性能
    drawMapLayer()
    drawRobotLayer()
}

// 计算两个触摸点之间的距离
const getTouchDistance = (touches) => {
    if (touches.length < 2) return 0
    const dx = touches[0].clientX - touches[1].clientX
    const dy = touches[0].clientY - touches[1].clientY
    return Math.sqrt(dx * dx + dy * dy)
}

// 触摸开始事件
const handleTouchStart = (e) => {
    e.preventDefault()
    isTouching.value = true
    
    // 单指触摸用于拖拽
    if (e.touches.length === 1) {
        lastTouchPos.value = {
            x: e.touches[0].clientX,
            y: e.touches[0].clientY
        }
    }
    // 双指触摸用于缩放
    else if (e.touches.length === 2) {
        lastTouchDistance.value = getTouchDistance(e.touches)
    }
}

// 触摸移动事件
const handleTouchMove = (e) => {
    e.preventDefault()
    
    // 单指拖拽
    if (e.touches.length === 1 && isTouching.value) {
        const currentX = e.touches[0].clientX
        const currentY = e.touches[0].clientY
        const dx = currentX - lastTouchPos.value.x
        const dy = currentY - lastTouchPos.value.y
        
        offsetX.value += dx
        offsetY.value += dy
        
        lastTouchPos.value = { x: currentX, y: currentY }
        
        // 重新绘制地图
        drawMapLayer()
        drawRobotLayer()
    }
    // 双指缩放
    else if (e.touches.length === 2) {
        const currentDistance = getTouchDistance(e.touches)
        if (lastTouchDistance.value > 0) {
            const scaleFactor = currentDistance / lastTouchDistance.value
            // 调整最小缩放比例为0.5，避免地图过小
            scale.value = Math.max(0.5, Math.min(5, scale.value * scaleFactor))
            
            // 重新绘制地图
            drawMapLayer()
            drawRobotLayer()
        }
        lastTouchDistance.value = currentDistance
    }
}

// 触摸结束事件
const handleTouchEnd = (e) => {
    e.preventDefault()
    isTouching.value = false
    
    // 重置触摸距离
    if (e.touches.length < 2) {
        lastTouchDistance.value = 0
    }
}

// 监听数据变化，优化渲染性能

// 地图层监听器：仅当地图数据、宽高、缩放或偏移变化时重新渲染地图层
watch(
    () => [props.mapData, props.width, props.height, scale.value, offsetX.value, offsetY.value],
    () => drawMapLayer(),
    { deep: true }
)

// 机器人层监听器：仅当机器人数据或缩放变化时重新渲染机器人层
watch(
    () => [props.robots, scale.value, offsetX.value, offsetY.value],
    () => drawRobotLayer(),
    { deep: true }
)

// 地图自动居中函数
const centerMap = () => {
    // 重置缩放和偏移
    scale.value = 1
    offsetX.value = 0
    offsetY.value = 0
    
    // 获取地图边界
    const { minX, maxX, minY, maxY } = mapBounds.value
    const { width: canvasWidth, height: canvasHeight } = canvasSize.value
    
    // 计算地图尺寸
    const mapWidth = maxX - minX
    const mapHeight = maxY - minY
    
    // 计算合适的缩放比例（使地图适合画布）
    const xScale = canvasWidth / mapWidth
    const yScale = canvasHeight / mapHeight
    const fitScale = Math.min(xScale, yScale) * 0.9 // 留10%边距
    
    // 设置缩放比例，确保初始大小合适
    // 添加最小缩放比例限制，避免地图过小
    const minScale = 0.5 // 最小缩放比例
    const maxScale = 5 // 最大缩放比例
    scale.value = Math.max(minScale, Math.min(maxScale, fitScale))
}

// 定位特定机器人到地图中心
const locateRobot = (robotId) => {
    if (!robotId) return
    
    // 在机器人列表中查找对应ID的机器人
    const robot = props.robots.find(r => r.RobotId === robotId)
    if (!robot || !robot.position) return
    
    // 获取机器人在地图中的坐标
    const robotX = robot.position.x
    const robotY = robot.position.y
    
    // 获取地图边界
    const { minX, maxX, minY, maxY } = mapBounds.value
    const { width: canvasWidth, height: canvasHeight } = canvasSize.value
    
    // 计算当前缩放比例下的地图尺寸
    const usedScale = scale.value
    
    // 计算机器人在画布上的当前位置
    const currentPixelPos = coordToPixel(robotX, robotY)
    
    // 计算需要的偏移量，使机器人位于画布中心
    offsetX.value += (canvasWidth / 2) - currentPixelPos.x
    offsetY.value += (canvasHeight / 2) - currentPixelPos.y
    
    // 调整缩放比例，使机器人更清晰可见
    // 放大到合适大小，最大不超过5
    // const targetScale = Math.min(2, scale.value * 1.5)
    scale.value = 4
    
    // 重新绘制地图
    drawMapLayer()
    drawRobotLayer()
}

// 处理搜索输入变化
const handleSearchInputChange = (e) => {
    searchInput.value = e.target.value
}

// 处理搜索提交
const handleSearchSubmit = () => {
    if (searchInput.value.trim()) {
        locateRobot(searchInput.value.trim())
    }
}

// 处理键盘事件（回车键搜索）
const handleSearchKeyDown = (e) => {
    if (e.key === 'Enter') {
        handleSearchSubmit()
    }
}

// 监听搜索参数变化，自动定位机器人
watch(
    () => props.searchRobotId,
    (newRobotId) => {
        if (newRobotId) {
            // 延迟执行，确保DOM已更新
            nextTick(() => {
                locateRobot(newRobotId)
            })
        }
    },
    { immediate: true }
)

// 监听地图数据变化，自动居中
watch(
    () => props.mapData,
    () => {
        // 延迟执行，确保地图数据已完全加载
        nextTick(() => {
            centerMap()
        })
    },
    { deep: true, immediate: true }
)

onMounted(async () => {
    // 预加载图片
    await preloadImages()
    // 自动居中地图
    centerMap()
    // 绘制地图
    drawMap()
    scale.value = 2
    // 添加窗口大小变化监听
    window.addEventListener('resize', handleResize)
})

// 窗口大小变化处理
const handleResize = () => {
    // 延迟执行，确保DOM已更新
    nextTick(() => {
        // 重新计算地图居中
        centerMap()
    })
}

// 组件卸载时移除事件监听
onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
})
</script>

<template>
    <div class="map-component-container">
        <!-- 搜索框 -->
        <div class="map-search-container">
            <input 
                type="text" 
                v-model="searchInput" 
                placeholder="搜索机器人ID" 
                class="map-search-input"
                @input="handleSearchInputChange"
                @keydown="handleSearchKeyDown"
            />
            <button 
                class="map-search-button"
                @click="handleSearchSubmit"
            >
                搜索
            </button>
        </div>
        
        <!-- 地图层（底层） -->
        <canvas 
            ref="mapCanvasRef" 
            :width="canvasSize.width" 
            :height="canvasSize.height"
            style="top: 0; left: 0; border: 1px solid #ccc; cursor: move; width: 100%; height: auto;" 
        />

        <!-- 机器人层（顶层） -->
        <canvas 
            ref="robotCanvasRef" 
            :width="canvasSize.width" 
            :height="canvasSize.height" 
            @mousedown="handleMouseDown"
            @mousemove="handleMouseMove" @mouseup="handleMouseUp" @mouseleave="handleMouseUp" @wheel="handleWheel"
            style="position: absolute; top: 0; left: 0; cursor: move; pointer-events: none; width: 100%; height: auto;" 
        />

        <!-- 交互层（顶层，用于接收鼠标和触摸事件） -->
        <div class="interaction-layer" @mousedown="handleMouseDown" @mousemove="handleMouseMove"
            @mouseup="handleMouseUp" @mouseleave="handleMouseUp" @wheel="handleWheel"
            @touchstart="handleTouchStart" @touchmove="handleTouchMove" @touchend="handleTouchEnd"
            @touchcancel="handleTouchEnd"
            style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: move; -webkit-tap-highlight-color: transparent;" />
    </div>
</template>

<style scoped>
.map-component-container {
    position: relative;
    display: inline-block;
    max-width: 100%;
    max-height: 80vh;
    overflow: hidden; /* 隐藏滚动条，使用拖拽和缩放来导航 */
    height: 100%; /* 自适应高度 */
    min-height: 300px; /* 设置最小高度 */
    touch-action: none; /* 禁用浏览器默认触摸行为 */
    user-select: none; /* 禁用文本选择 */
}

/* 搜索框样式 */
.map-search-container {
    position: absolute;
    top: 10px;
    left: 10px;
    z-index: 1000; /* 确保在地图之上 */
    display: flex;
    gap: 5px;
    background: rgba(255, 255, 255, 0.9);
    padding: 5px;
    border-radius: 4px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.map-search-input {
    padding: 8px 12px;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 14px;
    width: 150px;
    outline: none;
    transition: border-color 0.3s;
}

.map-search-input:focus {
    border-color: #409eff;
}

.map-search-button {
    padding: 8px 16px;
    background-color: #409eff;
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 14px;
    cursor: pointer;
    transition: background-color 0.3s;
}

.map-search-button:hover {
    background-color: #66b1ff;
}

/* 响应式设计，针对移动端优化 */
@media (max-width: 768px) {
    .map-component-container {
        max-height: 70vh; /* 在移动端使用更大的屏幕比例 */
    }
    
    .map-search-container {
        top: 5px;
        left: 5px;
        right: 5px;
        flex-direction: column;
        gap: 3px;
    }
    
    .map-search-input {
        width: auto;
    }
    
    .map-search-button {
        padding: 6px 12px;
    }
}
</style>