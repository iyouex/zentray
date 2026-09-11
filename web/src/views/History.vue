<template>
  <div class="page history-page">
    <div class="page-header">
      <h2>📜 历史记录</h2>
      <a-space>
        <a-select
          v-model="days"
          size="small"
          style="width: 110px"
          :options="dayOpts"
          @change="reload"
        />
        <a-button size="small" @click="cancelHost">关闭</a-button>
      </a-space>
    </div>

    <div class="page-body history-body">
      <a-tabs v-model:active-key="tab" type="rounded" size="small">
        <!-- ========== 任务 ========== -->
        <a-tab-pane key="task" title="任务">
          <div class="pane-shell">
            <div class="toolbar">
              <a-radio-group v-model="taskSort" size="mini" type="button">
                <a-radio value="desc">时间倒序</a-radio>
                <a-radio value="asc">时间正序</a-radio>
              </a-radio-group>
              <a-checkbox-group v-model="taskTypes" size="mini" class="type-chips">
                <a-checkbox
                  v-for="t in TASK_TYPE_OPTS"
                  :key="t.value"
                  :value="t.value"
                >
                  <span class="chip">{{ t.icon }} {{ t.label }}</span>
                </a-checkbox>
              </a-checkbox-group>
            </div>

            <a-spin :loading="loading" class="pane-spin">
              <div v-if="!filteredTaskEvents.length" class="empty-wrap">
                <a-empty description="暂无任务操作日志" />
              </div>
              <div v-else class="split">
                <div class="timeline-col">
                  <div
                    v-for="(e, i) in filteredTaskEvents"
                    :key="i"
                    class="tl-row"
                    :class="{ active: selectedTask === e }"
                    @click="selectedTask = e"
                  >
                    <div class="tl-rail">
                      <div class="tl-dot" :data-action="e.action" />
                      <div class="tl-line" />
                    </div>
                    <div class="tl-time">{{ formatClock(e.time) }}</div>
                    <div class="tl-main">
                      <span class="tl-icon" :title="actionLabel(e.action)">
                        {{ actionIcon(e.action) }}
                      </span>
                      <span class="tl-title">{{ e.title || '—' }}</span>
                      <a-tag size="small" :color="actionColor(e.action)">
                        {{ actionLabel(e.action) }}
                      </a-tag>
                    </div>
                  </div>
                </div>
                <div class="detail-col">
                  <template v-if="selectedTask">
                    <div class="detail-head">
                      <span class="detail-icon">{{ actionIcon(selectedTask.action) }}</span>
                      <div>
                        <div class="detail-title">{{ selectedTask.title || '—' }}</div>
                        <div class="detail-sub">
                          {{ actionLabel(selectedTask.action) }} ·
                          {{ formatFull(selectedTask.time) }}
                        </div>
                      </div>
                    </div>
                    <a-divider :margin="12" />
                    <div class="detail-block">
                      <div class="k">操作</div>
                      <div class="v">{{ actionLabel(selectedTask.action) }}（{{ selectedTask.action }}）</div>
                    </div>
                    <div class="detail-block">
                      <div class="k">时间</div>
                      <div class="v mono">{{ formatFull(selectedTask.time) }}</div>
                    </div>
                    <div class="detail-block">
                      <div class="k">详情</div>
                      <div class="v">{{ selectedTask.detail || '无' }}</div>
                    </div>
                    <div v-if="selectedTask.meta && Object.keys(selectedTask.meta).length" class="detail-block">
                      <div class="k">元数据</div>
                      <pre class="meta-pre">{{ formatMeta(selectedTask.meta) }}</pre>
                    </div>
                  </template>
                  <a-empty v-else description="选择时间轴上的事件查看详情" />
                </div>
              </div>
            </a-spin>
          </div>
        </a-tab-pane>

        <!-- ========== AI ========== -->
        <a-tab-pane key="ai" title="AI">
          <div class="pane-shell">
            <div class="toolbar">
              <a-radio-group v-model="aiSort" size="mini" type="button">
                <a-radio value="desc">时间倒序</a-radio>
                <a-radio value="asc">时间正序</a-radio>
              </a-radio-group>
              <a-checkbox-group v-model="aiTypes" size="mini" class="type-chips">
                <a-checkbox value="plan"><span class="chip">📋 计划</span></a-checkbox>
                <a-checkbox value="review"><span class="chip">📝 复盘</span></a-checkbox>
              </a-checkbox-group>
            </div>

            <a-spin :loading="loading" class="pane-spin">
              <div v-if="!filteredAiItems.length" class="empty-wrap">
                <a-empty description="暂无 AI 计划/复盘记录" />
              </div>
              <div v-else class="split">
                <div class="timeline-col">
                  <div
                    v-for="(item, i) in filteredAiItems"
                    :key="item.key"
                    class="tl-row"
                    :class="{ active: selectedAiKey === item.key }"
                    @click="selectAi(item)"
                  >
                    <div class="tl-rail">
                      <div class="tl-dot" :data-action="item.kind" />
                      <div class="tl-line" />
                    </div>
                    <div class="tl-time">{{ formatClock(item.time) }}</div>
                    <div class="tl-main">
                      <span class="tl-icon">{{ item.kind === 'plan' ? '📋' : '📝' }}</span>
                      <span class="tl-title">{{ item.label }}</span>
                      <a-tag
                        size="small"
                        :color="item.kind === 'plan' ? 'orangered' : 'purple'"
                      >
                        {{ item.kind === 'plan' ? '计划' : '复盘' }}
                      </a-tag>
                    </div>
                  </div>
                </div>
                <div class="detail-col">
                  <template v-if="selectedAiKey">
                    <div class="detail-head">
                      <span class="detail-icon">
                        {{ selectedAiItem?.kind === 'plan' ? '📋' : '📝' }}
                      </span>
                      <div>
                        <div class="detail-title">{{ selectedAiItem?.label }}</div>
                        <div class="detail-sub">
                          {{ formatFull(selectedAiItem?.time) }}
                          <span v-if="selectedAiItem?.detail"> · {{ selectedAiItem.detail }}</span>
                        </div>
                      </div>
                    </div>
                    <a-divider :margin="12" />
                    <a-spin :loading="loadingReport">
                      <pre v-if="reportContent" class="md-pre">{{ reportContent }}</pre>
                      <a-empty v-else description="暂无报告正文（可能未开启本地保存）" />
                    </a-spin>
                  </template>
                  <a-empty v-else description="选择时间轴上的报告查看全文" />
                </div>
              </div>
            </a-spin>
          </div>
        </a-tab-pane>

        <!-- ========== 全部 ========== -->
        <a-tab-pane key="all" title="全部">
          <div class="pane-shell">
            <div class="toolbar">
              <a-radio-group v-model="allCat" size="mini" type="button">
                <a-radio value="all">全部</a-radio>
                <a-radio value="task">任务</a-radio>
                <a-radio value="ai">AI</a-radio>
              </a-radio-group>
              <a-checkbox-group
                v-if="allCat !== 'ai'"
                v-model="allTaskTypes"
                size="mini"
                class="type-chips"
              >
                <a-checkbox
                  v-for="t in TASK_TYPE_OPTS"
                  :key="'a-' + t.value"
                  :value="t.value"
                >
                  <span class="chip">{{ t.icon }} {{ t.label }}</span>
                </a-checkbox>
              </a-checkbox-group>
              <a-checkbox-group
                v-if="allCat !== 'task'"
                v-model="allAiTypes"
                size="mini"
                class="type-chips"
              >
                <a-checkbox value="plan"><span class="chip">📋 计划</span></a-checkbox>
                <a-checkbox value="review"><span class="chip">📝 复盘</span></a-checkbox>
              </a-checkbox-group>
            </div>

            <a-spin :loading="loading" class="pane-spin">
              <div v-if="!allDateKeys.length" class="empty-wrap">
                <a-empty description="暂无记录" />
              </div>
              <div v-else class="split all-split">
                <div class="date-sidebar">
                  <div
                    v-for="d in allDateKeys"
                    :key="d"
                    class="date-item"
                    :class="{ active: selectedDate === d }"
                    @click="selectedDate = d"
                  >
                    <div class="date-label">{{ d }}</div>
                    <div class="date-count">{{ (eventsByDate[d] || []).length }} 条</div>
                  </div>
                </div>
                <div class="day-log-col">
                  <div v-if="!dayLogs.length" class="empty-wrap">
                    <a-empty description="该日无匹配日志" />
                  </div>
                  <div
                    v-for="(e, i) in dayLogs"
                    :key="i"
                    class="day-log-row"
                  >
                    <span class="day-time mono">{{ formatClock(e.time) }}</span>
                    <a-tag size="small" :color="e.category === 'ai' ? 'purple' : 'arcoblue'">
                      {{ e.category === 'ai' ? 'AI' : '任务' }}
                    </a-tag>
                    <span class="day-icon">{{
                      e.category === 'ai'
                        ? e.action === 'plan'
                          ? '📋'
                          : '📝'
                        : actionIcon(e.action)
                    }}</span>
                    <a-tag size="small" :color="actionColor(e.action)">
                      {{ actionLabel(e.action) }}
                    </a-tag>
                    <span class="day-title">{{ e.title || '—' }}</span>
                    <span v-if="e.detail" class="day-detail">{{ e.detail }}</span>
                  </div>
                </div>
              </div>
            </a-spin>
          </div>
        </a-tab-pane>
      </a-tabs>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { cancelHost, fetchHistory, fetchAiReport } from '@/api/client'

