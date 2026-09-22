<template>
  <div class="page">
    <div class="page-header">
      <h2>任务列表</h2>
      <a-space>
        <a-button type="primary" @click="goNew">
          <template #icon><PhPlus :size="16" /></template>
          {{ mainBtnLabel }}
        </a-button>
        <a-button type="secondary" @click="cancelHost" aria-label="关闭窗口">
          <template #icon><PhX :size="16" /></template>
        </a-button>
      </a-space>
    </div>

    <div class="two-col">
      <a-card title="活跃任务" :bordered="true">
        <div class="filter-row" role="group" aria-label="构成筛选">
          <button
            v-for="c in typeChips"
            :key="c.key"
            class="fchip"
            type="button"
            :aria-pressed="String(typeFilter === c.key)"
            @click="setType(c.key)"
          >
            {{ c.label }} · {{ c.count }}
          </button>
        </div>
        <div v-if="categoryChips.length > 1" class="filter-row" role="group" aria-label="分类筛选">
          <button
            v-for="c in categoryChips"
            :key="c.key"
            class="fchip"
            type="button"
            :aria-pressed="String(categoryFilter === c.key)"
            @click="setFilter(c.key)"
          >
            {{ c.label }} · {{ c.count }}
          </button>
        </div>
        <a-spin :loading="loading" style="width: 100%">
          <TransitionGroup v-if="leftItems.length" ref="listRef" name="zt-list" tag="div" class="task-card-list">
            <div
              v-for="item in leftItems"
              :key="item.key"
              class="task-card-item"
              :class="{
                active: item.key === selectedKey,
                dormant: item.kind === 'tmpl',
                'flip-gone': !matches(item),
              }"
              :data-task-id="item.kind === 'task' ? item.id : undefined"
              :style="item.kind === 'task' ? cardStyle(item) : {}"
              @click="selectedKey = item.key"
            >
              <div class="task-card-main">
                <span class="task-card-title">
                  {{ item.title }}
                  <span v-if="item.priority" class="zt-pri" :class="PRI_CLASS[item.priority] || 'zt-pri-l'">
                    {{ PRI_LABEL[item.priority] || '低' }}
                  </span>
                </span>
                <div class="task-card-meta">
                  <PhRepeat
                    v-if="item.kind === 'tmpl' || item.task_type === 'periodic_instance'"
                    class="zt-periodic-ico"
                    :size="13"
                  />
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
                  <template v-if="item.kind === 'task'">
                    <span class="task-card-sub">进度: {{ item.progress || 0 }}%</span>
                    <span
                      v-if="deadlineInfo(item)"
                      class="task-card-sub"
                      :class="deadlineInfo(item).cls"
                    >
                      截止: {{ deadlineInfo(item).text }}
                    </span>
                  </template>
                  <span v-else class="task-card-sub">
                    {{ periodLabel(item) }} · {{ item.paused ? '已暂停' : '下次派发 ' + (item.next_spawn_date || '—') }}
                  </span>
                </div>
                <div v-if="item.kind === 'task' && item.progress" class="zt-card-prog">
                  <i :style="{ width: (item.progress || 0) + '%', background: categoryColor(item.category) }" />
                </div>
              </div>
              <PhCheckCircle
                v-if="item.kind === 'task' && item.progress === 100"
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
        <!-- 实例态 -->
        <template v-if="currentTask">
          <p class="title">{{ currentTask.title }}</p>
          <p class="meta">
            分类: {{ currentTask.category }}　优先级: {{ PRI_LABEL[currentTask.priority] || '低' }}
            进度: {{ currentTask.progress || 0 }}%
            <br v-if="currentTask.deadline" />
            <span v-if="currentTask.deadline">截止: {{ currentTask.deadline }}</span>
            <span v-if="currentTask.task_type === 'periodic_instance'" class="zt-origin">
              周期实例
              <a-link @click="goTemplateEdit">编辑模板</a-link>
            </span>
            <span v-if="reminderText(currentTask)">　提醒: {{ reminderText(currentTask) }}</span>
            <span v-if="currentTask.auto_abandon_on_overdue">　[逾期自动废弃]</span>
          </p>
          <p v-if="currentTask.details" class="details">{{ currentTask.details }}</p>

          <div class="inline-prog">
            <div class="pct-row">
              <span ref="pctRef" class="pct-label">{{ percent }}%</span>
              <a-slider
                class="theme-slider"
                v-model="percent"
                :min="0"
                :max="100"
                :step="10"
                :style="{ flex: 1 }"
              />
            </div>
            <div class="prog-actions">
              <a-input v-model="note" placeholder="本次进展描述（选填）" allow-clear size="small" style="flex: 1" />
              <a-button type="primary" size="small" :loading="progressSaving" @click="onProgressSave">记录</a-button>
            </div>
          </div>

          <a-space direction="vertical" fill style="width: 100%; margin-top: 12px">
            <a-space fill style="width: 100%">
              <a-button long type="outline" style="flex: 1" @click="onSelect">
                <template #icon><PhArrowsCounterClockwise :size="16" /></template>
                切换到此任务
              </a-button>
              <a-button long type="outline" style="flex: 1" @click="goEdit">
                <template #icon><PhPencil :size="16" /></template>
                编辑查看
              </a-button>
            </a-space>
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

          <div v-if="recentLogs.length" class="recent">
            <div class="recent-head">最近进展</div>
            <div v-for="(log, i) in recentLogs" :key="i" class="recent-item">
              <span>{{ log.percent }}%</span>
              <span class="note">{{ formatTime(log.time) }} · {{ log.note || '无备注' }}</span>
            </div>
          </div>
        </template>

        <!-- 休眠模板态 -->
        <template v-else-if="currentTmpl">
          <p class="title">{{ currentTmpl.base_title }}</p>
          <p class="meta">
            {{ periodLabel(currentTmpl) }}　分类: {{ currentTmpl.category }}
            优先级: {{ PRI_LABEL[currentTmpl.priority] || '低' }}
            <br />
            <span :class="{ 'zt-paused': currentTmpl.paused }">
              {{ currentTmpl.paused ? '已暂停（恢复后将为当前周期生成一次）' : '下次派发: ' + (currentTmpl.next_spawn_date || '—') }}
            </span>
            <br />
            <span>有效期: {{ currentTmpl.long_term ? '长期' : '至 ' + (currentTmpl.schedule_end_date || '—') }}</span>
            <span v-if="reminderText(currentTmpl)">　提醒: {{ reminderText(currentTmpl) }}</span>
            <span v-if="currentTmpl.auto_abandon_on_overdue">　[逾期自动废弃]</span>
          </p>
          <p v-if="currentTmpl.details" class="details">{{ currentTmpl.details }}</p>

          <a-space direction="vertical" fill style="width: 100%; margin-top: 12px">
            <a-button long type="outline" @click="goTemplateEdit">
              <template #icon><PhPencil :size="16" /></template>
              编辑模板
            </a-button>
            <a-button long type="outline" @click="onTogglePause">
              {{ currentTmpl.paused ? '恢复派发' : '暂停派发' }}
            </a-button>
            <div class="skip-row">
              <span class="task-card-sub">跳过接下来</span>
              <a-input-number v-model="skipCount" :min="1" :max="30" size="small" style="width: 84px" />
              <span class="task-card-sub">次</span>
              <a-button size="small" type="outline" @click="onSkip">确定</a-button>
            </div>
            <a-button long status="danger" type="outline" @click="onDeleteTemplate">
              <template #icon><PhTrash :size="16" /></template>
              删除模板
            </a-button>
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
import { PhPlus, PhX, PhRepeat, PhArrowsCounterClockwise, PhPencil, PhCheck, PhTrash, PhCheckCircle } from '@phosphor-icons/vue'
import {
  abandonTask,
  cancelHost,
  closeHost,
  deleteTemplate,
  listTasks,
  listTemplates,
  markDone,
  selectTask,
  skipTemplate,
  updateProgress,
  updateTemplate,
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
const templates = ref([])
const selectedKey = ref(null)

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

function periodLabel(t) {
  const n = Math.max(1, Number(t.interval) || 1)
  const unit = { daily: '天', weekly: '周', monthly: '月' }[t.periodicity] || '天'
  return n > 1 ? `每 ${n} ${unit}` : `每${unit}`
}

function reminderText(t) {
  const r = t.reminder
  if (!r || !r.enabled) return ''
  const wd = '一二三四五六日'
  const slotText = (s) => {
    let label = s.time_of_day || ''
    if (s.weekday != null) label += `(周${wd[s.weekday % 7]})`
    else if (s.day_of_month != null) label += `(每月${s.day_of_month}日)`
    return label
  }
  return [r.time_of_day, ...(r.slots || []).map(slotText)].filter(Boolean).join(' / ')
}

function snap10(v) {
  const n = Math.max(0, Math.min(100, Number(v) || 0))
  return Math.round(n / 10) * 10
}

function formatTime(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 19)
}

