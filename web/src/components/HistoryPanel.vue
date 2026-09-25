<template>
  <div class="hist-panel">
    <div class="hist-toolbar">
      <a-select
        v-model="days"
        size="small"
        style="width: 110px; flex: none"
        :options="dayOpts"
        @change="reload"
      />
      <a-checkbox-group v-model="filters" size="mini" class="hist-chips">
        <a-checkbox v-for="t in FILTER_OPTS" :key="t.value" :value="t.value">
          <span class="chip">{{ t.icon }} {{ t.label }}</span>
        </a-checkbox>
      </a-checkbox-group>
    </div>

    <a-spin :loading="loading" class="hist-spin">
      <div v-if="!dateKeys.length" class="hist-empty">
        <a-empty description="暂无记录" />
      </div>
      <div v-else class="hist-main">
        <!-- 日期侧栏 -->
        <div class="date-col">
          <div
            v-for="d in dateKeys"
            :key="d"
            class="date-item"
            :class="{ active: selectedDate === d }"
            @click="selectedDate = d"
          >
            <div class="date-label">{{ d }}</div>
            <div class="date-count">{{ rowsByDate[d].length }} 条</div>
          </div>
        </div>

        <!-- 统一时间轴（任务 + AI 合并） -->
        <div class="tl-col">
          <div v-if="!dayRows.length" class="hist-empty">
            <a-empty description="该日无匹配记录" />
          </div>
          <div
            v-for="r in dayRows"
            :key="r.key"
            class="tl-row"
            :class="{ active: selectedKey === r.key }"
            @click="selectRow(r)"
          >
            <span class="tl-time">{{ formatClock(r.time) }}</span>
            <a-tag size="small" :color="r.cat === 'ai' ? 'purple' : 'arcoblue'">
              {{ r.cat === 'ai' ? 'AI' : '任务' }}
            </a-tag>
            <span class="tl-icon">{{ actionIcon(r.action) }}</span>
            <a-tag size="small" :color="actionColor(r.action)">{{ actionLabel(r.action) }}</a-tag>
            <span class="tl-title">{{ r.title || '—' }}</span>
          </div>
        </div>

        <!-- 详情栏 -->
        <div class="detail-col">
          <template v-if="selectedRow">
            <div class="detail-head">
              <span class="detail-icon">{{ actionIcon(selectedRow.action) }}</span>
              <div>
                <div class="detail-title">{{ selectedRow.title || '—' }}</div>
                <div class="detail-sub">{{ actionLabel(selectedRow.action) }} · {{ formatFull(selectedRow.time) }}</div>
              </div>
            </div>
            <a-divider :margin="12" />

            <!-- AI 报告全文 -->
            <template v-if="selectedRow.cat === 'ai'">
              <a-spin :loading="loadingReport" style="width: 100%">
                <pre v-if="reportContent" class="md-pre">{{ reportContent }}</pre>
                <a-empty v-else description="暂无报告正文（可能未开启本地保存）" />
              </a-spin>
            </template>

            <!-- 任务事件详情块 -->
            <template v-else>
              <div class="detail-block">
                <div class="k">操作</div>
                <div class="v">{{ actionLabel(selectedRow.action) }}（{{ selectedRow.action }}）</div>
              </div>
              <div class="detail-block">
                <div class="k">时间</div>
                <div class="v mono">{{ formatFull(selectedRow.time) }}</div>
              </div>
              <div class="detail-block">
                <div class="k">详情</div>
                <div class="v">{{ selectedRow.detail || '无' }}</div>
              </div>
              <div v-if="selectedRow.meta && Object.keys(selectedRow.meta).length" class="detail-block">
                <div class="k">元数据</div>
                <pre class="md-pre">{{ formatMeta(selectedRow.meta) }}</pre>
              </div>
            </template>
          </template>
          <a-empty v-else description="选择时间轴上的记录查看详情" />
        </div>
      </div>
    </a-spin>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { fetchAiReport, fetchHistory } from '@/api/client'

