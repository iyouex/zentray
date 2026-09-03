<template>
  <a-config-provider :update-at-scroll="true">
    <router-view />
  </a-config-provider>
</template>

<script setup>
import { onMounted, onUnmounted, provide, ref } from 'vue'
import { applyTheme, watchSystemTheme } from './theme'
import { getSettings } from './api/client'

const themeMode = ref('system')
const themeEffective = ref('dark')

provide('themeMode', themeMode)
provide('themeEffective', themeEffective)
provide('setThemeMode', (mode) => {
  themeMode.value = mode || 'system'
  themeEffective.value = applyTheme(themeMode.value)
})

let unwatch = () => {}

// 无边框窗口拖拽：空白区域可拖，控件点击不抢占。
// 必须用 location.href：QWebEngine 同步拦截导航，Wayland 的 startSystemMove 才接得上用户按下。
const INTERACTIVE_SELECTOR = [
  'button',
  'a',
  'input',
  'textarea',
  'select',
  'label',
  '.arco-btn',
  '.arco-input',
  '.arco-input-wrapper',
  '.arco-select',
  '.arco-picker',
  '.arco-checkbox',
  '.arco-radio',
  '.arco-dropdown',
  '.arco-modal',
  '.arco-slider',
  '.arco-switch',
  '.arco-textarea',
  '.arco-table',
  '.no-drag',
  '.task-card-item',
].join(', ')

let isDragging = false
let startScreenX = 0
let startScreenY = 0

function sendBridgeSignal(url) {
  window.location.href = url
}

function handleMouseDown(e) {
  if (!e.target || e.button !== 0) return
  if (e.target.closest(INTERACTIVE_SELECTOR)) return
  // Arco 下拉/日期/级联等弹层 teleport 到 body（#app 之外），点在弹层上绝不触发窗口拖拽
  const appRoot = document.getElementById('app')
  if (appRoot && !appRoot.contains(e.target)) return

  isDragging = true
  startScreenX = e.screenX
  startScreenY = e.screenY
  sendBridgeSignal('zentray://start_drag')
}

function handleMouseMove(e) {
  if (!isDragging) return
  if ((e.buttons & 1) === 0) {
    isDragging = false
    return
  }
  const dx = e.screenX - startScreenX
  const dy = e.screenY - startScreenY
  if (dx !== 0 || dy !== 0) {
    startScreenX = e.screenX
    startScreenY = e.screenY
    sendBridgeSignal(`zentray://move?dx=${dx}&dy=${dy}`)
  }
}

function handleMouseUp() {
  isDragging = false
}

onMounted(async () => {
  window.addEventListener('mousedown', handleMouseDown)
  window.addEventListener('mousemove', handleMouseMove)
  window.addEventListener('mouseup', handleMouseUp)

  try {
    const s = await getSettings()
    themeMode.value = s?.appearance?.theme || 'system'
  } catch (_) {
    themeMode.value = 'system'
  }
  themeEffective.value = applyTheme(themeMode.value)
  unwatch = watchSystemTheme(
    () => themeMode.value,
    (eff) => {
      themeEffective.value = eff
    },
  )
})

onUnmounted(() => {
  window.removeEventListener('mousedown', handleMouseDown)
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('mouseup', handleMouseUp)
  if (unwatch) unwatch()
})
</script>
