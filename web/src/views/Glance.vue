<template>
  <div class="glance-page" tabindex="-1" @keydown.esc="onClose">
    <!-- 轮播槽大卡：饼图 + 优先级 + 子任务进度；◀▶ 手动切任务（不改调度） -->
    <div v-if="item" class="g-card">
      <div class="g-card-head">
        <div class="g-ring" :style="ringStyle">
          <span class="g-ring-num">{{ ringPct }}%</span>
        </div>
        <div class="g-card-main">
          <div class="g-tags">
            <span class="g-tag" :class="`pri-${item.priority}`">
              {{ PRI_LABEL[item.priority] || '中' }}优先
            </span>
            <span v-if="item.category" class="g-cat">{{ item.category }}</span>
          </div>
          <p class="g-title">{{ item.display_title || item.title }}</p>
        </div>
        <div class="g-nav" v-if="activeCount > 1">
          <a-button size="mini" @click="navTask(-1)" aria-label="上一条">◀</a-button>
          <a-button size="mini" @click="navTask(1)" aria-label="下一条">▶</a-button>
        </div>
      </div>
      <p class="g-meta">
        <template v-if="item.subs_total">子任务 {{ item.subs_done }}/{{ item.subs_total }} ·</template>
        <template v-if="item.deadline">截止 {{ item.deadline }}</template>
        <span v-if="!item.subs_total && !item.deadline" class="g-meta-dim">无子任务与截止</span>
      </p>
    </div>
    <div v-else class="g-empty" @click="quickAdd">
      暂无活跃任务 — <span class="g-empty-act">⚡ 记一笔？</span>
    </div>

    <!-- 番茄态行：进行中才显示；按钮随阶段切换 -->
    <div v-if="pomo.phase !== 'idle'" class="g-pomo">
      <div class="g-pomo-line">
        <span class="g-pomo-icon">{{ isBreak ? '☕' : '🍅' }}</span>
        <span class="g-pomo-state">{{ isBreak ? '休息中' : '专注中' }} {{ mmss(pomo.remaining) }}</span>
        <span class="g-pomo-today">今日 {{ pomo.today_count }} 🍅 / {{ pomo.today_minutes }}min</span>
      </div>
      <div class="g-pomo-ops">
        <template v-if="isBreak">
          <a-button size="small" status="warning" @click="control('skip_break')">⏭ 跳过休息</a-button>
        </template>
        <template v-else>
          <a-button size="small" status="danger" @click="control('stop')">⏹ 中止</a-button>
          <a-button size="small" @click="control('extend')">➕ 延长</a-button>
        </template>
      </div>
    </div>

    <!-- 报告 chips：点开即消 -->
    <div v-if="reports.length" class="g-reports">
      <button
        v-for="r in reports"
        :key="r.key"
        class="g-chip"
        :title="r.text"
        @click="openReport(r.key)"
      >
        📄 {{ r.text }}
      </button>
    </div>

    <!-- 快捷行：作用于当前轮播槽任务 -->
    <div class="g-actions">
      <a-button size="small" type="primary" status="success" :disabled="!item" @click="markDone">✓ 完成</a-button>
      <a-button
        size="small"
        status="warning"
        :disabled="!item || pomo.phase !== 'idle' || opsBusy"
        :title="opsBusy ? '脚本运行中' : ''"
        @click="focusTask"
      >🍅 以此专注</a-button>
      <a-button size="small" @click="quickAdd">⚡ 快速添加</a-button>
      <a-button size="small" @click="openTasks">📋 打开完整列表</a-button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import {
  cancelHost,
  closeHost,
  getGlance,
  glanceReportOpen,
  markDone as markDoneApi,
  pomodoroControl,
  selectTask,
  startPomodoro,
} from '@/api/client'

const PRI_LABEL = { high: '高', medium: '中', low: '低' }
const PRI_COLOR = { high: '#e5484d', medium: '#f5a524', low: '#30a46c' }

const item = ref(null)
const activeIds = ref([])
const pomo = ref({ phase: 'idle', today_count: 0, today_minutes: 0 })
const reports = ref([])
const opsBusy = ref(false)

let timer = null
let pollSeq = 0

const isBreak = computed(() => ['short_break', 'long_break'].includes(pomo.value.phase))
const activeCount = computed(() => activeIds.value.length)

/** 饼图环：子任务完成比例（无子任务按优先级色 100% 空环心） */
const ringPct = computed(() => {
  const it = item.value
  if (!it || !it.subs_total) return 0
  return Math.round((it.subs_done / it.subs_total) * 100)
})
const ringStyle = computed(() => {
  const color = PRI_COLOR[item.value?.priority] || PRI_COLOR.low
  const pct = ringPct.value
  return {
    background: `conic-gradient(${color} ${pct * 3.6}deg, var(--color-fill-2, rgba(148,163,184,.2)) 0deg)`,
  }
})