/** 筛选项：任务 6 操作 + AI 计划/复盘，默认全开 */
const FILTER_OPTS = [
  { value: 'create', label: '新增', icon: '➕' },
  { value: 'update', label: '编辑', icon: '✏️' },
  { value: 'progress', label: '更新', icon: '📈' },
  { value: 'delay', label: '延时', icon: '⏱' },
  { value: 'done', label: '完成', icon: '✅' },
  { value: 'abandon', label: '废弃', icon: '🗑' },
  { value: 'plan', label: '计划', icon: '📋' },
  { value: 'review', label: '复盘', icon: '📝' },
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

const dayOpts = [
  { label: '近 7 天', value: 7 },
  { label: '近 30 天', value: 30 },
  { label: '近 90 天', value: 90 },
]

const loading = ref(false)
const loadingReport = ref(false)
const days = ref(30)
const filters = ref(FILTER_OPTS.map((t) => t.value))
const events = ref([])
const aiReports = ref([])
const selectedDate = ref('')
const selectedKey = ref('')
const reportContent = ref('')

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

/** AI 条目：activity 事件 ∪ reviews 文件（无日志的补全），按 (日期, 类型) 编序号 */
const aiItems = computed(() => {
  const items = events.value
    .filter((e) => e.category === 'ai' && (e.action === 'plan' || e.action === 'review'))
    .map((e) => ({
      cat: 'ai',
      action: e.action,
      time: e.time,
      date: e.meta?.date || eventDate(e.time),
      file: e.meta?.file || '',
      detail: e.detail,
      title: e.title,
      meta: e.meta,
    }))
  const eventFiles = new Set(items.map((x) => x.file).filter(Boolean))
  for (const r of aiReports.value) {
    if (eventFiles.has(r.name)) continue
    items.push({
      cat: 'ai',
      action: r.kind,
      time: r.mtime,
      date: r.date || eventDate(r.mtime),
      file: r.name,
      detail: '',
      title: r.label || r.name,
      meta: null,
    })
  }
  const groups = {}
  for (const item of items) {
    const k = `${item.date}|${item.action}`
    if (!groups[k]) groups[k] = []
    groups[k].push(item)
  }
  for (const list of Object.values(groups)) {
    list.sort((a, b) => String(a.time).localeCompare(String(b.time)))
    list.forEach((item, i) => {
      item.seq = i + 1
      const kindCn = item.action === 'plan' ? '计划' : '复盘'
      item.title = item.title || `${item.date}-${kindCn}`
    })
  }
  return items
})

/** 统一行集：任务事件 + AI 条目，经筛选后按日期分组倒序 */
const rowsByDate = computed(() => {
  const rows = []
  for (const e of events.value) {
    if (e.category !== 'task') continue
    if (!filters.value.includes(e.action)) continue
    rows.push({
      key: `t-${e.time}-${e.action}-${e.title}`,
      cat: 'task',
      action: e.action,
      time: e.time,
      detail: e.detail,
      title: e.title,
      meta: e.meta,
    })
  }
  for (const a of aiItems.value) {
    if (!filters.value.includes(a.action)) continue
    rows.push({
      key: `a-${a.time}-${a.action}-${a.title}-${a.seq}`,
      cat: 'ai',
      action: a.action,
      time: a.time,
      file: a.file,
      date: a.date,
      seq: a.seq,
      detail: a.detail,
      title: a.title,
      meta: null,
    })
  }
  const map = {}
  for (const r of rows) {
    const d = eventDate(r.time)
    if (!d) continue
    if (!map[d]) map[d] = []
    map[d].push(r)
  }
  for (const d of Object.keys(map)) {
    map[d].sort((a, b) => String(b.time).localeCompare(String(a.time)))
  }
  return map
})

const dateKeys = computed(() =>
  Object.keys(rowsByDate.value).sort((a, b) => b.localeCompare(a)),
)

const dayRows = computed(() => rowsByDate.value[selectedDate.value] || [])

const selectedRow = computed(() => dayRows.value.find((r) => r.key === selectedKey.value) || null)

watch(dateKeys, (keys) => {
  if (!keys.length) {
    selectedDate.value = ''
    return
  }
  if (!keys.includes(selectedDate.value)) selectedDate.value = keys[0]
})

watch(dayRows, (rows) => {
  const hit = rows.find((r) => r.key === selectedKey.value)
  selectedKey.value = hit ? hit.key : ''
  reportContent.value = ''
})

/** AI 行点击后加载报告正文（file 缺失时按 日期+类型+序号 兜底匹配） */
function selectRow(r) {
  selectedKey.value = r.key
  reportContent.value = ''
  if (r.cat !== 'ai') return
  let file = r.file
  if (!file) {
    const kindCn = r.action === 'plan' ? '计划' : '复盘'
    const label = `${r.date}-${kindCn}-#${r.seq}`
    const hit = aiReports.value.find(
      (x) => x.label === label || (x.date === r.date && x.kind === r.action && x.seq === r.seq),
    )
    file = hit?.name
  }
  if (file) loadReport(file)
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
.hist-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hist-toolbar {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
  padding: 2px 0 6px;
  border-bottom: 1px solid var(--color-border-2);
}
.hist-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
}
.chip {
  font-size: 12px;
}
.hist-spin {
  flex: 1;
  min-height: 0;
  width: 100%;
  display: block;
}
.hist-spin :deep(.arco-spin) {
  height: 100%;
  width: 100%;
  display: block;
}
.hist-spin :deep(.arco-spin-children) {
  height: 100%;
  min-height: 0;
}
.hist-empty {
  height: 100%;
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.hist-main {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: 128px minmax(260px, 1fr) minmax(280px, 1.1fr);
  gap: 12px;
}
.date-col {
  overflow: auto;
  min-height: 0;
  border-right: 1px solid var(--color-border-2);
  padding-right: 6px;
}
.date-item {
  padding: 9px 8px;
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
.tl-col {
  overflow: auto;
  min-height: 0;
  padding-right: 4px;
}
.tl-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  padding: 8px 6px;
  border-bottom: 1px solid var(--color-border-2);
  border-radius: var(--zt-radius-md);
  cursor: pointer;
  font-size: 13px;
}
.tl-row:hover {
  background: var(--color-fill-1);
}
.tl-row.active {
  background: var(--color-fill-2);
}
.tl-time {
  font-size: 12px;
  color: var(--color-text-3);
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.tl-icon {
  font-size: 14px;
}
.tl-title {
  font-weight: 600;
  color: var(--color-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
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
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.md-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
@media (max-width: 760px) {
  .hist-main {
    grid-template-columns: 1fr;
  }
  .date-col {
    display: flex;
    gap: 4px;
    overflow-x: auto;
    border-right: none;
    border-bottom: 1px solid var(--color-border-2);
  }
  .date-item {
    flex-shrink: 0;
  }
}

/* ---- 皮肤变体（body.zt-skin-* 门控） ---- */
/* Aurora */
body.zt-skin-aurora .date-item.active {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--color-primary) 18%, transparent),
    transparent
  );
}
body.zt-skin-aurora .tl-col {
  padding-left: 14px;
  position: relative;
}
/* 极光时间轴脊线 */
body.zt-skin-aurora .tl-col::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 6px;
  bottom: 6px;
  width: 2px;
  border-radius: 999px;
  background: linear-gradient(180deg, var(--color-primary), #818cf8 60%, transparent);
  opacity: 0.5;
  pointer-events: none;
}
body.zt-skin-aurora .tl-row.active {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--color-primary) 16%, transparent),
    transparent
  );
}
body.zt-skin-aurora .detail-col {
  border: 1px solid color-mix(in srgb, var(--color-text-primary) 9%, transparent);
  background: color-mix(in srgb, var(--color-surface) 45%, transparent);
  backdrop-filter: blur(14px) saturate(1.4);
  -webkit-backdrop-filter: blur(14px) saturate(1.4);
}
/* Neo */
body.zt-skin-neo .hist-chips :deep(.arco-checkbox) {
  border: 1.5px solid var(--color-border);
  border-bottom-width: 2.5px;
  border-radius: 4px;
  padding: 2px 8px;
  transition: border-color var(--zt-dur-fast, 120ms) var(--zt-ease-out, ease),
    background-color var(--zt-dur-fast, 120ms) var(--zt-ease-out, ease);
}
body.zt-skin-neo .hist-chips :deep(.arco-checkbox:hover) {
  border-color: var(--zt-cyan, #53e0d9);
}
body.zt-skin-neo .hist-chips :deep(.arco-checkbox.arco-checkbox-checked) {
  border-color: var(--zt-lime, #c8f542);
  background: color-mix(in srgb, var(--zt-lime, #c8f542) 10%, transparent);
}
body.zt-skin-neo .detail-col {
  border: 1.5px solid var(--color-border);
}
</style>
