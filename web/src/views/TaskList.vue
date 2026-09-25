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

    <div class="page-body page-body--cols">
      <div class="two-col">
        <a-card title="活跃任务" :bordered="true">
          <div class="filter-row" role="group" aria-label="视图切换">
            <button
              v-for="c in tabChips"
              :key="c.key"
              class="fchip"
              type="button"
              :aria-pressed="String(viewTab === c.key)"
              @click="setTab(c.key)"
            >
              {{ c.label }} · {{ c.count }}
            </button>
          </div>
          <div v-if="viewTab === 'history' && archivedLoaded" class="filter-row" role="group" aria-label="状态筛选">
            <button
              v-for="c in histStatusChips"
              :key="c.key"
              class="fchip"
              type="button"
              :aria-pressed="String(histStatus === c.key)"
              @click="setHistStatus(c.key)"
            >
              {{ c.label }} · {{ histStatusCount(c.key) }}
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
          <div class="col-scroll">
            <a-spin :loading="loading || histLoading" style="width: 100%">
              <TransitionGroup v-if="leftItems.length" ref="listRef" name="zt-list" tag="div" class="task-card-list">
                <div
                  v-for="item in leftItems"
                  :key="item.key"
                  class="task-card-item"
                  :class="{
                    active: item.key === selectedKey,
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
                        <span v-if="item.task_type === 'periodic_instance'" class="zt-tag-periodic">
                          <PhRepeat :size="11" style="vertical-align: -1px" /> 周期
                        </span>
                        <span v-if="subCount(item).total" class="task-card-sub">
                          子任务 {{ subCount(item).done }}/{{ subCount(item).total }}
                        </span>
                        <span
                          v-if="deadlineInfo(item)"
                          class="task-card-sub"
                          :class="deadlineInfo(item).cls"
                        >
                          截止: {{ deadlineInfo(item).text }}
                        </span>
                      </template>
                      <template v-else-if="item.kind === 'tmpl'">
                        <span class="task-card-sub">
                          {{ periodLabel(item) }} · {{ item.paused ? '已暂停' : '下次派发 ' + (item.next_spawn_date || '—') }}
                        </span>
                      </template>
                      <template v-else>
                        <span class="task-card-sub">{{ formatTime(item.archived_at) }}</span>
                        <a-tag size="small" :color="STATUS_FAMILY[item.status] === 'done' ? 'green' : 'red'">
                          {{ STATUS_LABEL[item.status] || item.status }}
                        </a-tag>
                      </template>
                    </div>
                    <div v-if="item.kind === 'task' && subCount(item).total" class="zt-card-prog">
                      <i
                        :style="{
                          width: (subCount(item).done / subCount(item).total) * 100 + '%',
                          background: categoryColor(item.category),
                        }"
                      />
                    </div>
                  </div>
                </div>
              </TransitionGroup>
              <a-empty v-else-if="!loading" :description="emptyText" />
            </a-spin>
          </div>
        </a-card>

        <a-card title="任务详情与操作" :bordered="true">
          <template v-if="suggestOn" #extra>
            <a-button size="small" type="outline" :loading="suggestLoading" @click="onAiSuggest">
              <template #icon><PhLightbulb :size="15" /></template>
              AI 建议
            </a-button>
          </template>
          <div class="col-scroll">
            <!-- AI 建议卡片：应用即改任务，忽略即消失 -->
            <div v-if="suggestOn && (aiSuggestions.length || suggestLoading)" class="ai-suggest-box">
              <a-spin :loading="suggestLoading" style="width: 100%">
                <div v-for="(s, i) in aiSuggestions" :key="i" class="ai-suggest-card">
                  <div class="ai-suggest-main">
                    <a-tag size="small" :color="SUGGEST_COLOR[s.type] || 'gray'">{{ SUGGEST_LABEL[s.type] || '建议' }}</a-tag>
                    <span class="ai-suggest-text">{{ s.text }}</span>
                  </div>
                  <span v-if="s.target_title" class="ai-suggest-target">→ {{ s.target_title }}</span>
                  <div class="ai-suggest-ops">
                    <a-button
                      v-if="canApplySuggest(s)"
                      size="mini"
                      type="primary"
                      status="success"
                      @click="applySuggest(i)"
                    >
                      应用
                    </a-button>
                    <a-button size="mini" type="secondary" @click="aiSuggestions.splice(i, 1)">忽略</a-button>
                  </div>
                </div>
                <p v-if="!suggestLoading && !aiSuggestions.length" class="ai-suggest-empty">
                  暂无建议，列表状态良好 👌
                </p>
              </a-spin>
            </div>
            <!-- 任务态（单次 + 周期实例 + 孤儿） -->
            <template v-if="currentTask">
              <p class="title">{{ currentTask.title }}</p>
              <p class="meta">
                <a-tag
                  v-if="currentTask.category"
                  size="small"
                  :style="{
                    color: categoryColor(currentTask.category),
                    background: categoryColor(currentTask.category) + '24',
                    borderRadius: '999px',
                  }"
                >
                  {{ currentTask.category }}
                </a-tag>
                <span v-if="currentTask.priority" class="zt-pri" :class="PRI_CLASS[currentTask.priority] || 'zt-pri-l'">
                  {{ PRI_LABEL[currentTask.priority] || '低' }}
                </span>
                <br v-if="currentTask.deadline || currentTask.task_type === 'periodic_instance'" />
                <span v-if="currentTask.deadline">截止: {{ currentTask.deadline }}</span>
                <span v-if="currentTask.task_type === 'periodic_instance' && !currentTask.orphan" class="zt-origin">
                  周期实例
                  <a-link @click="goTemplateEdit">编辑模板</a-link>
                </span>
                <span v-else-if="currentTask.orphan" class="zt-origin">周期实例（模板已删除）</span>
                <br v-if="reminderText(currentTask) || currentTask.auto_abandon_on_overdue" />
                <span v-if="reminderText(currentTask)">提醒: {{ reminderText(currentTask) }}</span>
                <span v-if="currentTask.auto_abandon_on_overdue">　[逾期自动废弃]</span>
              </p>
              <p v-if="currentTask.details" class="details">{{ currentTask.details }}</p>

              <!-- 子任务 -->
              <div v-if="currentTask.subtasks?.length" class="subtasks">
                <div class="sub-head">
                  <span>子任务 {{ subCount(currentTask).done }}/{{ subCount(currentTask).total }}</span>
                  <div class="zt-card-prog sub-prog">
                    <i
                      :style="{
                        width: (subCount(currentTask).done / subCount(currentTask).total) * 100 + '%',
                        background: categoryColor(currentTask.category),
                      }"
                    />
                  </div>
                </div>
                <div
                  v-for="s in currentTask.subtasks"
                  :key="s.id"
                  class="sub-row"
                  :class="{ 'sub-done': s.status === 'done', 'sub-abandoned': s.status === 'abandoned' }"
                >
                  <span class="sub-title">{{ s.title }}</span>
                  <span v-if="s.status === 'active'" class="sub-ops">
                    <a-button size="mini" type="primary" status="success" @click="onSub(s.id, 'done')">完成</a-button>
                    <a-button size="mini" status="danger" @click="onSub(s.id, 'abandon')">废弃</a-button>
                  </span>
                  <a-tag v-else size="small" :color="s.status === 'done' ? 'green' : 'red'">
                    {{ s.status === 'done' ? '已完成' : '已废弃' }}
                  </a-tag>
                </div>
              </div>
              <div class="sub-add">
                <a-input v-model="newSubTitle" size="small" placeholder="添加子任务，回车确认" @press-enter="onAddSub" />
              </div>

              <div class="detail-actions">
                <a-button type="outline" @click="onSelect">
                  <template #icon><PhArrowsCounterClockwise :size="16" /></template>
                  切换到此任务
                </a-button>
                <a-button type="outline" @click="goEdit">
                  <template #icon><PhPencil :size="16" /></template>
                  编辑查看
                </a-button>
                <a-button type="primary" status="success" @click="onDone">
                  <template #icon><PhCheck :size="16" /></template>
                  完成
                </a-button>
                <a-button status="danger" @click="onAbandon">
                  <template #icon><PhTrash :size="16" /></template>
                  废弃
                </a-button>
              </div>
            </template>

            <!-- 模板态（纯生成器：暂停/恢复/跳过/删除，实例在活跃任务中管理） -->
            <template v-else-if="currentTmpl">
              <p class="title">{{ currentTmpl.base_title }}</p>
              <p class="meta">
                {{ periodLabel(currentTmpl) }}
                <a-tag
                  v-if="currentTmpl.category"
                  size="small"
                  :style="{
                    color: categoryColor(currentTmpl.category),
                    background: categoryColor(currentTmpl.category) + '24',
                    borderRadius: '999px',
                  }"
                >
                  {{ currentTmpl.category }}
                </a-tag>
                <span v-if="currentTmpl.priority" class="zt-pri" :class="PRI_CLASS[currentTmpl.priority] || 'zt-pri-l'">
                  {{ PRI_LABEL[currentTmpl.priority] || '低' }}
                </span>
                <br />
                <span :class="{ 'zt-paused': currentTmpl.paused }">
                  {{ currentTmpl.paused ? '已暂停（恢复后将为当前周期生成一次）' : '下次派发: ' + (currentTmpl.next_spawn_date || '—') }}
                </span>
                <br />
                <span>有效期: {{ currentTmpl.long_term ? '长期' : '至 ' + (currentTmpl.schedule_end_date || '—') }}</span>
                <span v-if="reminderText(currentTmpl)">　提醒: {{ reminderText(currentTmpl) }}</span>
                <span v-if="currentTmpl.auto_abandon_on_overdue">　[逾期自动废弃]</span>
                <template v-if="currentTmpl.subtasks?.length">
                  <br />
                  <span>预设子任务: {{ currentTmpl.subtasks.map((s) => s.title).join('、') }}</span>
                </template>
              </p>
              <p v-if="currentTmpl.details" class="details">{{ currentTmpl.details }}</p>
              <p class="meta">生成的实例在「活跃任务」中管理。</p>

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

            <!-- 历史任务（只读） -->
            <template v-else-if="currentHist">
              <p class="title">{{ currentHist.title }}</p>
              <p class="meta">
                {{ STATUS_LABEL[currentHist.status] || currentHist.status }} · {{ formatTime(currentHist.archived_at) }}
                <a-tag
                  v-if="currentHist.category"
                  size="small"
                  :style="{
                    color: categoryColor(currentHist.category),
                    background: categoryColor(currentHist.category) + '24',
                    borderRadius: '999px',
                  }"
                >
                  {{ currentHist.category }}
                </a-tag>
                <span v-if="currentHist.priority" class="zt-pri" :class="PRI_CLASS[currentHist.priority] || 'zt-pri-l'">
                  {{ PRI_LABEL[currentHist.priority] || '低' }}
                </span>
                <br />
                <span v-if="currentHist.attachment_count">附件数: {{ currentHist.attachment_count }}</span>
              </p>
              <p v-if="currentHist.details" class="details">{{ currentHist.details }}</p>
            </template>

            <a-empty v-else description="请选择左侧任务" />
          </div>
        </a-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { PhPlus, PhX, PhRepeat, PhArrowsCounterClockwise, PhPencil, PhCheck, PhTrash, PhLightbulb } from '@phosphor-icons/vue'