const TASK_TYPE_OPTS = [
  { value: 'create', label: '新增', icon: '➕' },
  { value: 'update', label: '编辑', icon: '✏️' },
  { value: 'progress', label: '更新', icon: '📈' },
  { value: 'delay', label: '延时', icon: '⏱' },
  { value: 'done', label: '完成', icon: '✅' },
  { value: 'abandon', label: '废弃', icon: '🗑' },
]

const ALL_TASK_TYPES = TASK_TYPE_OPTS.map((t) => t.value)

const loading = ref(false)
const loadingReport = ref(false)
const tab = ref('task')
const days = ref(30)
const events = ref([])
const aiReports = ref([])

const taskSort = ref('desc')
const taskTypes = ref([...ALL_TASK_TYPES])
const selectedTask = ref(null)

const aiSort = ref('desc')
const aiTypes = ref(['plan', 'review'])
const selectedAiKey = ref('')
const reportContent = ref('')

const allCat = ref('all')
const allTaskTypes = ref([...ALL_TASK_TYPES])
const allAiTypes = ref(['plan', 'review'])
const selectedDate = ref('')

const dayOpts = [
  { label: '近 7 天', value: 7 },
  { label: '近 30 天', value: 30 },
  { label: '近 90 天', value: 90 },
]

const ACTION_META = {
  create: { label: '新增', icon: '➕', color: 'green' },
  update: { label: '编辑', icon: '✏️', color: 'arcoblue' },
  progress: { label: '更新', icon: '📈', color: 'cyan' },
  delay: { label: '延时', icon: '⏱', color: 'orangered' },
  done: { label: '完成', icon: '✅', color: 'green' },
  abandon: { label: '废弃', icon: '🗑', color: 'red' },
  select: { label: '切换', icon: '🎯', color: 'gray' },
  plan: { label: '计划', icon: '📋', color: 'orangered' },
  review: { label: '复盘', icon: '📝', color: 'purple' },
}

