/**
 * 主题：与 Python zentray/ui/theme.py 一致
 * mode: light | dark | system
 */

export function resolveEffectiveTheme(mode) {
  const m = (mode || 'system').toLowerCase()
  if (m === 'light' || m === 'dark' || m === 'oled-dark' || m === 'slate-dark') {
    return m
  }
  // system
  try {
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'slate-dark'
    }
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
      return 'light'
    }
  } catch (_) {}
  return 'slate-dark'
}

/**
 * 应用 Arco + 页面 CSS 变量
 * @param {string} mode light | dark | oled-dark | slate-dark | system
 * @returns {string} 实际生效的 mode
 */
export function applyTheme(mode) {
  const effective = resolveEffectiveTheme(mode)
  const root = document.body

  // 清除旧主题 class
  root.classList.remove('theme-light', 'theme-dark', 'theme-slate-dark', 'theme-oled-dark')

  if (effective === 'light') {
    root.removeAttribute('arco-theme')
    root.classList.add('theme-light')
  } else if (effective === 'oled-dark') {
    root.setAttribute('arco-theme', 'dark')
    root.classList.add('theme-dark', 'theme-oled-dark')
  } else {
    // dark or slate-dark
    root.setAttribute('arco-theme', 'dark')
    root.classList.add('theme-dark', 'theme-slate-dark')
  }

  root.dataset.themeMode = mode || 'system'
  root.dataset.themeEffective = effective
  return effective
}

/** 监听系统主题变化（仅 mode=system 时生效） */
export function watchSystemTheme(getMode, onChange) {
  if (!window.matchMedia) return () => {}
  const mq = window.matchMedia('(prefers-color-scheme: dark)')
  const handler = () => {
    const mode = typeof getMode === 'function' ? getMode() : getMode
    if ((mode || 'system').toLowerCase() === 'system') {
      const eff = applyTheme('system')
      onChange && onChange(eff)
    }
  }
  if (mq.addEventListener) mq.addEventListener('change', handler)
  else if (mq.addListener) mq.addListener(handler)
  return () => {
    if (mq.removeEventListener) mq.removeEventListener('change', handler)
    else if (mq.removeListener) mq.removeListener(handler)
  }
}

/**
 * 分类识别色：固定 8 色板稳定映射（spec §2）。
 * 默认分类「工作/个人/学习」固定落前三席；其余分类按名称 hash，
 * 保证同名永远同色。
 */
const CATEGORY_PALETTE = [
  '#14b8a6', // teal    工作
  '#a78bfa', // violet  个人
  '#fbbf24', // amber   学习
  '#38bdf8', // sky
  '#fb7185', // rose
  '#a3e635', // lime
  '#94a3b8', // slate
  '#e879f9', // fuchsia
]
const KNOWN_CATEGORY_SEAT = { 工作: 0, 个人: 1, 学习: 2 }

export function categoryColor(name) {
  const s = String(name || '').trim()
  if (Object.prototype.hasOwnProperty.call(KNOWN_CATEGORY_SEAT, s)) {
    return CATEGORY_PALETTE[KNOWN_CATEGORY_SEAT[s]]
  }
  let h = 0
  for (let i = 0; i < s.length; i++) h = (Math.imul(h, 31) + s.charCodeAt(i)) >>> 0
  return CATEGORY_PALETTE[h % CATEGORY_PALETTE.length]
}

/**
 * 外观偏好：动效开关与形状风格（spec §5）。
 * body class: zt-motion-off / zt-shape-crisp，令牌层按 class 切换档位。
 */
export function applyAppearance(prefs) {
  const motion = prefs?.motion === 'off' ? 'off' : 'full'
  const shape = prefs?.shape === 'crisp' ? 'crisp' : 'round'
  const root = document.body
  root.classList.toggle('zt-motion-off', motion === 'off')
  root.classList.toggle('zt-shape-crisp', shape === 'crisp')
  root.dataset.ztMotion = motion
  root.dataset.ztShape = shape
  return { motion, shape }
}
