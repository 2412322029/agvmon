<template>
    <div class="path-show-card" :bordered="true">

        <div class="canvas-container" ref="containerRef">
            <canvas ref="canvasRef" :width="canvasWidth" :height="canvasHeight"></canvas>
            <div v-if="pathPointCount === 0" class="no-data">
                <n-empty description="暂无路径数据" />
            </div>
        </div>

    </div>
    <div class="controls">
        <n-space>
            <n-button-group size="small">
                <n-button @click="zoomIn" :disabled="pathPointCount === 0">
                    放大
                </n-button>
                <n-button @click="zoomOut" :disabled="pathPointCount === 0">
                    缩小
                </n-button>
                <!-- <n-button @click="resetView" :disabled="pathPointCount === 0">
                    重置
                </n-button> -->
                <n-button @click="fitView" :disabled="pathPointCount === 0" title="适应窗口">
                    适应
                </n-button>
                <n-button @click="rotateMap" title="旋转地图">
                    <template #icon>
                        <n-icon :component="Refresh" />
                    </template>
                </n-button>
            </n-button-group>
            <n-text depth="3">缩放: {{ (scale * 100).toFixed(0) }}%</n-text>
            <n-text depth="3">| 点数: {{ pathPointCount }}</n-text>
        </n-space>
    </div>
</template>

<script setup>
import { Refresh } from '@vicons/ionicons5'
import { NButton, NButtonGroup, NEmpty, NIcon, NSpace, NText } from 'naive-ui'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

const STORAGE_KEY = 'pathshow_rotation'
const loadRotation = () => {
    try {
        const saved = localStorage.getItem(STORAGE_KEY)
        return saved ? parseFloat(saved) : 0
    } catch {
        return 0
    }
}

const robotImgUrl = computed(() => location.origin + '/api/robot_img/online.png')
const rotationAngle = ref(loadRotation())

const props = defineProps({
    pathData: {
        type: Object,
        default: () => null
    },
    width: {
        type: [Number, String],
        default: 800
    },
    height: {
        type: [Number, String],
        default: 500
    },
    robotColor: {
        type: String,
        default: '#18a058'
    },
    pathColor: {
        type: String,
        default: '#2080f0'
    },
    showDirection: {
        type: Boolean,
        default: true
    },
    currentPosition: {
        type: Object,
        default: null
    }
})

const canvasRef = ref(null)
const containerRef = ref(null)
const scale = ref(1)
const offsetX = ref(0)
const offsetY = ref(0)
const isDragging = ref(false)
const lastMousePos = ref({ x: 0, y: 0 })
const canvasWidth = ref(800)
const canvasHeight = ref(500)
const isFirstLoad = ref(true)

let ctx = null

const initCanvas = () => {
    if (canvasRef.value) {
        ctx = canvasRef.value.getContext('2d')
        updateCanvasSize()
    }
}

const updateCanvasSize = () => {
    let actualWidth = props.width
    let actualHeight = props.height

    if (typeof actualWidth === 'string' && actualWidth.includes('%')) {
        if (containerRef.value) {
            const parentWidth = containerRef.value.clientWidth
            actualWidth = (parentWidth * parseFloat(actualWidth)) / 100
        }
    }

    if (typeof actualHeight === 'string' && actualHeight.includes('%')) {
        if (containerRef.value) {
            const parentHeight = containerRef.value.clientHeight
            actualHeight = (parentHeight * parseFloat(actualHeight)) / 100
        }
    }

    canvasWidth.value = Number(actualWidth) || 800
    canvasHeight.value = Number(actualHeight) || 500

    nextTick(() => {
        drawPath()
    })
}

const getPathPoints = () => {
    const data = props.pathData
    if (!data) return []

    const pathsObj = data.paths || data.Paths || data
    const pathArray = pathsObj?.Paths?.Path || pathsObj?.Path || []

    if (!pathArray || !Array.isArray(pathArray)) return []

    return pathArray.map(point => ({
        x: parseFloat(point['@x'] || point.x || 0),
        y: parseFloat(point['@y'] || point.y || 0),
        th: parseFloat(point['@th'] || point.th || 0)
    }))
}

const pathPointCount = computed(() => getPathPoints().length)

const currentPos = computed(() => {
    const pos = props.currentPosition
    if (!pos) return null

    return {
        x: parseFloat(pos.x || pos['@x'] || 0),
        y: parseFloat(pos.y || pos['@y'] || 0),
        h: parseFloat(pos.h || pos.th || pos['@th'] || pos.H || 0)
    }
})

const calculateBounds = (points) => {
    if (!points.length) return null

    let minX = Infinity, maxX = -Infinity
    let minY = Infinity, maxY = -Infinity

    points.forEach(p => {
        minX = Math.min(minX, p.x)
        maxX = Math.max(maxX, p.x)
        minY = Math.min(minY, p.y)
        maxY = Math.max(maxY, p.y)
    })

    const padding = 50
    return {
        minX: minX - padding,
        maxX: maxX + padding,
        minY: minY - padding,
        maxY: maxY + padding,
        width: maxX - minX + padding * 2,
        height: maxY - minY + padding * 2
    }
}