import {
  abandonTask,
  addSubtask,
  aiSuggest,
  cancelHost,
  closeHost,
  deleteTemplate,
  getMeta,
  listArchivedTasks,
  listTasks,
  listTemplates,
  markDone,
  selectTask,
  setSubtaskStatus,
  skipTemplate,
  updateTask,
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
const archived = ref([]) // 历史任务（懒加载）
const archivedLoaded = ref(false)
const histLoading = ref(false)

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

function formatTime(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 19)
}

/** 子任务计数：done = 已完成（active/done/abandoned） */
function subCount(item) {
  const subs = item?.subtasks || []
  return { done: subs.filter((s) => s.status === 'done').length, total: subs.length }
}

// ---- 三视图数据：活跃任务（一次性 + 周期实例）/ 周期模板 / 历史任务 ----
const knownTemplateIds = computed(() => new Set(templates.value.map((t) => t.template_id)))

/** 左栏统一条目：任务 key='t:'+id（周期实例带 orphan 标），模板 key='m:'+tid，历史 key='h:'+时间+序号 */
const leftItems = computed(() => [
  ...tasks.value.map((t) => ({
    ...t,
    key: `t:${t.id}`,
    kind: 'task',
    title: t.title,
    orphan: t.task_type === 'periodic_instance' && !knownTemplateIds.value.has(t.template_id),
  })),
  ...templates.value.map((t) => ({
    ...t,
    key: `m:${t.template_id}`,
    kind: 'tmpl',
    title: t.base_title,
  })),
  ...archived.value.map((a, i) => ({
    ...a,
    key: `h:${a.archived_at}:${i}`,
    kind: 'hist',
    title: a.title,
  })),
])