function actionLabel(a) {
  return ACTION_META[a]?.label || a
}
function actionIcon(a) {
  return ACTION_META[a]?.icon || '•'
}
function actionColor(a) {
  return ACTION_META[a]?.color || 'gray'
}

function formatClock(t) {
  if (!t) return ''
  const s = String(t).replace('T', ' ')
  return s.length >= 19 ? s.slice(11, 19) : s.slice(11)
}

function formatFull(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 19)
}

function formatMeta(m) {
  try {
    return JSON.stringify(m, null, 2)
  } catch {
    return String(m)
  }
}

function eventDate(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 10)
}

function sortByTime(list, order) {
  const arr = [...list]
  arr.sort((a, b) => {
    const ta = String(a.time || '')
    const tb = String(b.time || '')
    return order === 'asc' ? ta.localeCompare(tb) : tb.localeCompare(ta)
  })
  return arr
}

/** 任务事件（含 select 但默认筛选不含） */
const filteredTaskEvents = computed(() => {
  let list = events.value.filter((e) => e.category === 'task')
  if (taskTypes.value.length) {
    list = list.filter((e) => taskTypes.value.includes(e.action))
  } else {
    list = []
  }
  return sortByTime(list, taskSort.value)
})

/**
 * AI 时间轴项：优先 activity 事件，并与 reviews 文件合并。
 * 标签：日期-复盘/计划-#序号
 */
