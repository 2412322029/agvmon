import { computed, ref } from 'vue'

const _accentColor = ref('')
let _loaded = false

export function useAccentColor() {

  async function loadFromServer() {
    if (_loaded) return
    _loaded = true
    try {
      const res = await fetch('/api/util/background/settings')
      if (res.ok) {
        const s = await res.json()
        if (s.accent_color) {
          _accentColor.value = s.accent_color
        }
      }
    } catch { /* offline */ }
  }

  function setAccent(v) {
    _accentColor.value = v
  }

  function resetAccent() {
    _accentColor.value = ''
  }

  const themeOverrides = computed(() => {
    if (!_accentColor.value) return {}
    const c = _accentColor.value
    return { common: { primaryColor: c, primaryColorHover: c, primaryColorPressed: c, primaryColorSuppl: c } }
  })

  return { accentColor: _accentColor, setAccent, resetAccent, themeOverrides, loadFromServer }
}