// ---- 混排数据：任务 + 休眠模板（无活跃实例） ----
const periodicTasks = computed(() => tasks.value.filter((t) => t.task_type === 'periodic_instance'))
const activeTmplIds = computed(() => new Set(periodicTasks.value.map((t) => t.template_id)))
const dormantTemplates = computed(() =>
  templates.value.filter((t) => !activeTmplIds.value.has(t.template_id))
)

/** 左栏统一条目：任务 key='t:'+id，模板 key='m:'+template_id（Flip 靠前缀隔离） */
const leftItems = computed(() => [
  ...tasks.value.map((t) => ({ ...t, key: `t:${t.id}`, kind: 'task', title: t.title })),
  ...dormantTemplates.value.map((t) => ({
    ...t,
    key: `m:${t.template_id}`,
    kind: 'tmpl',
    title: t.base_title,
  })),
])

const current = computed(() => leftItems.value.find((i) => i.key === selectedKey.value) || null)
const currentTask = computed(() => (current.value?.kind === 'task' ? current.value : null))
const currentTmpl = computed(() => (current.value?.kind === 'tmpl' ? current.value : null))

// ---- 构成筛选（全部/一次性/周期）+ 分类筛选：双层 AND，class 隐藏配 Flip ----
const typeFilter = ref('all')
const filter = ref('all') // 分类
const listRef = ref(null)