const drawPath = () => {
    if (!ctx || !canvasRef.value) return

    const canvas = canvasRef.value
    const width = canvas.width
    const height = canvas.height

    ctx.clearRect(0, 0, width, height)

    ctx.fillStyle = '#f5f5f5'
    ctx.fillRect(0, 0, width, height)

    const points = getPathPoints()
    if (!points.length) return

    const bounds = calculateBounds(points)
    if (!bounds) return

    const scaleX = (width - 100) / bounds.width
    const scaleY = (height - 100) / bounds.height
    const baseScale = Math.min(scaleX, scaleY) * 0.9

    const finalScale = baseScale * scale.value

    const centerX = width / 2
    const centerY = height / 2

    const mapCenterX = (bounds.minX + bounds.maxX) / 2
    const mapCenterY = (bounds.minY + bounds.maxY) / 2

    const transform = (x, y) => {
        const rotated = rotatePoint(-x + mapCenterX, y - mapCenterY, rotationAngle.value)
        return {
            x: centerX + rotated.x * finalScale + offsetX.value,
            y: centerY + rotated.y * finalScale + offsetY.value
        }
    }

    const rotatePoint = (x, y, angleDeg) => {
        const angleRad = (angleDeg * Math.PI) / 180
        const cos = Math.cos(angleRad)
        const sin = Math.sin(angleRad)
        return {
            x: x * cos - y * sin,
            y: x * sin + y * cos
        }
    }

    drawGrid(ctx, width, height, transform, bounds, finalScale)

    if (points.length > 1) {
        ctx.beginPath()
        ctx.strokeStyle = props.pathColor
        ctx.lineWidth = 3
        ctx.lineCap = 'round'
        ctx.lineJoin = 'round'

        const start = transform(points[0].x, points[0].y)
        ctx.moveTo(start.x, start.y)

        for (let i = 1; i < points.length; i++) {
            const p = transform(points[i].x, points[i].y)
            ctx.lineTo(p.x, p.y)
        }
        ctx.stroke()

        ctx.beginPath()
        ctx.strokeStyle = 'rgba(32, 128, 240, 0.3)'
        ctx.lineWidth = 8
        ctx.moveTo(start.x, start.y)

        for (let i = 1; i < points.length; i++) {
            const p = transform(points[i].x, points[i].y)
            ctx.lineTo(p.x, p.y)
        }
        ctx.stroke()
    }

    points.forEach((point, index) => {
        const p = transform(point.x, point.y)

        if (index === 0) {
            ctx.beginPath()
            ctx.fillStyle = '#52c41a'
            ctx.arc(p.x, p.y, 8, 0, Math.PI * 2)
            ctx.fill()

            ctx.fillStyle = '#fff'
            ctx.font = 'bold 10px sans-serif'
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            ctx.fillText('S', p.x, p.y)
        } else if (index === points.length - 1) {
            ctx.beginPath()
            ctx.fillStyle = '#ff4d4f'
            ctx.arc(p.x, p.y, 8, 0, Math.PI * 2)
            ctx.fill()

            ctx.fillStyle = '#fff'
            ctx.font = 'bold 10px sans-serif'
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            ctx.fillText('E', p.x, p.y)
        }
    })

    if (props.showDirection && points.length > 1) {
        const step = Math.max(1, Math.floor(points.length / 20))
        for (let i = 0; i < points.length; i += step) {
            const point = points[i]
            const p = transform(point.x, point.y)

            const angleRad = (point.th * Math.PI) / 180
            const arrowLength = 15 * finalScale / baseScale

            const endX = p.x + Math.cos(angleRad) * arrowLength
            const endY = p.y + Math.sin(angleRad) * arrowLength

            ctx.beginPath()
            ctx.strokeStyle = 'rgba(255, 77, 79, 0.8)'
            ctx.lineWidth = 2
            ctx.moveTo(p.x, p.y)
            ctx.lineTo(endX, endY)
            ctx.stroke()

            const arrowSize = 6 * finalScale / baseScale
            const angle1 = angleRad + Math.PI * 0.8
            const angle2 = angleRad - Math.PI * 0.8

            ctx.beginPath()
            ctx.fillStyle = 'rgba(255, 77, 79, 0.8)'
            ctx.moveTo(endX, endY)
            ctx.lineTo(endX + Math.cos(angle1) * arrowSize, endY + Math.sin(angle1) * arrowSize)
            ctx.lineTo(endX + Math.cos(angle2) * arrowSize, endY + Math.sin(angle2) * arrowSize)
            ctx.closePath()
            ctx.fill()
        }
    }

    const drawRobot = (point, color, label) => {
        if (!point) return

        const p = transform(point.x, point.y)

        const img = new Image()
        img.src = robotImgUrl.value
        if (img.complete) {
            drawRobotImage(img, p, point, label)
        } else {
            img.onload = () => drawRobotImage(img, p, point, label)
        }
    }

    const drawRobotImage = (img, p, point, label) => {
        const size = 24 * finalScale / baseScale
        const halfSize = size / 2

        ctx.save()
        ctx.translate(p.x, p.y)
        const direction = point.direction !== undefined ? point.direction : (point.th !== undefined ? point.th : point.h)
        const angleRad = ((direction - 90) * Math.PI) / 180 + Math.PI / 2
        ctx.rotate(angleRad)
        ctx.drawImage(img, -halfSize, -halfSize, size, size)
        ctx.restore()

        if (label) {
            ctx.fillStyle = '#fff'
            ctx.font = 'bold 10px sans-serif'
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            ctx.fillText(label, p.x, p.y)
        }
    }

    if (currentPos.value) {
        drawRobot(currentPos.value, '#faad14', 'R')
    } else if (points.length > 0) {
        const lastPoint = points[points.length - 1]
        drawRobot(lastPoint, props.robotColor, null)
    }
}

