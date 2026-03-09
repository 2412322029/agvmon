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
        default: 800
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
const pendingDraw = ref(false)
const selectedRobot = ref(null)

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

// 内部地图渲染函数
const renderMapLayerInternal = (ctx, width, height) => {
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
        const points = mapRet.Point || mapRet.points || []
        if (points.length < 3) return

        const pixelPoints = points.map(point => {
            const x = point.xpos || point['@xpos']
            const y = point.ypos || point['@ypos']
            return coordToPixel(Number(x), Number(y))
        })

        ctx.beginPath()
        ctx.moveTo(pixelPoints[0].x, pixelPoints[0].y)
        for (let i = 1; i < pixelPoints.length; i++) {
            ctx.lineTo(pixelPoints[i].x, pixelPoints[i].y)
        }
        ctx.closePath()

        const area = mapRet.Area || mapRet.area
        const r = area.color_r || area['@color_r']
        const g = area.color_g || area['@color_g']
        const b = area.color_b || area['@color_b']
        const a = area.color_a || area['@color_a']
        ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${a / 255})`
        ctx.fill()

        ctx.strokeStyle = '#000000'
        ctx.lineWidth = 1
        ctx.stroke()
    })

    // 绘制文本标签
    retNameList.forEach(retName => {
        const startX = retName.start_x || retName['@start_x']
        const endX = retName.end_x || retName['@end_x']
        const startY = retName.start_y || retName['@start_y']
        const endY = retName.end_y || retName['@end_y']
        const centerX = (Number(startX) + Number(endX)) / 2
        const centerY = (Number(startY) + Number(endY)) / 2
        const { x, y } = coordToPixel(centerX, centerY)

        const r = retName.font_color_r || retName['@font_color_r']
        const g = retName.font_color_g || retName['@font_color_g']
        const b = retName.font_color_b || retName['@font_color_b']
        const a = retName.font_color_a || retName['@font_color_a']
        const size = (retName.size || retName['@size'])/2
        const font = retName.font || retName['@font']

        const fontSize = Math.max(10, Math.min(30, (size || 16) * scale.value * 0.3))

        ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${a / 255})`
        ctx.font = `${fontSize}px ${font}`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'

        const text = retName.text || retName['#text']
        ctx.fillText(text, x, y)
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
    
    // 使用实时渲染以支持缩放和偏移
    renderMapLayerInternal(ctx, canvas.width, canvas.height)
}

