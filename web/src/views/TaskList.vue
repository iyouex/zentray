<template>
  <div class="page">
    <div class="page-header">
      <h2>任务列表</h2>
      <a-space>
        <a-button type="primary" @click="$router.push({ path: '/tasks/new', query: { from: 'list' } })">
          <template #icon><PhPlus :size="16" /></template>
          新建
        </a-button>
        <a-button @click="$router.push({ path: '/periodic', query: { from: 'list' } })">
          <template #icon><PhRepeat :size="16" /></template>
          周期任务
        </a-button>
        <a-button type="secondary" @click="cancelHost" aria-label="关闭窗口">
          <template #icon><PhX :size="16" /></template>
          关闭
        </a-button>
      </a-space>
    </div>

    <div class="two-col">
      <a-card title="活跃任务" :bordered="true">
        <div v-if="filterChips.length > 1" class="filter-row" role="group" aria-label="分类筛选">
          <button
            v-for="c in filterChips"
            :key="c.key"
            class="fchip"
            type="button"
            :aria-pressed="String(filter === c.key)"
            @click="setFilter(c.key)"
          >
            {{ c.label }} · {{ c.count }}
          </button>
        </div>
        <a-spin :loading="loading" style="width: 100%">
          <TransitionGroup v-if="tasks.length" ref="listRef" name="zt-list" tag="div" class="task-card-list">
            <div
              v-for="item in tasks"
              :key="item.id"
              class="task-card-item"
              :class="{ active: item.id === selectedId, 'flip-gone': !matchesFilter(item) }"
              :data-task-id="item.id"
              :style="cardStyle(item)"
              @click="selectedId = item.id"
            >
              <div class="task-card-main">
                <span class="task-card-title">
                  {{ item.title }}
                  <span v-if="item.priority" class="zt-pri" :class="PRI_CLASS[item.priority] || 'zt-pri-l'">
                    {{ PRI_LABEL[item.priority] || '低' }}
                  </span>
                </span>
                <div class="task-card-meta">
                  <a-tag
                    v-if="item.category"
                    size="small"
                    :style="{
                      color: categoryColor(item.category),
                      background: categoryColor(item.category) + '24',
                      borderRadius: '999px',
                    }"
                  >
                    {{ item.category }}
                  </a-tag>
                  <span class="task-card-sub">进度: {{ item.progress || 0 }}%</span>
                  <span
                    v-if="deadlineInfo(item)"
                    class="task-card-sub"
                    :class="deadlineInfo(item).cls"
                  >
                    截止: {{ deadlineInfo(item).text }}
                  </span>
                </div>
                <div v-if="item.progress" class="zt-card-prog">
                  <i :style="{ width: (item.progress || 0) + '%', background: categoryColor(item.category) }" />
                </div>
              </div>
              <PhCheckCircle
                v-if="item.progress === 100"
                class="icon-check-animated"
                :size="22"
                weight="fill"
              />
            </div>
          </TransitionGroup>
          <a-empty v-else-if="!loading" description="暂无活跃任务" />
        </a-spin>
      </a-card>

      <a-card title="任务详情与操作" :bordered="true">
        <template v-if="current">
          <p class="title">{{ current.title }}</p>
          <p class="meta">
            分类: {{ current.category }}　优先级: {{ current.priority }}　进度: {{ current.progress || 0 }}%
            <br v-if="current.deadline" />
            <span v-if="current.deadline">截止: {{ current.deadline }}</span>
          </p>
          <a-space direction="vertical" fill style="width: 100%">
            <a-button long type="outline" @click="onSelect">
              <template #icon><PhArrowsCounterClockwise :size="16" /></template>
              切换到此任务
            </a-button>
            <a-button long type="outline" @click="goProgress">
              <template #icon><PhPencil :size="16" /></template>
              更新进度
            </a-button>
            <a-button long type="outline" @click="goEdit">
              <template #icon><PhPencil :size="16" /></template>
              编辑查看
            </a-button>
            <a-space fill style="width: 100%">
              <a-button type="primary" status="success" style="flex: 1" @click="onDone">
                <template #icon><PhCheck :size="16" /></template>
                完成
              </a-button>
              <a-button status="danger" style="flex: 1" @click="onAbandon">
                <template #icon><PhTrash :size="16" /></template>
                废弃
              </a-button>
            </a-space>
          </a-space>
        </template>
        <a-empty v-else description="请选择左侧任务" />
      </a-card>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { PhPlus, PhRepeat, PhX, PhArrowsCounterClockwise, PhPencil, PhCheck, PhTrash, PhCheckCircle } from '@phosphor-icons/vue'