const current = computed(() => leftItems.value.find((i) => i.key === selectedKey.value) || null)
const currentTask = computed(() => (current.value?.kind === 'task' ? current.value : null))
const currentTmpl = computed(() => (current.value?.kind === 'tmpl' ? current.value : null))
const currentHist = computed(() => (current.value?.kind === 'hist' ? current.value : null))

// ---- 视图 tab（活跃/周期/历史）+ 分类筛选：双层 AND，class 隐藏配 Flip ----
const viewTab = ref('active')
const categoryFilter = ref('all') // 分类
const listRef = ref(null)

const STATUS_LABEL = { DONE: '已完成', ABANDONED: '已废弃', ABANDONED_OVERDUE: '逾期废弃' }
const STATUS_FAMILY = { DONE: 'done', ABANDONED: 'abandoned', ABANDONED_OVERDUE: 'abandoned' }
const histStatus = ref('all') // 历史状态筛选（客户端过滤）

const tabChips = computed(() => [
  { key: 'active', label: '活跃任务', count: tasks.value.length },
  { key: 'periodic', label: '周期任务', count: templates.value.length },
  { key: 'history', label: '历史任务', count: archived.value.length },
])

const histStatusChips = [
  { key: 'all', label: '全部' },
  { key: 'done', label: '已完成' },
  { key: 'abandoned', label: '已废弃' },
]