// 绘制网格参考线
const drawGridLines = (ctx, width, height) => {
    const { minX, maxX, minY, maxY } = mapBounds.value
    
    // 计算网格间距
    const rangeX = maxX - minX
    const rangeY = maxY - minY
    const mapDiagonal = Math.sqrt(rangeX * rangeX + rangeY * rangeY)
    
    // 根据地图大小和缩放比例确定网格间距
    let gridSize = 100
    if (mapDiagonal > 2000) gridSize = 500
    else if (mapDiagonal > 1000) gridSize = 200
    
    // 计算网格线数量
    const xLines = Math.ceil(rangeX / gridSize)
    const yLines = Math.ceil(rangeY / gridSize)
    
    // 只在缩放比例较大时显示网格
    if (scale.value > 0.8) {
        ctx.save()
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.1)'
        ctx.lineWidth = 1
        ctx.setLineDash([5, 5])
        
        // 绘制垂直线
        for (let i = 0; i <= xLines; i++) {
            const x = minX + i * gridSize
            const { x: pixelX } = coordToPixel(x, minY)
            if (pixelX >= -50 && pixelX <= width + 50) {
                ctx.beginPath()
                ctx.moveTo(pixelX, 0)
                ctx.lineTo(pixelX, height)
                ctx.stroke()
                
                // 绘制X坐标标签
                if (scale.value > 1.5) {
                    ctx.fillStyle = 'rgba(0, 0, 0, 0.5)'
                    ctx.font = '10px Arial'
                    ctx.textAlign = 'center'
                    ctx.textBaseline = 'top'
                    ctx.fillText(Math.round(x), pixelX, height - 20)
                }
            }
        }
        
        // 绘制水平线
        for (let j = 0; j <= yLines; j++) {
            const y = minY + j * gridSize
            const { y: pixelY } = coordToPixel(minX, y)
            if (pixelY >= -50 && pixelY <= height + 50) {
                ctx.beginPath()
                ctx.moveTo(0, pixelY)
                ctx.lineTo(width, pixelY)
                ctx.stroke()
                
                // 绘制Y坐标标签
                if (scale.value > 1.5) {
                    ctx.fillStyle = 'rgba(0, 0, 0, 0.5)'
                    ctx.font = '10px Arial'
                    ctx.textAlign = 'right'
                    ctx.textBaseline = 'middle'
                    ctx.fillText(Math.round(y), width - 20, pixelY)
                }
            }
        }
        
        ctx.restore()
    }
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
        const baseRobotSize = 30 
        // 基于缩放比例动态调整，但设置最大最小限制
        const scaledRobotSize = Math.max(20, Math.min(40, baseRobotSize * scale.value))
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
                { x: -10, y: 10 },  
                { x: -10, y: -10 }, 
                { x: 10, y: 10 },   
                { x: 10, y: -10 }   
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
        ctx.font = `${12}px Arial`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.fillText(robot.RobotId, x, y + 25)
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
    
    const canvas = robotCanvasRef.value
    if (!canvas) return
    
    const rect = canvas.getBoundingClientRect()
    const mouseX = e.clientX - rect.left
    const mouseY = e.clientY - rect.top
    
    // 计算鼠标位置在地图上的坐标
    const mapX = (mouseX - canvas.width / 2 - offsetX.value) / scale.value + (mapBounds.value.minX + mapBounds.value.maxX) / 2
    const mapY = (canvas.height / 2 + offsetY.value - mouseY) / scale.value + (mapBounds.value.minY + mapBounds.value.maxY) / 2
    
    const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1
    const newScale = scale.value * zoomFactor
    
    // 计算缩放后需要调整的偏移量，使鼠标位置保持不变
    offsetX.value = mouseX - canvas.width / 2 - (mapX - (mapBounds.value.minX + mapBounds.value.maxX) / 2) * newScale
    offsetY.value = mouseY - canvas.height / 2 + (mapY - (mapBounds.value.minY + mapBounds.value.maxY) / 2) * newScale
    
    scale.value = newScale

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
            const newScale = scale.value * scaleFactor
            
            // 计算双指中心点
            const canvas = robotCanvasRef.value
            if (canvas) {
                const rect = canvas.getBoundingClientRect()
                const touch1X = e.touches[0].clientX - rect.left
                const touch1Y = e.touches[0].clientY - rect.top
                const touch2X = e.touches[1].clientX - rect.left
                const touch2Y = e.touches[1].clientY - rect.top
                const centerX = (touch1X + touch2X) / 2
                const centerY = (touch1Y + touch2Y) / 2
                
                // 计算中心点在地图上的坐标
                const mapX = (centerX - canvas.width / 2 - offsetX.value) / scale.value + (mapBounds.value.minX + mapBounds.value.maxX) / 2
                const mapY = (canvas.height / 2 + offsetY.value - centerY) / scale.value + (mapBounds.value.minY + mapBounds.value.maxY) / 2
                
                // 计算缩放后需要调整的偏移量，使中心点保持不变
                offsetX.value = centerX - canvas.width / 2 - (mapX - (mapBounds.value.minX + mapBounds.value.maxX) / 2) * newScale
                offsetY.value = centerY - canvas.height / 2 + (mapY - (mapBounds.value.minY + mapBounds.value.maxY) / 2) * newScale
            }
            
            scale.value = newScale
            
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
    const fitScale = Math.min(xScale, yScale) * 0.9 
    
    // 设置缩放比例，确保初始大小合适，最小缩放比例为0.5
    const minScale = 0.5
    scale.value = Math.max(minScale, fitScale)
}

// 缩放控制
const zoomIn = () => {
    scale.value = scale.value * 1.2
}

const zoomOut = () => {
    scale.value = scale.value / 1.2
}

const resetView = () => {

    centerMap()    
    scale.value = 3
    offsetX.value = 0
    offsetY.value = 0
}

// 点击机器人处理
const handleCanvasClick = (e) => {
    const canvas = robotCanvasRef.value
    if (!canvas) return
    
    const rect = canvas.getBoundingClientRect()
    const clickX = e.clientX - rect.left
    const clickY = e.clientY - rect.top
    
    // 遍历机器人，检查是否点击了某个机器人
    for (const robot of props.robots) {
        if (!robot.position) continue
        
        const { x, y } = coordToPixel(robot.position.x, robot.position.y)
        const baseRobotSize = 30 
        const scaledRobotSize = Math.max(20, Math.min(40, baseRobotSize * scale.value))
        const robotSize = scaledRobotSize
        
        // 计算点击点与机器人中心的距离
        const dx = clickX - x
        const dy = clickY - y
        const distance = Math.sqrt(dx * dx + dy * dy)
        
        // 如果点击在机器人范围内
        if (distance < robotSize / 2 + 10) {
            selectedRobot.value = robot
            break
        }
    }
}

