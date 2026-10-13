<template>
  <div ref="rootRef" class="page reminder-page">
    <div class="page-header">
      <h2>⏰ 任务提醒（{{ cards.length }}）</h2>
    </div>

    <a-spin :loading="loading" style="width: 100%">
      <TransitionGroup v-if="cards.length" name="rm-card" tag="div" class="deck">
        <div v-for="c in cards" :key="c.id" class="rcard" :class="{ acting: c.acting }">
          <div class="rcard-head">
            <span class="rcard-title">{{ c.task.title }}</span>
            <a-tag size="small" :class="PRI_CLASS[c.task.priority] || 'zt-pri-l'">
              {{ PRI_LABEL[c.task.priority] || '低' }}
            </a-tag>
          </div>
          <div class="rcard-meta">
            <a-tag v-if="c.task.category" size="small" :style="{
              color: categoryColor(c.task.category),
              background: categoryColor(c.task.category) + '24',
              borderRadius: '999px',
            }">
              {{ c.task.category }}
            </a-tag>
            <span class="rcard-time">{{ timeOf(c) }}</span>
          </div>
          <p v-if="c.task.details" class="rcard-details">{{ c.task.details }}</p>
          <div class="rcard-actions">
            <a-button size="small" type="primary" status="success" :loading="c.acting" @click="act(c, 'done')">
              ✅ 完成
            </a-button>
            <a-dropdown-button size="small" type="outline" :disabled="c.acting" @click="act(c, 'snooze', 10)">
              😴 稍后 10 分钟 ▾
              <template #content>
                <a-doption @click="act(c, 'snooze', 60)">1 小时后</a-doption>
                <a-doption @click="act(c, 'snooze', minutesToEod())">当天 23:59</a-doption>
                <a-doption @click="c.customOpen = true">自定义…</a-doption>
              </template>
            </a-dropdown-button>
            <a-button size="small" type="outline" :loading="c.acting" @click="act(c, 'dismiss')">
              忽略
            </a-button>
            <a-button size="small" type="text" :loading="c.acting" @click="jump(c)">↗ 跳转</a-button>
          </div>
          <div v-if="c.customOpen" class="rcard-custom">
            稍后
            <a-input-number v-model="c.customMin" :min="1" :max="1440" size="small" style="width: 96px" />
            分钟
            <a-button size="small" type="primary" :loading="c.acting" @click="act(c, 'snooze', c.customMin || 30)">
              确定
            </a-button>
          </div>
        </div>
      </TransitionGroup>
      <a-empty v-else-if="!loading" description="没有到期提醒" />
    </a-spin>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { closeHost, listTasks, reminderAction, reportHostHeight } from '@/api/client'
import { categoryColor } from '@/theme'

const route = useRoute()
const loading = ref(true)
const cards = ref([]) // [{ id, fireKey, acting, task }]

const PRI_CLASS = { high: 'zt-pri-h', medium: 'zt-pri-m', low: 'zt-pri-l' }
const PRI_LABEL = { high: '高', medium: '中', low: '低' }

function timeOf(c) {
  const k = (c.fireKey || '').split('|')[1]
  return k || c.task.reminder?.time_of_day || ''
}

/** 逐卡即时动作：落库后卡片离场；甲板清空自动关窗（未处理卡由宿主扫尾 dismiss） */
async function act(c, action, snoozeMin = 10) {
  c.acting = true
  try {
    await reminderAction(c.id, {
      action,
      fire_key: c.fireKey || '',
      snooze_minutes: snoozeMin,
    })
    cards.value = cards.value.filter((x) => x.id !== c.id)
    if (!cards.value.length) closeHost({ action: 'deck-cleared' })
  } catch (e) {
    c.acting = false
    Message.error(e?.message || '操作失败')
  }
}

/** 当天档：距 23:59 的分钟数（前端折算，后端只收 snooze_minutes） */
function minutesToEod() {
  const eod = new Date()
  eod.setHours(23, 59, 59, 0)
  return Math.max(1, Math.ceil((eod.getTime() - Date.now()) / 60000))
}