import {
  abandonTask,
  cancelHost,
  closeHost,
  listTasks,
  markDone,
  selectTask,
} from '@/api/client'
import { categoryColor } from '@/theme'
import { gsap, Flip, EASE, DUR, motionOff, isReduced } from '@/motion'

const route = useRoute()
const router = useRouter()
const loading = ref(false)

watch(() => route.path, (newPath) => {
  if (newPath === '/tasks') {
    reload()
  }
})
const tasks = ref([])
const selectedId = ref(null)

const PRI_CLASS = { high: 'zt-pri-h', medium: 'zt-pri-m', low: 'zt-pri-l' }
const PRI_LABEL = { high: '高', medium: '中', low: '低' }

function deadlineInfo(item) {
  if (!item.deadline) return null
  const t = new Date(String(item.deadline).replace(' ', 'T')).getTime()
  if (Number.isNaN(t)) return null
  const diff = t - Date.now()
  if (diff < 0) return { text: item.deadline, cls: 'zt-dl-late' }
  if (diff < 24 * 3600 * 1000) return { text: item.deadline, cls: 'zt-dl-soon' }
  return { text: item.deadline, cls: '' }
}

function cardStyle(item) {
  const dl = deadlineInfo(item)
  const style = {}
  if (dl?.cls === 'zt-dl-late') style['--cat-color'] = 'var(--zt-due-late)'
  else if (item.category) style['--cat-color'] = categoryColor(item.category)
  return style
}

// ---- 分类筛选 + Flip 布局流动（spec §3.2，原型场景 2） ----
// 过滤用 class 隐藏而非 v-if：TransitionGroup 把节点移除当增删动画，会与 Flip 打架。
const filter = ref('all')
const listRef = ref(null)

const filterChips = computed(() => {
  const counts = new Map()
  for (const t of tasks.value) {
    const k = t.category || '未分类'
    counts.set(k, (counts.get(k) || 0) + 1)
  }
  const chips = [{ key: 'all', label: '全部', count: tasks.value.length }]
  for (const [k, n] of counts) chips.push({ key: k, label: k, count: n })
  return chips.slice(0, 6)
})

function matchesFilter(item) {
  return filter.value === 'all' || (item.category || '未分类') === filter.value
}

function setFilter(k) {
  if (filter.value === k) return
  runFlip(() => {
    filter.value = k
  })
}

// 分类在数据刷新后消失时回退到「全部」，避免假空列表
watch(filterChips, (chips) => {
  if (!chips.some((c) => c.key === filter.value)) filter.value = 'all'
})

/** DOM 集合变化前后捕获/回放：幸存卡片流动，离场收缩淡出、回归弹性放大 */
async function runFlip(mutate) {
  const root = listRef.value?.$el ?? listRef.value // TransitionGroup 的 ref 是组件实例，$el 才是 tag 渲染的 div
  if (!root || motionOff() || isReduced()) {
    await mutate()
    return
  }
  const cards = root.querySelectorAll('.task-card-item')
  const state = Flip.getState(cards)
  await mutate()
  await nextTick()
  Flip.from(state, {
    duration: DUR.flip,
    ease: EASE.spring,
    stagger: 0.02,
    absolute: true,
    onEnter: (els) => gsap.fromTo(els, { opacity: 0, scale: 0.88 }, { opacity: 1, scale: 1, duration: DUR.enter, ease: EASE.spring, clearProps: 'all' }),
    onLeave: (els) => gsap.to(els, { opacity: 0, scale: 0.88, duration: 0.2, ease: EASE.out }),
  })
}

const current = computed(() => tasks.value.find((t) => t.id === selectedId.value) || null)