const aiItems = computed(() => {
  const fromEvents = events.value
    .filter((e) => e.category === 'ai' && (e.action === 'plan' || e.action === 'review'))
    .map((e) => {
      const kind = e.action
      const date = e.meta?.date || eventDate(e.time)
      const file = e.meta?.file || ''
      return {
        key: `ev-${e.time}-${kind}-${e.title}`,
        kind,
        time: e.time,
        date,
        file,
        detail: e.detail,
        seq: e.meta?.seq || 0,
        title: e.title,
        source: 'event',
      }
    })

  // 文件侧：补全无日志的报告
  const eventFiles = new Set(fromEvents.map((x) => x.file).filter(Boolean))
  for (const r of aiReports.value) {
    if (eventFiles.has(r.name)) continue
    fromEvents.push({
      key: `file-${r.name}`,
      kind: r.kind,
      time: r.mtime,
      date: r.date || eventDate(r.mtime),
      file: r.name,
      detail: '',
      seq: r.seq || 0,
      title: r.label || r.name,
      source: 'file',
    })
  }

  // 按 (date, kind) 升序赋序号
  const groups = {}
  for (const item of fromEvents) {
    const k = `${item.date}|${item.kind}`
    if (!groups[k]) groups[k] = []
    groups[k].push(item)
  }
  for (const items of Object.values(groups)) {
    items.sort((a, b) => String(a.time).localeCompare(String(b.time)))
    items.forEach((item, i) => {
      item.seq = i + 1
      const kindCn = item.kind === 'plan' ? '计划' : '复盘'
      item.label = `${item.date}-${kindCn}-#${item.seq}`
    })
  }
  return fromEvents
})

const filteredAiItems = computed(() => {
  let list = aiItems.value.filter((x) => aiTypes.value.includes(x.kind))
  return sortByTime(list, aiSort.value)
})

const selectedAiItem = computed(() =>
  filteredAiItems.value.find((x) => x.key === selectedAiKey.value) || null,
)

/** 全部页：按筛选后的事件按日期分组 */
const filteredAllEvents = computed(() => {
  return events.value.filter((e) => {
    if (allCat.value === 'task' && e.category !== 'task') return false
    if (allCat.value === 'ai' && e.category !== 'ai') return false
    if (e.category === 'task') {
      if (!allTaskTypes.value.includes(e.action)) return false
    } else if (e.category === 'ai') {
      if (!allAiTypes.value.includes(e.action)) return false
    }
    return true
  })
})

const eventsByDate = computed(() => {
  const map = {}
  for (const e of filteredAllEvents.value) {
    const d = eventDate(e.time)
    if (!d) continue
    if (!map[d]) map[d] = []
    map[d].push(e)
  }
  for (const d of Object.keys(map)) {
    map[d].sort((a, b) => String(b.time).localeCompare(String(a.time)))
  }
  return map
})

const allDateKeys = computed(() =>
  Object.keys(eventsByDate.value).sort((a, b) => b.localeCompare(a)),
)

const dayLogs = computed(() => {
  if (!selectedDate.value) return []
  return eventsByDate.value[selectedDate.value] || []
})

watch(filteredTaskEvents, (list) => {
  if (!list.length) {
    selectedTask.value = null
    return
  }
  if (!selectedTask.value || !list.includes(selectedTask.value)) {
    selectedTask.value = list[0]
  }
})

watch(filteredAiItems, (list) => {
  if (!list.length) {
    selectedAiKey.value = ''
    reportContent.value = ''
    return
  }
  if (!list.find((x) => x.key === selectedAiKey.value)) {
    selectAi(list[0])
  }
})

watch(allDateKeys, (keys) => {
  if (!keys.length) {
    selectedDate.value = ''
    return
  }
  if (!keys.includes(selectedDate.value)) {
    selectedDate.value = keys[0]
  }
})

async function selectAi(item) {
  selectedAiKey.value = item.key
  reportContent.value = ''
  if (!item.file) {
    // 尝试用 label 匹配报告
    const hit = aiReports.value.find(
      (r) => r.label === item.label || (r.date === item.date && r.kind === item.kind && r.seq === item.seq),
    )
    if (hit) {
      await loadReport(hit.name)
    }
    return
  }
  await loadReport(item.file)
}

async function loadReport(name) {
  loadingReport.value = true
  try {
    const data = await fetchAiReport(name)
    reportContent.value = data.content || ''
  } catch (e) {
    reportContent.value = ''
    Message.error(e?.message || '读取失败')
  } finally {
    loadingReport.value = false
  }
}