const drawGrid = (ctx, width, height, transform, bounds, finalScale) => {
    const gridSize = 1000

    ctx.strokeStyle = '#e0e0e0'
    ctx.lineWidth = 1

    const startX = Math.floor(bounds.minX / gridSize) * gridSize
    const startY = Math.floor(bounds.minY / gridSize) * gridSize

    for (let x = startX; x <= bounds.maxX; x += gridSize) {
        const p = transform(x, 0)
        ctx.beginPath()
        ctx.moveTo(p.x, 0)
        ctx.lineTo(p.x, height)
        ctx.stroke()
    }

    for (let y = startY; y <= bounds.maxY; y += gridSize) {
        const p = transform(0, y)
        ctx.beginPath()
        ctx.moveTo(0, p.y)
        ctx.lineTo(width, p.y)
        ctx.stroke()
    }

    ctx.fillStyle = '#999'
    ctx.font = '10px sans-serif'

    for (let x = startX; x <= bounds.maxX; x += gridSize) {
        const p = transform(x, 0)
        ctx.fillText((x / 1000).toFixed(1) + 'm', p.x + 2, height - 5)
    }

    for (let y = startY; y <= bounds.maxY; y += gridSize) {
        const p = transform(0, y)
        ctx.fillText((y / 1000).toFixed(1) + 'm', 5, p.y - 2)
    }
}

const zoomIn = () => {
    scale.value = Math.min(scale.value * 1.2, 5)
    drawPath()
}

const zoomOut = () => {
    scale.value = Math.max(scale.value / 1.2, 0.2)
    drawPath()
}

const resetView = () => {
    scale.value = 1
    offsetX.value = 0
    offsetY.value = 0
    drawPath()
}

const fitView = () => {
    resetView()
    isFirstLoad.value = false
    drawPath()
}

const rotateMap = () => {
    rotationAngle.value -= 90
    if (rotationAngle.value <= -360) {
        rotationAngle.value += 360
    }
    try {
        localStorage.setItem(STORAGE_KEY, String(rotationAngle.value))
    } catch {}
    drawPath()
}

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
    drawPath()
}

const handleMouseUp = () => {
    isDragging.value = false
}

const handleWheel = (e) => {
    e.preventDefault()

    if (e.deltaY < 0) {
        zoomIn()
    } else {
        zoomOut()
    }
}

watch(() => props.pathData, () => {
    nextTick(() => {
        if (isFirstLoad.value) {
            resetView()
            isFirstLoad.value = false
        }
        drawPath()
    })
}, { deep: true, immediate: true })

watch(() => props.currentPosition, () => {
    nextTick(() => {
        drawPath()
    })
}, { deep: true })

watch([() => props.width, () => props.height], () => {
    updateCanvasSize()
})

onMounted(() => {
    initCanvas()

    if (canvasRef.value) {
        canvasRef.value.addEventListener('mousedown', handleMouseDown)
        window.addEventListener('mousemove', handleMouseMove)
        window.addEventListener('mouseup', handleMouseUp)
        canvasRef.value.addEventListener('wheel', handleWheel, { passive: false })
    }

    window.addEventListener('resize', updateCanvasSize)
})

onUnmounted(() => {
    if (canvasRef.value) {
        canvasRef.value.removeEventListener('mousedown', handleMouseDown)
        window.removeEventListener('mousemove', handleMouseMove)
        window.removeEventListener('mouseup', handleMouseUp)
        canvasRef.value.removeEventListener('wheel', handleWheel)
    }

    window.removeEventListener('resize', updateCanvasSize)
})
</script>

<style scoped>
.path-show-card {
    width: 100%;
    height: 100%;
}

.header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}

.canvas-container {
    position: relative;
    width: 100%;
    height: 100%;
    min-height: 300px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.canvas-container canvas {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    cursor: grab;
}

.canvas-container canvas:active {
    cursor: grabbing;
}

.no-data {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
}

.controls {
    display: flex;
    align-items: center;
    gap: 8px;
}
.n-empty .n-empty__description {
    font-size: 12px;
    color: #d62a2a !important;
}

</style>