async function reload() {
  loading.value = true
  try {
    const fresh = await listTasks()
    runFlip(() => {
      tasks.value = fresh
    })
    if (!selectedId.value && tasks.value.length) {
      selectedId.value = tasks.value[0].id
    }
  } catch (e) {
    Message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function onSelect() {
  if (!current.value) return
  await selectTask(current.value.id)
  Message.success('已切换')
  closeHost({ action: 'select', id: current.value.id })
}

function goProgress() {
  if (!current.value) return
  router.push({ path: `/tasks/${current.value.id}/progress`, query: { from: 'list' } })
}

function goEdit() {
  if (!current.value) return
  router.push({ path: `/tasks/${current.value.id}/edit`, query: { from: 'list' } })
}

/** 卡片离场庆祝：卡片弹性收缩浮起，邻居轻微让位（spec §3.5） */
function celebrateCard(itemId) {
  if (motionOff()) return false
  const root = listRef.value?.$el ?? listRef.value // 同 Task 4：组件实例 → $el
  if (!root) return false
  const cards = Array.from(root.querySelectorAll('.task-card-item'))
  const idx = cards.findIndex((c) => c.dataset.taskId === String(itemId))
  const target = idx >= 0 ? cards[idx] : null
  if (target) {
    gsap.to(target, { scale: 1.02, y: -3, duration: 0.2, ease: EASE.spring })
    gsap.to(target, { autoAlpha: 0, scale: 0.88, y: -8, duration: 0.26, ease: EASE.out, delay: 0.18 })
  }
  cards.forEach((c, j) => {
    if (!target || c === target) return
    const dir = j < idx ? -1 : 1
    gsap.fromTo(c, { y: dir * 2 }, { y: 0, duration: 0.5, ease: EASE.spring })
  })
  return true
}

async function onDone() {
  if (!current.value) return
  await markDone(current.value.id)
  Message.success('已完成')
  if (celebrateCard(current.value.id)) {
    setTimeout(() => closeHost({ action: 'done', id: current.value.id }), 520)
  } else {
    closeHost({ action: 'done', id: current.value.id })
  }
}

function onAbandon() {
  if (!current.value) return
  Modal.confirm({
    draggable: true,
    title: '确认废弃',
    content: `确定废弃「${current.value.title}」？`,
    onOk: async () => {
      await abandonTask(current.value.id)
      Message.success('已废弃')
      if (celebrateCard(current.value.id)) {
        setTimeout(() => closeHost({ action: 'abandon', id: current.value.id }), 520)
      } else {
        closeHost({ action: 'abandon', id: current.value.id })
      }
    },
  })
}

onMounted(reload)
</script>

<style scoped>
.task-card-list {
  display: flex;
  flex-direction: column;
  position: relative;
}
.task-card-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.task-card-title {
  font-weight: 600;
  font-size: 14px;
}
.task-card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}
.task-card-sub {
  font-size: 12px;
  color: var(--color-text-muted, #94a3b8);
}
.task-card-item.active {
  border-color: var(--color-primary, #0d9488);
  background: var(--color-surface-hover, rgba(20, 184, 166, 0.08));
}
.title {
  font-weight: 600;
  font-size: 16px;
  margin: 0 0 8px;
}
.meta {
  color: var(--color-text-muted, #94a3b8);
  font-size: 13px;
  margin: 0 0 16px;
}
.zt-card-prog {
  height: 4px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.18);
  margin-top: 6px;
  overflow: hidden;
}

.zt-card-prog i {
  display: block;
  height: 100%;
  border-radius: 999px;
}
.filter-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.filter-row .fchip {
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
  color: var(--color-text-muted);
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--zt-radius-pill);
  padding: 5px 14px;
  transition: color 0.2s ease, background-color 0.2s ease, border-color 0.2s ease;
}
.filter-row .fchip:hover {
  color: var(--color-text-primary);
}
.filter-row .fchip[aria-pressed='true'] {
  background: var(--color-primary-glow);
  color: var(--color-primary-hover);
  border-color: var(--color-primary);
}
.flip-gone {
  display: none;
}
</style>