async function reload() {
  loading.value = true
  try {
    const data = await fetchHistory({ days: days.value, category: 'all' })
    events.value = data.events || []
    aiReports.value = data.ai_reports || []
  } catch (e) {
    Message.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.history-page {
  overflow: hidden;
}
.history-body {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.history-body :deep(.arco-tabs) {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.history-body :deep(.arco-tabs-nav) {
  flex-shrink: 0;
}
.history-body :deep(.arco-tabs-content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.history-body :deep(.arco-tabs-content-item),
.history-body :deep(.arco-tabs-pane) {
  height: 100%;
}
.pane-shell {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  gap: 8px;
}
.toolbar {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
  padding: 2px 0 6px;
  border-bottom: 1px solid var(--color-border-2);
}
.type-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
}
.chip {
  font-size: 12px;
}
.pane-spin {
  flex: 1;
  min-height: 0;
  width: 100%;
  display: block;
  overflow: hidden;
}
.pane-spin :deep(.arco-spin) {
  height: 100%;
  width: 100%;
  display: block;
}
.pane-spin :deep(.arco-spin-children) {
  height: 100%;
  min-height: 0;
}
.empty-wrap {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
}
.split {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(240px, 1fr);
  gap: 12px;
  height: 100%;
  min-height: 0;
}
.all-split {
  grid-template-columns: 148px 1fr;
}
.timeline-col {
  overflow: auto;
  min-height: 0;
  padding-right: 4px;
  border-right: 1px solid var(--color-border-2);
}
.tl-row {
  display: grid;
  grid-template-columns: 14px 64px 1fr;
  gap: 6px;
  align-items: start;
  padding: 8px 8px 8px 2px;
  border-radius: var(--zt-radius-md);
  cursor: pointer;
  min-height: 44px;
}
.tl-row:hover {
  background: var(--color-fill-1);
}
.tl-row.active {
  background: var(--color-fill-2);
}
.tl-rail {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  min-height: 36px;
  padding-top: 4px;
}
.tl-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: rgb(var(--primary-6));
  flex-shrink: 0;
  z-index: 1;
}
.tl-dot[data-action='done'] {
  background: #00b42a;
}
.tl-dot[data-action='abandon'] {
  background: #f53f3f;
}
.tl-dot[data-action='delay'] {
  background: #ff7d00;
}
.tl-dot[data-action='plan'] {
  background: #f77234;
}
.tl-dot[data-action='review'] {
  background: #722ed1;
}
.tl-line {
  width: 2px;
  flex: 1;
  background: var(--color-border-2);
  margin-top: 2px;
  min-height: 16px;
}
.tl-row:last-child .tl-line {
  display: none;
}
.tl-time {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-3);
  padding-top: 2px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.tl-main {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  min-width: 0;
}
.tl-icon {
  font-size: 14px;
  flex-shrink: 0;
}
.tl-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}
.detail-col {
  overflow: auto;
  min-height: 0;
  padding: 8px 10px;
  border: 1px solid var(--color-border-2);
  border-radius: var(--zt-radius-md);
  background: var(--color-fill-1);
}
.detail-head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.detail-icon {
  font-size: 22px;
  line-height: 1.2;
}
.detail-title {
  font-size: 15px;
  font-weight: 700;
  word-break: break-word;
}
.detail-sub {
  font-size: 12px;
  color: var(--color-text-3);
  margin-top: 2px;
}
.detail-block {
  margin-bottom: 10px;
}
.detail-block .k {
  font-size: 11px;
  color: var(--color-text-3);
  margin-bottom: 2px;
}
.detail-block .v {
  font-size: 13px;
  color: var(--color-text-1);
  word-break: break-word;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
}
.meta-pre,
.md-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.date-sidebar {
  overflow: auto;
  min-height: 0;
  border-right: 1px solid var(--color-border-2);
  padding-right: 6px;
}
.date-item {
  padding: 10px 8px;
  border-radius: var(--zt-radius-md);
  cursor: pointer;
  margin-bottom: 2px;
}
.date-item:hover {
  background: var(--color-fill-1);
}
.date-item.active {
  background: var(--color-fill-2);
}
.date-label {
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.date-count {
  font-size: 11px;
  color: var(--color-text-3);
  margin-top: 2px;
}
.day-log-col {
  overflow: auto;
  min-height: 0;
  padding: 0 4px;
}
.day-log-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  padding: 8px 6px;
  border-bottom: 1px solid var(--color-border-2);
  font-size: 13px;
}
.day-time {
  font-size: 12px;
  color: var(--color-text-3);
  min-width: 58px;
}
.day-title {
  font-weight: 600;
  color: var(--color-text-1);
}
.day-detail {
  width: 100%;
  font-size: 12px;
  color: var(--color-text-3);
  padding-left: 66px;
}
@media (max-width: 720px) {
  .split {
    grid-template-columns: 1fr;
  }
  .all-split {
    grid-template-columns: 1fr;
  }
  .timeline-col {
    border-right: none;
    border-bottom: 1px solid var(--color-border-2);
    max-height: 40vh;
  }
  .date-sidebar {
    border-right: none;
    border-bottom: 1px solid var(--color-border-2);
    display: flex;
    gap: 4px;
    overflow-x: auto;
    max-height: none;
  }
  .date-item {
    flex-shrink: 0;
  }
}
</style>