// 关闭详情
const closeRobotDetail = () => {
    selectedRobot.value = null
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
    
    // 计算地图中心点
    const centerX = (maxX + minX) / 2
    const centerY = (maxY + minY) / 2
    
    // 计算合适的缩放比例（使机器人清晰可见）
    const xScale = canvasWidth / (maxX - minX)
    const yScale = canvasHeight / (maxY - minY)
    const fitScale = Math.min(xScale, yScale) * 0.9
    
    // 设置缩放比例，确保机器人清晰可见
    const minScale = 7
    scale.value = Math.max(minScale, fitScale)
    
    // 计算机器人在画布上的目标位置（画布中心）
    const targetPixelX = canvasWidth / 2
    const targetPixelY = canvasHeight / 2
    
    // 计算机器人在当前缩放下的像素位置（相对于地图中心）
    const usedScale = Math.min(xScale, yScale) * scale.value
    const pixelXFromCenter = (robotX - centerX) * usedScale
    const pixelYFromCenter = -(robotY - centerY) * usedScale
    
    // 计算需要的偏移量，使机器人位于画布中心
    offsetX.value = targetPixelX - (canvasWidth / 2) - pixelXFromCenter
    offsetY.value = targetPixelY - (canvasHeight / 2) - pixelYFromCenter
    
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
            @touchcancel="handleTouchEnd" @click="handleCanvasClick"
            style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: pointer; -webkit-tap-highlight-color: transparent;" />
        
        <!-- 地图导航控件 -->
        <div class="map-controls">
            <button class="map-control-btn zoom-in" @click="zoomIn" title="放大">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="8"></circle>
                    <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                    <line x1="11" y1="8" x2="11" y2="14"></line>
                    <line x1="8" y1="11" x2="14" y2="11"></line>
                </svg>
            </button>
            <button class="map-control-btn zoom-out" @click="zoomOut" title="缩小">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="8"></circle>
                    <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                    <line x1="8" y1="11" x2="14" y2="11"></line>
                </svg>
            </button>
            <button class="map-control-btn reset" @click="resetView" title="重置视图">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
                    <path d="M3 3v5h5"></path>
                </svg>
            </button>
        </div>
    </div>
    
    <!-- 机器人详情弹窗 -->
    <div v-if="selectedRobot" class="robot-detail-overlay" @click="closeRobotDetail">
        <div class="robot-detail-modal" @click.stop>
            <div class="robot-detail-header">
                <h3>{{ selectedRobot.RobotId }}</h3>
                <button class="close-btn" @click="closeRobotDetail">×</button>
            </div>
            <div class="robot-detail-body">
                <div class="detail-item">
                    <span class="label">状态:</span>
                    <span class="value">{{ selectedRobot.status || '未知' }}</span>
                </div>
                <div class="detail-item">
                    <span class="label">位置 X:</span>
                    <span class="value">{{ selectedRobot.position?.x || 'N/A' }}</span>
                </div>
                <div class="detail-item">
                    <span class="label">位置 Y:</span>
                    <span class="value">{{ selectedRobot.position?.y || 'N/A' }}</span>
                </div>
                <div class="detail-item">
                    <span class="label">方向:</span>
                    <span class="value">{{ selectedRobot.direction || 0 }}°</span>
                </div>
                <div class="detail-item">
                    <span class="label">滚筒状态:</span>
                    <span class="value">{{ selectedRobot.roller_status_code || 'N/A' }}</span>
                </div>
                <div class="detail-item">
                    <span class="label">电池电量:</span>
                    <span class="value">{{ selectedRobot.battery || 'N/A' }}%</span>
                </div>
            </div>
        </div>
    </div>
</template>
<style scoped>
.map-component-container {
    position: relative;
    display: inline-block;
    max-width: 100%;
    max-height: 100vh;
    overflow: hidden; /* 隐藏滚动条，使用拖拽和缩放来导航 */
    height: 100%; /* 自适应高度 */
    /* min-height: 500px;  */
    touch-action: none; /* 禁用浏览器默认触摸行为 */
    user-select: none; /* 禁用文本选择 */
    background-color: aliceblue;
}

/* 搜索框样式 */
.map-search-container {
    position: absolute;
    top: 10px;
    left: 10px;
    z-index: 1000; /* 确保在地图之上 */
    display: flex;
    gap: 5px;
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

/* 地图导航控件样式 */
.map-controls {
    position: absolute;
    top: 10px;
    right: 10px;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 5px;
    padding: 5px;
    border-radius: 4px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    background-color: white;
}

.map-control-btn {
    width: 36px;
    height: 36px;
    padding: 0;
    border: 1px solid #ccc;
    border-radius: 4px;
    background-color: white;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s;
    color: #333;
}

.map-control-btn:hover {
    background-color: #f5f5f5;
    border-color: #999;
}

.map-control-btn:active {
    background-color: #e0e0e0;
}

.robot-detail-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.5);
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
}

.robot-detail-modal {
    background-color: white;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    width: 300px;
    max-width: 90%;
    overflow: hidden;
}

.robot-detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px;
    border-bottom: 1px solid #eee;
}

.robot-detail-header h3 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: #333;
}

.close-btn {
    background: none;
    border: none;
    font-size: 24px;
    cursor: pointer;
    color: #999;
    line-height: 1;
    padding: 0;
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    transition: all 0.3s;
}

.close-btn:hover {
    background-color: #f5f5f5;
    color: #333;
}

.robot-detail-body {
    padding: 16px;
}

.detail-item {
    display: flex;
    justify-content: space-between;
    padding: 10px 0;
    border-bottom: 1px solid #f0f0f0;
}

.detail-item:last-child {
    border-bottom: none;
}

.detail-item .label {
    color: #666;
    font-size: 14px;
}

.detail-item .value {
    color: #333;
    font-weight: 500;
    font-size: 14px;
}

/* 响应式设计，针对移动端优化 */
@media (max-width: 768px) {
    .map-component-container {
        max-height: 70vh; 
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
    
    .map-controls {
        top: auto;
        bottom: 10px;
        flex-direction: row;
    }
    
    .robot-detail-modal {
        width: 90%;
    }
}
</style>