const typeChips = computed(() => [
  { key: 'all', label: '全部', count: leftItems.value.length },
  { key: 'onetime', label: '一次性', count: tasks.value.length - periodicTasks.value.length },
  { key: 'periodic', label: '周期', count: periodicTasks.value.length + dormantTemplates.value.length },
])

function matchesType(item) {
  // 全部 = 任务实例 + 休眠模板：完成实例后模板原地转休眠，任何视图下周期任务不断档
  if (typeFilter.value === 'all') return true
  if (typeFilter.value === 'onetime') return item.kind === 'task' && item.task_type !== 'periodic_instance'
  return item.kind === 'tmpl' || item.task_type === 'periodic_instance'
}

function matches(item) {
  const catOk = filter.value === 'all' || (item.category || '未分类') === filter.value
  return matchesType(item) && catOk
}

// 分类 chips 计数基于构成筛选后的可见集合（模板 category 参与）
const categoryChips = computed(() => {
  const visible = leftItems.value.filter(matchesType)
  const counts = new Map()
  for (const t of visible) {
    const k = t.category || '未分类'
    counts.set(k, (counts.get(k) || 0) + 1)
  }
  const chips = [{ key: 'all', label: '全部', count: visible.length }]
  for (const [k, n] of counts) chips.push({ key: k, label: k, count: n })
  return chips.slice(0, 6)
})