function mmss(sec) {
  const s = Math.max(0, int(sec))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}
function int(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

async function poll() {
  const seq = ++pollSeq
  try {
    const d = await getGlance()
    if (seq !== pollSeq) return // 过期响应丢弃，防旧盖新
    item.value = d.item
    activeIds.value = d.active_ids || []
    pomo.value = d.pomodoro || { phase: 'idle', today_count: 0, today_minutes: 0 }
    reports.value = d.reports || []
    opsBusy.value = !!d.ops_busy
  } catch (_) {
    /* 面板常驻轮询，瞬时失败静默（下次 tick 重试） */
  }
}

/** ◀▶：沿活跃序切换当前任务（selectTask 即轮播槽换位，不改自动调度节奏） */
async function navTask(dir) {
  const ids = activeIds.value
  const n = ids.length
  if (n < 2) return
  const idx = ids.indexOf(item.value?.id)
  const next = ids[((idx < 0 ? 0 : idx) + dir + n) % n]
  try {
    await selectTask(next)
    await poll()
  } catch (e) {
    Message.error(e?.message || '切换失败')
  }
}

async function control(action) {
  try {
    await pomodoroControl(action)
    await poll()
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '操作失败')
  }
}

async function openReport(key) {
  try {
    await glanceReportOpen(key)
    await poll()
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '打开失败')
  }
}

async function markDone() {
  if (!item.value) return
  try {
    await markDoneApi(item.value.id)
    await poll()
  } catch (e) {
    Message.error(e?.message || '完成失败')
  }
}

async function focusTask() {
  if (!item.value) return
  try {
    await startPomodoro(item.value.id)
    await poll()
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '开始专注失败')
  }
}

function quickAdd() {
  closeHost({ action: 'quick_add' })
}
function openTasks() {
  closeHost({ action: 'open_tasks' })
}
function onClose() {
  cancelHost()
}

onMounted(() => {
  poll()
  timer = setInterval(poll, 1000)
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
  window.removeEventListener('keydown', onKey)
})
function onKey(e) {
  if (e.key === 'Escape') onClose()
}
</script>

<style scoped>
.glance-page {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 100vh;
  box-sizing: border-box;
  animation: glance-in 0.1s ease-out;
}
@keyframes glance-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .glance-page {
    animation: none;
  }
}

/* 轮播槽大卡 */
.g-card {
  border: 1px solid var(--color-border);
  border-radius: var(--zt-radius-card, 12px);
  padding: 10px 12px;
  background: var(--color-fill-1, rgba(148, 163, 184, 0.08));
}
.g-card-head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.g-ring {
  flex: none;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}
.g-ring::after {
  content: '';
  position: absolute;
  inset: 6px;
  border-radius: 50%;
  background: var(--color-bg-2, #fff);
}
.g-ring-num {
  position: relative;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-1);
}
.g-card-main {
  flex: 1;
  min-width: 0;
}
.g-tags {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 4px;
}
.g-tag {
  font-size: 11px;
  border-radius: var(--zt-radius-pill, 999px);
  padding: 1px 8px;
  color: #fff;
}
.g-tag.pri-high {
  background: #e5484d;
}
.g-tag.pri-medium {
  background: #f5a524;
}
.g-tag.pri-low {
  background: #30a46c;
}
.g-cat {
  font-size: 11px;
  color: var(--color-text-3);
}
.g-title {
  margin: 0;
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.g-nav {
  flex: none;
  display: flex;
  gap: 4px;
}
.g-meta {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--color-text-3);
}
.g-meta-dim {
  opacity: 0.7;
}

/* 空态 */
.g-empty {
  border: 1px dashed var(--color-border-2);
  border-radius: var(--zt-radius-card, 12px);
  padding: 22px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--color-text-3);
  cursor: pointer;
}
.g-empty-act {
  color: rgb(var(--primary-6));
}

/* 番茄态行 */
.g-pomo {
  border: 1px solid var(--color-border);
  border-radius: var(--zt-radius-card, 12px);
  padding: 8px 12px;
  background: var(--color-fill-1, rgba(148, 163, 184, 0.08));
}
.g-pomo-line {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
}
.g-pomo-state {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.g-pomo-today {
  margin-left: auto;
  color: var(--color-text-3);
  font-size: 12px;
}
.g-pomo-ops {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

/* 报告 chips */
.g-reports {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.g-chip {
  border: 1px solid var(--color-border-2);
  background: var(--color-fill-1, rgba(148, 163, 184, 0.08));
  color: var(--color-text-2);
  border-radius: var(--zt-radius-pill, 999px);
  padding: 4px 12px;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.g-chip:hover {
  color: var(--color-text-1);
  border-color: rgb(var(--primary-6));
}

/* 快捷行 */
.g-actions {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
  margin-top: auto;
}
</style>