function histStatusCount(k) {
  if (k === 'all') return archived.value.length
  return archived.value.filter((a) => STATUS_FAMILY[a.status] === k).length
}

function matchesType(item) {
  // 活跃 = 全部在库任务（一次性 + 周期实例 + 孤儿）；周期 = 纯模板；历史 = 归档条目
  if (viewTab.value === 'active') return item.kind === 'task'
  if (viewTab.value === 'periodic') return item.kind === 'tmpl'
  return item.kind === 'hist' && (histStatus.value === 'all' || STATUS_FAMILY[item.status] === histStatus.value)
}

function matches(item) {
  const catOk = categoryFilter.value === 'all' || (item.category || '未分类') === categoryFilter.value
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

function setTab(k) {
  if (viewTab.value === k) return
  runFlip(() => {
    viewTab.value = k
  })
  if (k === 'history' && !archivedLoaded.value) loadArchived()
  ensureSelectionVisible()
}

function setHistStatus(k) {
  if (histStatus.value === k) return
  runFlip(() => {
    histStatus.value = k
  })
  ensureSelectionVisible()
}

/** 历史任务懒加载：状态筛选客户端做（与分类 chips 同机制，Flip 连续） */
async function loadArchived() {
  histLoading.value = true
  try {
    archived.value = await listArchivedTasks({ days: 90 })
    archivedLoaded.value = true
    if (viewTab.value === 'history' && !selectedKey.value) {
      selectedKey.value = leftItems.value.find(matches)?.key || null
    }
  } catch (e) {
    Message.error(e?.message || '历史加载失败')
  } finally {
    histLoading.value = false
  }
}

function setFilter(k) {
  if (categoryFilter.value === k) return
  runFlip(() => {
    categoryFilter.value = k
  })
  ensureSelectionVisible()
}

/** 分类在数据刷新后消失时回退到「全部」，避免假空列表 */
watch(categoryChips, (chips) => {
  if (!chips.some((c) => c.key === categoryFilter.value)) categoryFilter.value = 'all'
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
      // 外部入口（提醒等）经 ?select= 直达选中（含周期实例——活跃任务中作为普通卡管理）
      const want = route.query.select
      if (want && freshTasks.some((t) => t.id === want)) {
        viewTab.value = 'active'
        selectedKey.value = `t:${want}`
      } else {
        selectedKey.value = leftItems.value.find(matches)?.key || null
      }
    }
  } catch (e) {
    Message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

// ---- 头部 ----
const mainBtnLabel = computed(() => (viewTab.value === 'periodic' ? '新建周期任务' : '新建'))

function goNew() {
  const query = { from: 'list' }
  if (viewTab.value === 'periodic') query.mode = 'periodic'
  router.push({ path: '/tasks/new', query })
}

const emptyText = computed(() =>
  viewTab.value === 'active' ? '暂无活跃任务' : viewTab.value === 'periodic' ? '暂无周期任务' : '暂无历史记录'
)

// ---- 任务操作 ----
async function onSelect() {
  const t = currentTask.value
  if (!t) return
  await selectTask(t.id)
  Message.success('已切换')
  closeHost({ action: 'select', id: t.id })
}

function goEdit() {
  const t = currentTask.value
  if (!t) return
  router.push({ path: `/tasks/${t.id}/edit`, query: { from: 'list' } })
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

/** 存在活跃子任务时完成/废弃父任务需确认（连带结束子任务） */
function confirmWithSubs(t, verb) {
  const n = (t?.subtasks || []).filter((s) => s.status === 'active').length
  if (!n) return Promise.resolve(true)
  return new Promise((resolve) => {
    Modal.confirm({
      draggable: true,
      title: `仍有 ${n} 个活跃子任务`,
      content: `将连带 ${n} 个子任务一起结束，确定${verb}「${t.title}」？`,
      okText: `连带${verb}`,
      cancelText: '取消',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    })
  })
}

async function onDone() {
  const t = currentTask.value
  if (!t) return
  if (!(await confirmWithSubs(t, '完成'))) return
  await markDone(t.id)
  Message.success('已完成')
  finishAndRefresh(t.id)
}

function onAbandon() {
  const t = currentTask.value
  if (!t) return
  const doAbandon = async () => {
    await abandonTask(t.id)
    Message.success('已废弃')
    finishAndRefresh(t.id)
  }
  confirmWithSubs(t, '废弃').then((ok) => {
    if (!ok) return
    Modal.confirm({
      draggable: true,
      title: '确认废弃',
      content: `确定废弃「${t.title}」？`,
      onOk: doAbandon,
    })
  })
}

// ---- 子任务操作 ----
const newSubTitle = ref('')

watch(current, () => {
  newSubTitle.value = ''
})

async function onAddSub() {
  const t = currentTask.value
  const title = (newSubTitle.value || '').trim()
  if (!t || !title) return
  try {
    const fresh = await addSubtask(t.id, title)
    const i = tasks.value.findIndex((x) => x.id === t.id)
    if (i >= 0 && fresh) tasks.value[i] = fresh
    newSubTitle.value = ''
  } catch (e) {
    Message.error(e?.message || '添加失败')
  }
}

async function onSub(sid, action) {
  const t = currentTask.value
  if (!t) return
  try {
    const data = await setSubtaskStatus(t.id, sid, action)
    if (data.auto_completed) {
      // 子任务全部结束 → 父任务已自动完成归档，卡片离场
      Message.success('子任务全部结束，任务自动完成')
      finishAndRefresh(t.id)
      return
    }
    const i = tasks.value.findIndex((x) => x.id === t.id)
    if (i >= 0 && data.item) tasks.value[i] = data.item
  } catch (e) {
    Message.error(e?.message || '操作失败')
  }
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

// ---- AI 建议（开关来自 meta.ai_features.task_suggest，默认关）----

const SUGGEST_LABEL = { priority: '优先级', deadline: '截止日', split: '拆子任务', review: '复盘提醒', clean: '清理建议' }
const SUGGEST_COLOR = { priority: 'orangered', deadline: 'orange', split: 'cyan', review: 'purple', clean: 'gray' }
const suggestOn = ref(false)
const suggestLoading = ref(false)
const aiSuggestions = ref([])

onMounted(async () => {
  try {
    const meta = await getMeta()
    suggestOn.value = !!meta?.ai_features?.task_suggest
  } catch (_) {}
})

async function onAiSuggest() {
  suggestLoading.value = true
  aiSuggestions.value = []
  try {
    aiSuggestions.value = await aiSuggest(currentTask.value?.id || '')
  } catch (e) {
    Message.error(e?.response?.data?.error || e?.message || '获取建议失败')
  } finally {
    suggestLoading.value = false
  }
}

/** priority/deadline/split 带有效 patch 才可应用；review/clean 为纯文本提醒 */
function canApplySuggest(s) {
  if (s.type === 'priority') return !!s.patch?.priority
  if (s.type === 'deadline') return !!s.patch?.deadline
  if (s.type === 'split') return !!s.patch?.subtask_titles?.length
  return false
}

/** 建议目标：标题精确 → 互相包含 → 当前选中任务 */
function findSuggestTarget(s) {
  const title = s.target_title
  if (!title) return currentTask.value
  return (
    tasks.value.find((t) => t.title === title) ||
    tasks.value.find((t) => t.title.includes(title) || title.includes(t.title)) ||
    currentTask.value
  )
}

async function applySuggest(i) {
  const s = aiSuggestions.value[i]
  const t = findSuggestTarget(s)
  if (!t) return
  try {
    if (s.type === 'priority') {
      await updateTask(t.id, { priority: s.patch.priority })
    } else if (s.type === 'deadline') {
      await updateTask(t.id, { deadline: s.patch.deadline })
    } else if (s.type === 'split') {
      for (const st of s.patch.subtask_titles || []) await addSubtask(t.id, st)
    }
    Message.success('已应用')
    aiSuggestions.value.splice(i, 1)
    reload()
  } catch (e) {
    Message.error(e?.message || '应用失败')
  }
}
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
  flex-wrap: wrap;
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
  margin: 0 0 10px;
}
.meta {
  color: var(--color-text-muted, #94a3b8);
  font-size: 13px;
  margin: 0 0 12px;
  line-height: 1.8;
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
  margin: 0 0 12px;
  display: -webkit-box;
  -webkit-line-clamp: 5;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-line;
  word-break: break-word;
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
/* 子任务块 */
.subtasks {
  margin-bottom: 10px;
}
.meta .arco-tag,
.meta .zt-pri {
  margin-left: 6px;
}
.sub-head {
  font-size: 12px;
  color: var(--color-text-3);
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.sub-prog {
  flex: 1;
  margin-top: 0;
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
  transition: width 0.4s var(--zt-ease, ease-out);
}
.sub-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  border-top: 1px solid var(--color-border-2);
}
.sub-title {
  flex: 1;
  font-size: 13px;
  word-break: break-word;
}
.sub-ops {
  display: flex;
  gap: 6px;
  flex: none;
}
.sub-done .sub-title {
  text-decoration: line-through;
  color: var(--color-text-3);
}
.sub-abandoned .sub-title {
  color: var(--color-text-3);
}
.sub-add {
  margin-bottom: 12px;
}
/* 详情操作按钮：两行两列 */
.detail-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 4px;
}
.skip-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ---- 皮肤变体（body.zt-skin-* 门控，scoped 属性编译不受影响） ---- */
/* Aurora */
body.zt-skin-aurora .task-card-item.active {
  border-color: color-mix(in srgb, var(--color-primary, #0d9488) 60%, transparent);
  background: color-mix(in srgb, var(--color-primary, #0d9488) 10%, transparent);
}
body.zt-skin-aurora .filter-row .fchip[aria-pressed='true'] {
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--color-primary) 28%, transparent),
    color-mix(in srgb, #818cf8 26%, transparent)
  );
  color: var(--color-text-primary);
  border-color: color-mix(in srgb, var(--color-primary) 55%, transparent);
  box-shadow: 0 2px 10px var(--color-primary-glow);
}
body.zt-skin-aurora .sub-row {
  border-top: 1px solid color-mix(in srgb, var(--color-text-primary) 8%, transparent);
}
/* Neo */
body.zt-skin-neo .task-card-item.active {
  border-color: var(--zt-lime, #c8f542);
  background: color-mix(in srgb, var(--zt-lime, #c8f542) 7%, var(--color-surface));
}
/* kbd 键帽风格筛选 chip：小圆角 + 1.5px 描边 + 加粗底边 */
body.zt-skin-neo .filter-row .fchip {
  background: var(--color-surface);
  border: 1.5px solid var(--color-border);
  border-bottom-width: 3px;
  border-radius: 4px;
  padding: 4px 12px;
  transition: color var(--zt-dur-fast, 120ms) var(--zt-ease-out, ease),
    background-color var(--zt-dur-fast, 120ms) var(--zt-ease-out, ease),
    border-color var(--zt-dur-fast, 120ms) var(--zt-ease-out, ease),
    transform var(--zt-dur-fast, 120ms) var(--zt-ease-out, ease);
}
body.zt-skin-neo .filter-row .fchip:hover {
  border-color: var(--zt-cyan, #53e0d9);
  transform: translate(1px, 1px);
  border-bottom-width: 2px;
}
body.zt-skin-neo .filter-row .fchip[aria-pressed='true'] {
  background: var(--zt-lime, #c8f542);
  color: var(--zt-ink, #0b0d10);
  border-color: var(--zt-lime, #c8f542);
  border-bottom-color: color-mix(in srgb, var(--zt-ink, #0b0d10) 45%, var(--zt-lime, #c8f542));
  font-weight: 600;
}
body.zt-skin-neo .zt-card-prog {
  border-radius: 0;
  background: rgba(148, 163, 184, 0.2);
  border: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
}
body.zt-skin-neo .zt-card-prog i {
  border-radius: 0;
}

/* AI 建议卡片 */
.ai-suggest-box {
  border: 1px solid var(--color-border);
  border-radius: var(--zt-radius-card, 12px);
  padding: 10px 12px;
  margin-bottom: 12px;
  background: var(--color-fill-1, rgba(148, 163, 184, 0.06));
}
.ai-suggest-card {
  padding: 8px 0;
  border-bottom: 1px dashed var(--color-border-2);
}
.ai-suggest-card:last-child {
  border-bottom: none;
}
.ai-suggest-main {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.ai-suggest-text {
  font-size: 13px;
  flex: 1;
  word-break: break-word;
}
.ai-suggest-target {
  display: block;
  font-size: 12px;
  color: var(--color-text-3);
  margin: 4px 0 0 2px;
}
.ai-suggest-ops {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
  margin-top: 6px;
}
.ai-suggest-empty {
  font-size: 13px;
  color: var(--color-text-3);
  text-align: center;
  margin: 6px 0;
}
</style>