function setType(k) {
  if (typeFilter.value === k) return
  runFlip(() => {
    typeFilter.value = k
  })
  ensureSelectionVisible()
}

function setFilter(k) {
  if (filter.value === k) return
  runFlip(() => {
    filter.value = k
  })
  ensureSelectionVisible()
}

/** 分类在数据刷新后消失时回退到「全部」，避免假空列表 */
watch(categoryChips, (chips) => {
  if (!chips.some((c) => c.key === filter.value)) filter.value = 'all'
})

/** 选中项被筛掉时回退到首个可见项 */
function ensureSelectionVisible() {
  if (!selectedKey.value) return
  if (leftItems.value.some((i) => i.key === selectedKey.value && matches(i))) return
  selectedKey.value = leftItems.value.find(matches)?.key || null
}

/** DOM 集合变化前后捕获/回放：幸存卡片流动，离场收缩淡出、回归弹性放大 */
async function runFlip(mutate) {
  const root = listRef.value?.$el ?? listRef.value // TransitionGroup 的 ref 是组件实例，$el 才是 tag 渲染的 div
  if (!root || motionOff() || isReduced()) {
    await mutate()
    return
  }
  const cards = root.querySelectorAll('.task-card-item')
  // 上一次 Flip 未完时接管，从当前视觉位置继续
  gsap.killTweensOf(cards)
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

async function reload() {
  loading.value = true
  try {
    const [freshTasks, freshTemplates] = await Promise.all([listTasks(), listTemplates()])
    runFlip(() => {
      tasks.value = freshTasks
      templates.value = freshTemplates
    })
    if (!selectedKey.value) {
      // 外部入口（提醒等）经 ?select= 直达选中
      const want = route.query.select
      if (want && freshTasks.some((t) => t.id === want)) {
        selectedKey.value = `t:${want}`
      } else {
        selectedKey.value = leftItems.value[0]?.key || null
      }
    }
  } catch (e) {
    Message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

// ---- 头部 ----
const mainBtnLabel = computed(() => (typeFilter.value === 'periodic' ? '新建周期任务' : '新建'))

function goNew() {
  const query = { from: 'list' }
  if (typeFilter.value === 'periodic') query.mode = 'periodic'
  router.push({ path: '/tasks/new', query })
}

// ---- 内联进度 ----
const percent = ref(0)
const note = ref('')
const progressSaving = ref(false)
const pctRef = ref(null)

watch(current, (c) => {
  percent.value = c?.kind === 'task' ? snap10(c.progress || 0) : 0
  note.value = ''
})

const recentLogs = computed(() =>
  currentTask.value ? [...(currentTask.value.progress_logs || [])].slice(-3).reverse() : []
)

/** 100% 达成庆祝：百分比数字弹性绽放（spec §3.5 关键时刻，单元素编排放行） */
function celebrateProgress() {
  if (motionOff() || isReduced()) return
  if (pctRef.value) {
    gsap.fromTo(pctRef.value, { scale: 1 }, { scale: 1.18, duration: 0.28, ease: EASE.spring, yoyo: true, repeat: 1, transformOrigin: '50% 50%' })
  }
}

async function onProgressSave() {
  const t = currentTask.value
  if (!t) return
  progressSaving.value = true
  try {
    const fresh = await updateProgress(t.id, snap10(percent.value), note.value)
    const i = tasks.value.findIndex((x) => x.id === t.id)
    if (i >= 0 && fresh) tasks.value[i] = fresh
    Message.success('进度已记录')
    note.value = ''
    if ((fresh?.progress ?? 0) >= 100) celebrateProgress()
  } catch (e) {
    Message.error(e?.message || '保存失败')
  } finally {
    progressSaving.value = false
  }
}

// ---- 实例操作 ----
async function onSelect() {
  if (!currentTask.value) return
  await selectTask(currentTask.value.id)
  Message.success('已切换')
  closeHost({ action: 'select', id: currentTask.value.id })
}

function goEdit() {
  if (!currentTask.value) return
  router.push({ path: `/tasks/${currentTask.value.id}/edit`, query: { from: 'list' } })
}

function goTemplateEdit() {
  const id = currentTask.value?.template_id || currentTmpl.value?.template_id
  if (!id) return
  router.push({ path: `/tasks/${id}/edit`, query: { template: '1', from: 'list' } })
}

/** 卡片离场庆祝：卡片弹性收缩浮起，邻居轻微让位（spec §3.5） */
function celebrateCard(itemId) {
  if (motionOff() || isReduced()) return false
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
  return !!target
}

/** 完成/废弃后留在列表刷新（列表为中心，不关窗） */
function finishAndRefresh(taskId) {
  celebrateCard(taskId)
  selectedKey.value = null
  setTimeout(reload, 520)
}

async function onDone() {
  if (!currentTask.value) return
  await markDone(currentTask.value.id)
  Message.success('已完成')
  finishAndRefresh(currentTask.value.id)
}

function onAbandon() {
  if (!currentTask.value) return
  Modal.confirm({
    draggable: true,
    title: '确认废弃',
    content: `确定废弃「${currentTask.value.title}」？`,
    onOk: async () => {
      await abandonTask(currentTask.value.id)
      Message.success('已废弃')
      finishAndRefresh(currentTask.value.id)
    },
  })
}

// ---- 模板操作 ----
const skipCount = ref(1)

async function onTogglePause() {
  const t = currentTmpl.value
  if (!t) return
  await updateTemplate(t.template_id, { paused: !t.paused })
  Message.success(t.paused ? '已恢复，将为当前周期生成一次' : '已暂停')
  reload()
}

async function onSkip() {
  const t = currentTmpl.value
  if (!t) return
  try {
    await skipTemplate(t.template_id, Math.max(1, Math.min(30, Number(skipCount.value) || 1)))
    Message.success(`已跳过接下来 ${skipCount.value} 次`)
    reload()
  } catch (e) {
    Message.error(e?.message || '跳过失败')
  }
}

function onDeleteTemplate() {
  const t = currentTmpl.value
  if (!t) return
  Modal.confirm({
    draggable: true,
    title: '确认删除',
    content: `确定删除「${t.base_title}」？已生成的实例不会自动删除。`,
    onOk: async () => {
      await deleteTemplate(t.template_id)
      Message.success('已删除')
      selectedKey.value = null
      reload()
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
.task-card-item.dormant {
  opacity: 0.62;
  border-style: dashed;
}
.title {
  font-weight: 600;
  font-size: 16px;
  margin: 0 0 8px;
}
.meta {
  color: var(--color-text-muted, #94a3b8);
  font-size: 13px;
  margin: 0 0 12px;
  line-height: 1.7;
}
.zt-origin {
  margin-left: 10px;
}
.zt-paused {
  color: rgb(var(--warning-6));
}
.details {
  font-size: 13px;
  color: var(--color-text-2, #cbd5e1);
  margin: 0 0 10px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-line;
  word-break: break-word;
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
.zt-periodic-ico {
  color: var(--color-text-muted, #94a3b8);
  flex: none;
}
.inline-prog {
  border-top: 1px solid var(--color-border-2);
  padding-top: 10px;
}
.pct-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.pct-label {
  font-size: 20px;
  font-weight: 700;
  min-width: 52px;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--primary-6));
}
.prog-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.skip-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.recent {
  margin-top: 14px;
}
.recent-head {
  font-size: 12px;
  color: var(--color-text-3);
  margin-bottom: 6px;
}
.recent-item {
  display: flex;
  gap: 10px;
  font-size: 12px;
  padding: 3px 0;
  border-top: 1px solid var(--color-border-2);
}
.note {
  color: var(--color-text-3);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.theme-slider :deep(.arco-slider-bar) {
  background: rgb(var(--primary-6));
}
.theme-slider :deep(.arco-slider-btn::after) {
  border-color: rgb(var(--primary-6));
}
</style>
