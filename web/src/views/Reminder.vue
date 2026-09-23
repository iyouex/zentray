<template>
  <div class="page reminder-page">
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
            <a-button size="small" type="outline" :loading="c.acting" @click="act(c, 'snooze')">
              😴 稍后 10 分钟
            </a-button>
            <a-button size="small" type="outline" :loading="c.acting" @click="act(c, 'dismiss')">
              忽略
            </a-button>
          </div>
        </div>
      </TransitionGroup>
      <a-empty v-else-if="!loading" description="没有到期提醒" />
    </a-spin>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { closeHost, listTasks, reminderAction } from '@/api/client'
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
async function act(c, action) {
  c.acting = true
  try {
    await reminderAction(c.id, {
      action,
      fire_key: c.fireKey || '',
      snooze_minutes: 10,
    })
    cards.value = cards.value.filter((x) => x.id !== c.id)
    if (!cards.value.length) closeHost({ action: 'deck-cleared' })
  } catch (e) {
    c.acting = false
    Message.error(e?.message || '操作失败')
  }
}

onMounted(async () => {
  try {
    const ids = String(route.query.ids || '').split(',').filter(Boolean)
    const keys = String(route.query.keys || '').split(',')
    const all = await listTasks()
    cards.value = ids
      .map((id, i) => {
        const task = all.find((t) => t.id === id)
        return task ? { id, fireKey: keys[i] || '', acting: false, task } : null
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
}
/* 卡片离场 */
.rm-card-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.rm-card-leave-to {
  opacity: 0;
  transform: scale(0.92);
}
</style>
