const FILTER_MAP = {
  none:        () => '',
  blur:        (s) => `blur(${s || 0}px)`,
  grayscale:   (s) => `grayscale(${(s || 50) / 100})`,
  sepia:       (s) => `sepia(${(s || 70) / 100})`,
  brightness:  (s) => `brightness(${(s || 55) / 100})`,
  contrast:    (s) => `contrast(${(s || 130) / 100})`,
  saturate:    (s) => `saturate(${(s || 30) / 100})`,
}

export async function applyBodyBg(overrides = {}) {
  const hasCustom = localStorage.getItem('has_custom_bg') === '1'
  if (!hasCustom) return null

  let settings = overrides
  if (!Object.keys(overrides).length) {
    try {
      const res = await fetch('/api/util/background/settings')
      if (res.ok) settings = await res.json()
    } catch { settings = {} }
  }

  const cbg = document.getElementById('cbg')
  if (cbg) cbg.style.display = 'none'

  const bodyOpacity = settings.body_opacity ?? 1
  const filterType = settings.filter ?? 'none'
  const strength = settings.strength ?? settings.blur ?? 0
  const fn = FILTER_MAP[filterType] || FILTER_MAP.none
  const filterValue = fn(strength)

  // body 设背景图 + 面板透明度
  document.body.style.backgroundImage = "url('/api/util/background')"
  document.body.style.backgroundSize = 'cover'
  document.body.style.backgroundPosition = 'center'
  document.body.style.backgroundAttachment = 'fixed'
  document.documentElement.style.setProperty('--body-opacity', bodyOpacity)

  // 滤镜层 (仅当有滤镜效果时)
  const styleId = 'bg-blur-style'
  let style = document.getElementById(styleId)
  if (!style) {
    style = document.createElement('style')
    style.id = styleId
    document.head.appendChild(style)
  }
  if (filterValue) {
    style.textContent = `
      body::before {
        content: '';
        position: fixed;
        inset: 0;
        z-index: -1;
        background-image: url('/api/util/background');
        background-size: cover;
        background-position: center;
        filter: ${filterValue};
        opacity: 1;
      }
      .n-card, .n-modal, .n-data-table, .n-collapse-item, .n-alert {
        opacity: var(--body-opacity, 1);
      }
    `
  } else {
    style.textContent = `
      .n-card, .n-modal, .n-data-table, .n-collapse-item, .n-alert {
        opacity: var(--body-opacity, 1);
      }
    `
  }

  return { body_opacity: bodyOpacity, filter: filterType, strength, accent_color: settings.accent_color || '' }
}

export function resetBodyBg() {
  const s = document.getElementById('bg-blur-style')
  if (s) s.remove()
  document.body.style.backgroundImage = ''
  document.body.style.backgroundSize = ''
  document.body.style.backgroundPosition = ''
  document.body.style.backgroundAttachment = ''
  document.body.style.opacity = ''
  document.documentElement.style.removeProperty('--body-opacity')
  const cbg = document.getElementById('cbg')
  if (cbg) cbg.style.display = ''
  localStorage.removeItem('has_custom_bg')
}
