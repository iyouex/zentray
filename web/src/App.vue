<template>
  <a-config-provider :update-at-scroll="true">
    <router-view :key="viewKey" />
  </a-config-provider>
</template>

<script setup>
import { onMounted, onUnmounted, provide, ref } from 'vue'
import { applyTheme, watchSystemTheme } from './theme'
import { getSettings } from './api/client'

const themeMode = ref('system')
const themeEffective = ref('dark')

// 关窗保活复用：Python 侧重新唤起保活面板时派发 zentray:reopen，
// 递增 router-view 的 key 强制重挂当前页面组件（onMounted 重新拉数据），
// 避免保活面板展示关窗前的陈旧数据。
const viewKey = ref(0)
const handleReopen = () => {
  viewKey.value++
}

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
  // 拖拽只从页面标题栏（.page-header）发起。
  // 此前是“落在非交互控件即可拖整窗”，但 Arco 的 a-menu-item / a-tabs-tab 等
  // 交互组件都是 div、不在白名单里 → 每次点击都被 zentray://start_drag →
  // startSystemMove 抢占吞掉（设置页分区菜单、各页 tab 全部失效的根因）。
  // 现在点击默认放行，拖拽改为显式标题栏区域；QuickAdd 等无标题栏页面的
  // 空白区拖拽由 Python 侧 DialogDragFilter 提供。
  if (!e.target.closest('.page-header')) return
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
  window.addEventListener('zentray:reopen', handleReopen)

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
  window.removeEventListener('zentray:reopen', handleReopen)
  if (unwatch) unwatch()
})
</script>