/** 跳转：整个甲板关窗（本卡与其余未处理卡由宿主统一 dismiss），宿主开任务列表直达选中 */
function jump(c) {
  closeHost({ action: 'jump', task_id: c.id })
}

onMounted(async () => {
  try {
    const ids = String(route.query.ids || '').split(',').filter(Boolean)
    const keys = String(route.query.keys || '').split(',')
    const all = await listTasks()
    cards.value = ids
      .map((id, i) => {
        const task = all.find((t) => t.id === id)
        return task ? { id, fireKey: keys[i] || '', acting: false, task, customOpen: false, customMin: 30 } : null
      })
      .filter(Boolean)
    // 全部已不存在（提前完成等）：直接关窗
    if (!cards.value.length) closeHost({ action: 'deck-cleared' })
  } catch (e) {
    Message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
})

/** 高度自适应：卡片增减即上报内容高，宿主同步调窗（开窗仍用 120+n*170 预估）。
 * 页面根有 min-height:100% 不可直接量（会随视口自放大），量到 deck 底边为止 */
const rootRef = ref(null)
let lastReportedH = 0
let deckEl = null
const resizeObserver = new ResizeObserver(syncHeight)
function syncHeight() {
  const root = rootRef.value
  const deck = root?.querySelector('.deck')
  if (!root || !deck) return
  if (deck !== deckEl) {
    deckEl = deck
    resizeObserver.observe(deck)
  }
  const h = Math.ceil(
    deck.getBoundingClientRect().bottom - root.getBoundingClientRect().top +
    parseFloat(getComputedStyle(root).paddingBottom),
  )
  if (h > 0 && h !== lastReportedH) {
    lastReportedH = h
    reportHostHeight(h)
  }
}
watch(() => cards.value.length, () => nextTick(syncHeight))
onBeforeUnmount(() => resizeObserver.disconnect())
</script>

<style scoped>
.reminder-page {
  padding: 12px 14px;
}
.deck {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.rcard {
  border: 1px solid var(--color-border);
  border-radius: var(--zt-radius-card, 16px);
  background: var(--color-surface);
  padding: 10px 14px;
  box-shadow: var(--zt-shadow-card);
}
.rcard-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rcard-title {
  font-weight: 600;
  font-size: 14px;
  flex: 1;
  word-break: break-word;
}
.rcard-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}
.rcard-time {
  font-size: 12px;
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}
.rcard-details {
  margin: 6px 0;
  font-size: 12.5px;
  color: var(--color-text-2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-line;
  word-break: break-word;
}
.rcard-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.rcard-custom {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--color-text-2);
}
/* 卡片离场 */
.rm-card-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.rm-card-leave-to {
  opacity: 0;
  transform: scale(0.92);
}

/* ---- 皮肤变体（body.zt-skin-* 门控） ---- */
/* Aurora：玻璃卡 + 极光渐变左缘 */
body.zt-skin-aurora .rcard {
  position: relative;
  border: 1px solid color-mix(in srgb, var(--color-text-primary) 9%, transparent);
  background: color-mix(in srgb, var(--color-surface) 55%, transparent);
  backdrop-filter: blur(18px) saturate(1.4);
  -webkit-backdrop-filter: blur(18px) saturate(1.4);
  padding: 10px 14px 10px 17px;
  box-shadow: 0 8px 32px rgba(2, 6, 23, 0.35),
    inset 0 1px 0 color-mix(in srgb, #ffffff 6%, transparent);
  overflow: hidden;
}
body.zt-skin-aurora .rcard::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: linear-gradient(180deg, var(--color-primary), #818cf8 55%, #e879f9);
  pointer-events: none;
}
/* Neo：2px 描边方角 */
body.zt-skin-neo .rcard {
  border: 2px solid var(--color-border);
  border-radius: var(--zt-radius-card, 4px);
}
</style>
